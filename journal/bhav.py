"""Read-only access to the local NSE bhavcopy cache (data/bhavcopy/YYYYMMDD.csv).

This is the journal's only market-data source: completed daily bars, local
files, no network. If a date is missing the caller gets fewer bars and must
treat the outcome as incomplete — never estimated.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BHAV_DIR = ROOT / "data" / "bhavcopy"

# NSE UDiFF bhavcopy column names
_COLS = {"open": "OpnPric", "high": "HghPric", "low": "LwPric", "close": "ClsPric"}
_VOL_COL = "TtlTradgVol"


def _file_date_iso(path: Path) -> str:
    s = path.stem
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def available_dates() -> list[str]:
    """Sorted ISO dates for which a bhavcopy file exists."""
    return sorted(_file_date_iso(p) for p in BHAV_DIR.glob("*.csv"))


def latest_date() -> str | None:
    dates = available_dates()
    return dates[-1] if dates else None


def bars_for_symbol(symbol: str, start_iso: str, max_bars: int,
                    include_start: bool = False) -> list[dict]:
    """Daily EQ bars for one symbol from the cache, oldest first.

    start_iso is exclusive unless include_start (intraday recs need the entry
    day's own bar). Stops after max_bars.
    """
    out: list[dict] = []
    for path in sorted(BHAV_DIR.glob("*.csv")):
        d = _file_date_iso(path)
        if d < start_iso or (d == start_iso and not include_start):
            continue
        bar = _row_for_symbol(path, symbol, d)
        if bar:
            out.append(bar)
            if len(out) >= max_bars:
                break
    return out


def _row_for_symbol(path: Path, symbol: str, date_iso: str) -> dict | None:
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("TckrSymb", "").strip().upper() == symbol
                    and row.get("SctySrs", "").strip().upper() == "EQ"):
                try:
                    vol_raw = row.get(_VOL_COL, "")
                    return {
                        "date": date_iso,
                        "open": float(row[_COLS["open"]]),
                        "high": float(row[_COLS["high"]]),
                        "low": float(row[_COLS["low"]]),
                        "close": float(row[_COLS["close"]]),
                        "volume": float(vol_raw) if vol_raw else 0.0,
                    }
                except (KeyError, ValueError):
                    return None
    return None


def load_universe_series(symbols: list[str]) -> dict[str, list[dict]]:
    """Parse every bhavcopy file once; return per-symbol daily series (oldest
    first). Used by backtests where per-symbol file scans would be O(n^2)."""
    want = {s.upper() for s in symbols}
    series: dict[str, list[dict]] = {s: [] for s in want}
    for path in sorted(BHAV_DIR.glob("*.csv")):
        d = _file_date_iso(path)
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sym = row.get("TckrSymb", "").strip().upper()
                if sym in want and row.get("SctySrs", "").strip().upper() == "EQ":
                    try:
                        vol_raw = row.get(_VOL_COL, "")
                        series[sym].append({
                            "date": d,
                            "open": float(row[_COLS["open"]]),
                            "high": float(row[_COLS["high"]]),
                            "low": float(row[_COLS["low"]]),
                            "close": float(row[_COLS["close"]]),
                            "volume": float(vol_raw) if vol_raw else 0.0,
                        })
                    except (KeyError, ValueError):
                        pass
    return series
