"""Daily OHLCV loading. Two sources, both real NSE data, never synthetic:

1. NSE bhavcopy archive (free, no auth) — primary source on the user's machine.
2. data/history_cache/*_5min_v8.json — real Dhan 5-min candles aggregated to
   daily bars. Fallback when bhavcopy is unreachable (e.g. sandboxed CI).

If neither source has data the caller gets an empty structure and must say so —
gaps are NEVER filled with assumptions (Hard Rule 5).
"""
from __future__ import annotations

import csv
import io
import json
import sys
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

from .config import BHAVCOPY_DIR, CACHE_5MIN_DIR

BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

Bar = dict  # {"date": "YYYY-MM-DD", "open","high","low","close","volume": float}


# ── bhavcopy source ──────────────────────────────────────────────────────────

def _cache_path(d: date) -> Path:
    return BHAVCOPY_DIR / f"{d.strftime('%Y%m%d')}.csv"


def download_day(d: date) -> bool:
    """Fetch and cache one bhavcopy. False on any failure (holiday/offline)."""
    BHAVCOPY_DIR.mkdir(parents=True, exist_ok=True)
    out = _cache_path(d)
    if out.exists():
        return True
    url = BHAVCOPY_URL.format(date_str=d.strftime("%Y%m%d"))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if n.endswith(".csv")]
            if not names:
                return False
            data = zf.read(names[0]).decode("utf-8", errors="replace")
    except Exception:
        return False
    tmp = out.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(out)  # atomic-ish; avoids half-written cache on Windows
    return True


def prefetch(n_trading_days: int, progress: bool = True) -> int:
    """Download the last n trading days of bhavcopy files. Returns count cached."""
    d = date.today() - timedelta(days=1)
    got, tried = 0, 0
    while got < n_trading_days and tried < n_trading_days * 2 + 40:
        if d.weekday() < 5:
            tried += 1
            if download_day(d):
                got += 1
                if progress and got % 25 == 0:
                    print(f"  bhavcopy: {got}/{n_trading_days} days", flush=True)
        d -= timedelta(days=1)
    return got


def _read_bhavcopy_day(d: date, symbols: set[str]) -> dict[str, Bar]:
    path = _cache_path(d)
    if not path.exists():
        return {}
    out: dict[str, Bar] = {}
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = row.get("TckrSymb", "").strip().upper()
            if sym not in symbols or row.get("SctySrs", "").strip().upper() != "EQ":
                continue
            try:
                out[sym] = {
                    "date": d.isoformat(),
                    "open": float(row["OpnPric"]), "high": float(row["HghPric"]),
                    "low": float(row["LwPric"]), "close": float(row["ClsPric"]),
                    "volume": float(row.get("TtlTradgVol", 0) or 0),
                }
            except (KeyError, ValueError):
                pass
    return out


def load_bhavcopy_series(symbols: list[str], n_trading_days: int) -> dict[str, list[Bar]]:
    """{symbol: [bars oldest→newest]} from local bhavcopy cache (no download)."""
    series: dict[str, list[Bar]] = {s: [] for s in symbols}
    symset = set(symbols)
    days = sorted(p.stem for p in BHAVCOPY_DIR.glob("*.csv")) if BHAVCOPY_DIR.exists() else []
    for stem in days[-n_trading_days:]:
        d = date(int(stem[:4]), int(stem[4:6]), int(stem[6:8]))
        for sym, bar in _read_bhavcopy_day(d, symset).items():
            series[sym].append(bar)
    return {s: b for s, b in series.items() if b}


# ── 5-min cache fallback ─────────────────────────────────────────────────────

def load_5min_cache_daily() -> dict[str, list[Bar]]:
    """Aggregate real 5-min candles (data/history_cache) into daily bars."""
    series: dict[str, list[Bar]] = {}
    if not CACHE_5MIN_DIR.exists():
        return series
    for path in sorted(CACHE_5MIN_DIR.glob("*_5min_v8.json")):
        sym = path.name.split("_5min_")[0]
        try:
            candles = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        by_day: dict[str, list[dict]] = {}
        for c in candles:
            by_day.setdefault(c["dt"][:10], []).append(c)
        bars = []
        for day in sorted(by_day):
            cs = by_day[day]
            bars.append({
                "date": day,
                "open": cs[0]["open"],
                "high": max(c["high"] for c in cs),
                "low": min(c["low"] for c in cs),
                "close": cs[-1]["close"],
                "volume": sum(c.get("volume", 0) for c in cs),
            })
        if bars:
            series[sym] = bars
    return series


def load_best_available(symbols: list[str], n_trading_days: int = 260) -> tuple[dict[str, list[Bar]], str]:
    """Source priority: Dhan daily cache (deepest, includes real index) →
    bhavcopy → 5-min cache. Returns (series, source)."""
    from .dhan_history import load_daily  # local import avoids cycle
    dhan = load_daily()
    if dhan and max(len(b) for b in dhan.values()) >= 30:
        return ({s: b[-n_trading_days:] for s, b in dhan.items() if s in symbols} or dhan,
                "dhan_daily")
    series = load_bhavcopy_series(symbols, n_trading_days)
    # Require a real span, not a stray file or two
    if series and max(len(b) for b in series.values()) >= 30:
        return series, "bhavcopy"
    fallback = load_5min_cache_daily()
    if fallback:
        return fallback, "history_cache_5min"
    return {}, "none"


def print_utf8_safe():
    """Windows cmd defaults to cp1252 — force UTF-8 stdout so ₹/arrows print."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
