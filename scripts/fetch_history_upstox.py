#!/usr/bin/env python3
"""
Upstox historical 5-min backfill — the deep-history source for backtesting.

Why Upstox: the v3 historical-candle endpoint is public (no account, no auth,
browser User-Agent required), serves native 5-min OHLCV back to at least
Feb 2022, one calendar month per request. Verified 2026-07-19. This replaces
the Dhan Data API (declined: paid) and breaks Yahoo's 60-day ceiling.

Output: data/history_cache_upstox/{TICKER}_5min_upstox.json — same bar format
as the Yahoo cache ({dt, open, high, low, close, volume}) but kept in a
SEPARATE directory so sources never silently mix. Cross-validate before use:
python scripts/fetch_history_upstox.py --validate

Usage:
  python scripts/fetch_history_upstox.py --from 2025-07-01 --to 2026-07-18
  python scripts/fetch_history_upstox.py --tickers RELIANCE SBIN --from 2024-01-01
  python scripts/fetch_history_upstox.py --validate   # compare vs Yahoo cache

Rate: ~4 req/s (0.25s delay). 149 tickers x 12 months ~= 1,800 requests ~= 8 min.
"""
import argparse, gzip, json, os, sys, time, urllib.parse, urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT       = Path(__file__).resolve().parent.parent
OUT_DIR    = ROOT / "data" / "history_cache_upstox"
YAHOO_DIR  = ROOT / "data" / "history_cache"
INSTR_FILE = ROOT / "data" / "upstox_instruments.json"
INSTR_URL  = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
API        = "https://api.upstox.com/v3/historical-candle"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36",
}

sys.path.insert(0, str(ROOT / "scripts"))
from fetch_history_yahoo import FULL_UNIVERSE  # single source of truth for the universe


# ── Instruments master (ticker -> NSE_EQ|ISIN instrument_key) ────────────────

def load_instrument_map(refresh=False) -> dict:
    if INSTR_FILE.exists() and not refresh:
        return json.loads(INSTR_FILE.read_text(encoding="utf-8"))
    print("Downloading Upstox NSE instruments master...")
    req = urllib.request.Request(INSTR_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = gzip.decompress(r.read())
    instruments = json.loads(raw)
    m = {}
    for ins in instruments:
        if (ins.get("segment") == "NSE_EQ" and ins.get("instrument_type") == "EQ"):
            m[ins.get("trading_symbol", "")] = ins.get("instrument_key", "")
    INSTR_FILE.write_text(json.dumps(m), encoding="utf-8")
    print(f"  {len(m)} NSE_EQ symbols mapped -> {INSTR_FILE.name}")
    return m


# ── Fetch ────────────────────────────────────────────────────────────────────

def month_chunks(frm: date, to: date):
    """Calendar-month windows [start, end] covering frm..to (API max = 1 month)."""
    chunks, cur = [], frm
    while cur <= to:
        month_end = (cur.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        end = min(month_end, to)
        chunks.append((cur.isoformat(), end.isoformat()))
        cur = end + timedelta(days=1)
    return chunks


def fetch_month(instrument_key: str, frm: str, to: str, retries=3):
    url = f"{API}/{urllib.parse.quote(instrument_key, safe='')}/minutes/5/{to}/{frm}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read())
            candles = d.get("data", {}).get("candles", [])
            bars = []
            for c in candles:  # [ts_iso, o, h, l, c, vol, oi] — newest first
                dt = c[0]
                hhmm = int(dt[11:13]) * 100 + int(dt[14:16])
                if hhmm < 915 or hhmm > 1515:
                    continue
                bars.append({"dt": dt, "open": float(c[1]), "high": float(c[2]),
                             "low": float(c[3]), "close": float(c[4]),
                             "volume": int(c[5])})
            return sorted(bars, key=lambda b: b["dt"])
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(5 * (attempt + 1)); continue
            if attempt == retries - 1:
                print(f"    HTTP {e.code} on {frm}..{to}")
                return []
            time.sleep(2)
        except Exception as e:
            if attempt == retries - 1:
                print(f"    error {e} on {frm}..{to}")
                return []
            time.sleep(2)
    return []


def backfill(tickers, frm: date, to: date, delay: float):
    imap = load_instrument_map()
    chunks = month_chunks(frm, to)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Backfill {len(tickers)} tickers x {len(chunks)} month-chunks "
          f"({frm} -> {to}) ~ {len(tickers)*len(chunks)} requests")
    ok = missing = 0
    for i, t in enumerate(tickers):
        key = imap.get(t)
        if not key:
            print(f"  {t:<14} NO instrument_key — skipped")
            missing += 1
            continue
        f = OUT_DIR / f"{t}_5min_upstox.json"
        existing = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
        merged = {b["dt"]: b for b in existing}
        new_ct = 0
        for frm_s, to_s in chunks:
            bars = fetch_month(key, frm_s, to_s)
            for b in bars:
                if b["dt"] not in merged:
                    new_ct += 1
                merged[b["dt"]] = b
            time.sleep(delay)
        allb = sorted(merged.values(), key=lambda b: b["dt"])
        f.write_text(json.dumps(allb), encoding="utf-8")
        days = len({b["dt"][:10] for b in allb})
        print(f"  [{i+1}/{len(tickers)}] {t:<14} +{new_ct} bars -> {days} days total", flush=True)
        ok += 1
    print(f"Done. ok={ok} missing_key={missing}")


# ── Cross-validation vs Yahoo cache ──────────────────────────────────────────

def validate(tickers, n_days=5):
    """Compare Upstox vs Yahoo bars on the most recent overlapping days."""
    print(f"{'ticker':<12} {'days':>4} {'bars':>5} {'close MAD%':>10} {'max dC%':>8} {'vol ratio':>9}  verdict")
    worst = 0.0
    for t in tickers:
        fu = OUT_DIR / f"{t}_5min_upstox.json"
        fy = YAHOO_DIR / f"{t}_5min_v8.json"
        if not (fu.exists() and fy.exists()):
            print(f"{t:<12} missing file(s)"); continue
        up = {b["dt"][:16]: b for b in json.loads(fu.read_text(encoding="utf-8"))}
        ya = {b["dt"][:16]: b for b in json.loads(fy.read_text(encoding="utf-8"))}
        common_days = sorted({k[:10] for k in up} & {k[:10] for k in ya})[-n_days:]
        keys = [k for k in up if k[:10] in common_days and k in ya]
        if not keys:
            print(f"{t:<12} no overlap"); continue
        dc = [abs(up[k]["close"] - ya[k]["close"]) / ya[k]["close"] * 100 for k in keys]
        vr = [up[k]["volume"] / ya[k]["volume"] for k in keys
              if ya[k]["volume"] > 0 and up[k]["volume"] > 0]
        mad = sum(dc) / len(dc)
        mx = max(dc)
        vmed = sorted(vr)[len(vr)//2] if vr else float("nan")
        verdict = "OK" if mx < 0.25 else ("WARN" if mx < 1.0 else "FAIL")
        worst = max(worst, mx)
        print(f"{t:<12} {len(common_days):>4} {len(keys):>5} {mad:>9.4f}% {mx:>7.3f}% {vmed:>9.2f}  {verdict}")
    print(f"\nworst single-bar close deviation: {worst:.3f}%  "
          f"({'PASS — sources agree' if worst < 1.0 else 'INVESTIGATE'})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", default="2025-07-01")
    ap.add_argument("--to", dest="to", default=date.today().isoformat())
    ap.add_argument("--tickers", nargs="*", default=None)
    ap.add_argument("--delay", type=float, default=0.25)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--refresh-instruments", action="store_true")
    a = ap.parse_args()

    tickers = a.tickers if a.tickers else FULL_UNIVERSE
    if a.refresh_instruments:
        load_instrument_map(refresh=True)
    if a.validate:
        validate(tickers if a.tickers else
                 ["RELIANCE", "SBIN", "TCS", "HDFCBANK", "TATASTEEL",
                  "DIXON", "BEL", "IRFC", "KAYNES", "ABFRL"])
        return
    backfill(tickers, date.fromisoformat(a.frm), date.fromisoformat(a.to), a.delay)


if __name__ == "__main__":
    main()
