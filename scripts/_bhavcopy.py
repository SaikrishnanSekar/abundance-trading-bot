#!/usr/bin/env python3
"""
NSE Bhavcopy — daily OHLCV cache and ATR calculator.

Downloads NSE CM bhavcopy ZIPs (free, no auth) from nsearchives.nseindia.com.
Each file covers all ~3 400 NSE CM instruments for one trading day.
Cache lives in  data/bhavcopy/<YYYYMMDD>.csv  relative to the project root.

Usage:
  python3 scripts/_bhavcopy.py atr     SYMBOL [DAYS]   → float (Wilder ATR-14)
  python3 scripts/_bhavcopy.py history SYMBOL [DAYS]   → JSON {open,high,low,close}
  python3 scripts/_bhavcopy.py quote   SYMBOL          → float (last close price)
  python3 scripts/_bhavcopy.py prefetch [DAYS]         → download N days of files
"""
import csv
import io
import json
import sys
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR    = PROJECT_ROOT / "data" / "bhavcopy"

BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


# ── helpers ──────────────────────────────────────────────────────────────────

def _cache_path(d: date) -> Path:
    return CACHE_DIR / f"{d.strftime('%Y%m%d')}.csv"


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5


def _download(d: date) -> bool:
    """Fetch and cache bhavcopy for date d. Returns True if successful."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = _cache_path(d)
    if out.exists():
        return True

    url = BHAVCOPY_URL.format(date_str=d.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
    except Exception:
        return False  # holiday or not yet published

    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            if not csv_names:
                return False
            csv_data = zf.read(csv_names[0]).decode("utf-8", errors="replace")
    except Exception:
        return False

    tmp = out.with_suffix(".tmp")
    tmp.write_text(csv_data, encoding="utf-8")
    tmp.replace(out)
    return True


def _extract(d: date, symbol: str) -> dict | None:
    """Return {open,high,low,close} for symbol+EQ from cached file, or None."""
    path = _cache_path(d)
    if not path.exists():
        return None

    sym = symbol.strip().upper()
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("TckrSymb", "").strip().upper() == sym
                    and row.get("SctySrs", "").strip().upper() == "EQ"):
                try:
                    return {
                        "open":  float(row["OpnPric"]),
                        "high":  float(row["HghPric"]),
                        "low":   float(row["LwPric"]),
                        "close": float(row["ClsPric"]),
                        "date":  d.isoformat(),
                    }
                except (KeyError, ValueError):
                    return None
    return None


def _fetch_rows(symbol: str, trading_days: int) -> list[dict]:
    """
    Return up to trading_days dicts [{open,high,low,close,date}], oldest first.
    Downloads any missing bhavcopy files on the fly.
    """
    needed = trading_days + 15  # extra buffer for holidays
    rows = []

    # Start from yesterday (today's file not published until ~17:30 IST)
    d = date.today() - timedelta(days=1)
    tried = 0
    while len(rows) < trading_days and tried < needed:
        if _is_weekday(d):
            tried += 1
            if not _cache_path(d).exists():
                _download(d)
            row = _extract(d, symbol)
            if row:
                rows.append(row)
        d -= timedelta(days=1)

    rows.reverse()  # oldest → newest
    return rows


# ── Wilder ATR ────────────────────────────────────────────────────────────────

def _wilder_atr(rows: list[dict], period: int = 14) -> float | None:
    if len(rows) < period + 1:
        return None
    trs = []
    for i in range(1, len(rows)):
        h, lo, prev_c = rows[i]["high"], rows[i]["low"], rows[i - 1]["close"]
        trs.append(max(h - lo, abs(h - prev_c), abs(lo - prev_c)))
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return round(atr, 4)


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: _bhavcopy.py {atr|history|quote|prefetch} SYMBOL [DAYS]",
              file=sys.stderr)
        sys.exit(1)

    subcmd = sys.argv[1]

    if subcmd == "prefetch":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        needed = days + 15
        d = date.today() - timedelta(days=1)
        fetched = 0
        while fetched < needed:
            if _is_weekday(d):
                ok = _download(d)
                status = "ok" if ok else "skip"
                print(f"  {d} {status}", file=sys.stderr)
                fetched += 1
            d -= timedelta(days=1)
        return

    if len(sys.argv) < 3:
        print(f"_bhavcopy.py: {subcmd} requires SYMBOL", file=sys.stderr)
        sys.exit(1)

    symbol = sys.argv[2]
    days   = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    if subcmd == "atr":
        rows = _fetch_rows(symbol, max(days, 20))
        if len(rows) < 15:
            print(f"_bhavcopy.py: only {len(rows)} rows for {symbol}",
                  file=sys.stderr)
            sys.exit(1)
        val = _wilder_atr(rows)
        if val is None:
            print("NA", file=sys.stderr)
            sys.exit(1)
        print(val)

    elif subcmd == "history":
        rows = _fetch_rows(symbol, days)
        if not rows:
            print(f"_bhavcopy.py: no data for {symbol}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps({
            "open":  [r["open"]  for r in rows],
            "high":  [r["high"]  for r in rows],
            "low":   [r["low"]   for r in rows],
            "close": [r["close"] for r in rows],
        }))

    elif subcmd == "quote":
        # Return the most recent close as an LTP proxy (useful outside market hours)
        rows = _fetch_rows(symbol, 1)
        if not rows:
            print(f"_bhavcopy.py: no data for {symbol}", file=sys.stderr)
            sys.exit(1)
        print(rows[-1]["close"])

    else:
        print(f"_bhavcopy.py: unknown subcommand: {subcmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
