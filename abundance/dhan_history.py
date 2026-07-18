"""Dhan daily-history source (READ-ONLY market data; no order endpoints).

Why: NSE bhavcopy needs ~260 ZIP downloads for a year; Dhan's
POST /v2/charts/historical returns a full year per symbol in one call, and can
also serve the real NIFTY index + India VIX for the regime snapshot.

Requires DHAN_ACCESS_TOKEN + DHAN_CLIENT_ID (env or repo-root .env, read-only).
Without credentials this module degrades gracefully: prints one clear line and
exits 0 so callers fall back to bhavcopy — no crash, no fake data.

Usage:
  python -m abundance.dhan_history fetch [--days 400]

Cache: data/dhan_daily/<SYMBOL>.json  (+ _NIFTY.json, _INDIAVIX.json)
Endpoints used (documented per Platform Req 4):
  https://api.dhan.co/v2/charts/historical      (daily OHLCV)
  https://images.dhan.co/api-data/api-scrip-master.csv  (securityId lookup)
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import NIFTY50, PROJECT_ROOT
from .notify import _env

BASE = "https://api.dhan.co"
DHAN_DAILY_DIR = PROJECT_ROOT / "data" / "dhan_daily"
SECURITIES_JSON = PROJECT_ROOT / "data" / "nse_securities.json"
EXTRA_IDS_JSON = PROJECT_ROOT / "data" / "dhan_securityids.json"
SCRIP_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"

INDICES = {  # securityIds from data/nse_securities.json NSE_INDEX block
    "_NIFTY": {"securityId": "13", "exchangeSegment": "IDX_I", "instrument": "INDEX"},
    "_INDIAVIX": {"securityId": "26017", "exchangeSegment": "IDX_I", "instrument": "INDEX"},
}


def _headers() -> dict | None:
    token, client = _env("DHAN_ACCESS_TOKEN"), _env("DHAN_CLIENT_ID")
    if not token or not client:
        return None
    return {"access-token": token, "client-id": client,
            "Content-Type": "application/json", "Accept": "application/json"}


def _known_ids() -> dict[str, str]:
    ids: dict[str, str] = {}
    if SECURITIES_JSON.exists():
        d = json.loads(SECURITIES_JSON.read_text(encoding="utf-8"))
        for sym, info in d.get("NSE_EQ", {}).items():
            ids[sym] = str(info["securityId"])
    if EXTRA_IDS_JSON.exists():
        ids.update(json.loads(EXTRA_IDS_JSON.read_text(encoding="utf-8")))
    return ids


def _resolve_missing(symbols: list[str], ids: dict[str, str]) -> dict[str, str]:
    """Fill missing securityIds from the public scrip master CSV. Additions are
    cached in data/dhan_securityids.json (nse_securities.json is human-managed
    and never modified here)."""
    missing = [s for s in symbols if s not in ids]
    if not missing:
        return ids
    try:
        req = urllib.request.Request(SCRIP_MASTER_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"scrip master unavailable ({type(e).__name__}) — proceeding with "
              f"{len(ids)} known ids; missing: {', '.join(missing[:8])}...")
        return ids
    found: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(text)):
        # Column names per Dhan scrip master: SEM_TRADING_SYMBOL, SEM_SMST_SECURITY_ID,
        # SEM_EXM_EXCH_ID (NSE), SEM_SEGMENT / SEM_INSTRUMENT_NAME (EQUITY series EQ)
        if row.get("SEM_EXM_EXCH_ID", "").strip() != "NSE":
            continue
        if row.get("SEM_INSTRUMENT_NAME", "").strip() != "EQUITY":
            continue
        sym = row.get("SEM_TRADING_SYMBOL", "").strip().upper()
        if sym in missing and sym not in found:
            found[sym] = str(row.get("SEM_SMST_SECURITY_ID", "")).strip()
    if found:
        EXTRA_IDS_JSON.write_text(json.dumps(found, indent=2), encoding="utf-8")
        ids.update(found)
        print(f"resolved {len(found)} securityIds via scrip master (cached).")
    still = [s for s in symbols if s not in ids]
    if still:
        print(f"unresolved symbols (skipped, not guessed): {', '.join(still)}")
    return ids


def _fetch_one(headers: dict, security_id: str, segment: str, instrument: str,
               d_from: str, d_to: str) -> list[dict] | None:
    body = json.dumps({"securityId": security_id, "exchangeSegment": segment,
                       "instrument": instrument, "expiryCode": 0,
                       "fromDate": d_from, "toDate": d_to}).encode()
    req = urllib.request.Request(f"{BASE}/v2/charts/historical", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode())
    except Exception:
        return None
    if not isinstance(d, dict) or "open" not in d or not d.get("open"):
        return None
    bars = []
    for i in range(len(d["open"])):
        ts = d.get("timestamp", [None] * len(d["open"]))[i]
        if ts is None:
            continue
        # Epoch → IST calendar date explicitly, so results don't depend on the
        # machine's local timezone setting.
        ist = timezone(timedelta(hours=5, minutes=30))
        day = datetime.fromtimestamp(ts, tz=ist).date().isoformat()
        bars.append({"date": day, "open": d["open"][i], "high": d["high"][i],
                     "low": d["low"][i], "close": d["close"][i],
                     "volume": (d.get("volume") or [0] * len(d["open"]))[i]})
    return bars or None


def fetch(days: int = 400) -> int:
    headers = _headers()
    if headers is None:
        print("dhan_history: DHAN_ACCESS_TOKEN / DHAN_CLIENT_ID not set — "
              "skipping Dhan fetch (bhavcopy fallback will be used).")
        return 0
    d_to = date.today().isoformat()
    d_from = (date.today() - timedelta(days=days)).isoformat()
    ids = _resolve_missing(NIFTY50, _known_ids())
    DHAN_DAILY_DIR.mkdir(parents=True, exist_ok=True)
    ok = 0
    targets = [(s, {"securityId": ids[s], "exchangeSegment": "NSE_EQ",
                    "instrument": "EQUITY"}) for s in NIFTY50 if s in ids]
    targets += list(INDICES.items())
    for name, meta in targets:
        bars = _fetch_one(headers, meta["securityId"], meta["exchangeSegment"],
                          meta["instrument"], d_from, d_to)
        if bars:
            (DHAN_DAILY_DIR / f"{name}.json").write_text(
                json.dumps(bars), encoding="utf-8")
            ok += 1
        else:
            print(f"  {name}: no data returned (skipped — never fabricated)")
        time.sleep(0.6)  # stay far below Dhan rate limits
    print(f"dhan_history: cached {ok}/{len(targets)} series → {DHAN_DAILY_DIR}")
    return ok


def load_daily() -> dict[str, list[dict]]:
    """{symbol: bars} for equities from the Dhan cache (indices excluded)."""
    out: dict[str, list[dict]] = {}
    if not DHAN_DAILY_DIR.exists():
        return out
    for p in sorted(DHAN_DAILY_DIR.glob("*.json")):
        if p.stem.startswith("_"):
            continue
        try:
            bars = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if bars:
            out[p.stem] = bars
    return out


def load_index(name: str = "_NIFTY") -> list[dict] | None:
    p = DHAN_DAILY_DIR / f"{name}.json"
    if not p.exists():
        return None
    try:
        bars = json.loads(p.read_text(encoding="utf-8"))
        return bars or None
    except (json.JSONDecodeError, OSError):
        return None


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd")
    f = sub.add_parser("fetch")
    f.add_argument("--days", type=int, default=400)
    a = ap.parse_args()
    if a.cmd == "fetch":
        fetch(a.days)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
