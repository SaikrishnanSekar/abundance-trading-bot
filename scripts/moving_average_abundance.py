#!/usr/bin/env python3
"""
Moving Average Abundance scanner.

Research-only screen for the current India APPROVED-WATCHLIST symbols.
Uses Kotak Neo for live LTP/VIX and local completed-day bhavcopy cache for
20/200-day moving average context.

No orders are placed. This does not alter the active ORB strategy.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import _kotak  # noqa: E402
from journal.selection import classify, sma  # noqa: E402 — shared with backtests
from journal.record import journal_safely, log_ma_abundance  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
WATCHLIST = ROOT / "memory" / "india" / "APPROVED-WATCHLIST.md"
BHAV_DIR = ROOT / "data" / "bhavcopy"
OUT_FILE = ROOT / "memory" / "india" / "MOVING-AVERAGE-ABUNDANCE-SCAN.md"


@dataclass
class Bar:
    date: str
    close: float


def parse_watchlist_symbols() -> list[str]:
    text = WATCHLIST.read_text(encoding="utf-8")
    matches = re.findall(r"^- ([A-Z0-9&-]+) \(ORB,", text, flags=re.MULTILINE)
    seen: set[str] = set()
    symbols: list[str] = []
    for sym in matches:
        if sym not in seen:
            seen.add(sym)
            symbols.append(sym)
    return symbols


def row_close_for_symbol(path: Path, symbol: str) -> Bar | None:
    day = f"{path.stem[:4]}-{path.stem[4:6]}-{path.stem[6:8]}"
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (
                row.get("TckrSymb", "").strip().upper() == symbol
                and row.get("SctySrs", "").strip().upper() == "EQ"
            ):
                try:
                    return Bar(date=day, close=float(row["ClsPric"]))
                except (KeyError, ValueError):
                    return None
    return None


def completed_daily_bars(symbol: str, limit: int = 220) -> list[Bar]:
    files = sorted(BHAV_DIR.glob("*.csv"), key=lambda p: p.name, reverse=True)
    rows: list[Bar] = []
    for path in files:
        row = row_close_for_symbol(path, symbol)
        if row:
            rows.append(row)
            if len(rows) >= limit:
                break
    rows.reverse()
    return rows


def fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "NA"
    return f"{value:.{digits}f}"


def extract_quote_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        data = raw.get("data", raw)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("list", "quotes", "data"):
                val = data.get(key)
                if isinstance(val, list):
                    return [x for x in val if isinstance(x, dict)]
            return [data]
    return []


def item_ltp(item: dict[str, Any]) -> float | None:
    for key in ("ltp", "last_price", "LastTradePrice", "lastPrice", "lastTradedPrice"):
        val = item.get(key)
        if val not in (None, "", "0", 0):
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
    return None


def item_token(item: dict[str, Any]) -> str | None:
    for key in ("instrument_token", "pSymbol", "token", "tk", "exchange_token"):
        val = item.get(key)
        if val not in (None, ""):
            return str(val)
    return None


def kotak_quotes(symbols: list[str]) -> tuple[dict[str, float], list[str]]:
    creds = _kotak._load_env()
    client = _kotak._get_client(creds)
    master = _kotak._get_master(creds["consumer_key"])

    resolved: list[tuple[str, str]] = []
    failed: list[str] = []
    for sym in symbols:
        token = master.get(sym) or master.get(sym + "-EQ")
        if token:
            resolved.append((sym, str(token)))
        else:
            failed.append(sym)

    prices: dict[str, float] = {}
    for i in range(0, len(resolved), 40):
        chunk = resolved[i : i + 40]
        tokens = [
            {"instrument_token": token, "exchange_segment": "nse_cm"}
            for _, token in chunk
        ]
        raw = client.quotes(instrument_tokens=tokens, quote_type="ltp")
        items = extract_quote_items(raw)
        by_token: dict[str, float] = {}
        for item in items:
            token = item_token(item)
            ltp = item_ltp(item)
            if token and ltp:
                by_token[token] = ltp

        if by_token:
            for sym, token in chunk:
                if token in by_token:
                    prices[sym] = by_token[token]
                else:
                    failed.append(sym)
        else:
            for (sym, _token), item in zip(chunk, items):
                ltp = item_ltp(item)
                if ltp:
                    prices[sym] = ltp
                else:
                    failed.append(sym)

    return prices, failed


def run_scan() -> str:
    symbols = parse_watchlist_symbols()
    if not symbols:
        raise RuntimeError("No symbols found in APPROVED-WATCHLIST.md")

    now = datetime.now(IST)
    prices, quote_failed = kotak_quotes(symbols)

    rows: list[dict[str, Any]] = []
    for sym in symbols:
        bars = completed_daily_bars(sym, 220)
        closes = [b.close for b in bars]
        ltp = prices.get(sym)
        if ltp is None:
            rows.append({"symbol": sym, "status": "DATA-FAIL", "note": "Kotak LTP missing"})
            continue
        if len(closes) < 201:
            rows.append({"symbol": sym, "status": "DATA-FAIL", "note": f"only {len(closes)} daily bars"})
            continue

        sma20_now = sma(closes[-20:], 20)
        sma20_prev = sma(closes[-21:-1], 20)
        sma200 = sma(closes[-200:], 200)
        if sma20_now is None or sma20_prev is None or sma200 is None:
            rows.append({"symbol": sym, "status": "DATA-FAIL", "note": "SMA calc failed"})
            continue

        last_hist_close = closes[-1]
        if sma200 / last_hist_close > 2.5 or sma200 / last_hist_close < 0.4:
            rows.append(
                {
                    "symbol": sym,
                    "ltp": ltp,
                    "sma20": sma20_now,
                    "sma200": sma200,
                    "dist20": (ltp - sma20_now) / sma20_now * 100,
                    "dist200": (ltp - sma200) / sma200 * 100,
                    "last_hist": bars[-1].date,
                    "status": "DATA-ANOMALY",
                    "note": "200DMA distorted by unadjusted history/corporate action",
                }
            )
            continue

        status, note = classify(ltp, sma20_now, sma20_prev, sma200)
        rows.append(
            {
                "symbol": sym,
                "ltp": ltp,
                "sma20": sma20_now,
                "sma200": sma200,
                "dist20": (ltp - sma20_now) / sma20_now * 100,
                "dist200": (ltp - sma200) / sma200 * 100,
                "last_hist": bars[-1].date,
                "status": status,
                "note": note,
            }
        )

    priority = {
        "LONG-WATCH": 0,
        "SHORT-WATCH": 1,
        "BASE-BUILD": 2,
        "BLOCKED-200": 3,
        "EXTENDED-LONG": 4,
        "EXTENDED-SHORT": 5,
        "NO-SETUP": 6,
        "DATA-ANOMALY": 8,
        "DATA-FAIL": 9,
    }
    rows.sort(key=lambda r: (priority.get(r["status"], 8), symbols.index(r["symbol"])))

    lines = [
        "# Moving Average Abundance Scan - India",
        "",
        f"Generated: {now.strftime('%Y-%m-%d %H:%M:%S')} IST",
        "Mode: RESEARCH ONLY - no order authority",
        "Live data: Kotak Neo LTP",
        "Historical context: local completed-day bhavcopy cache",
        "",
        "Rules:",
        "- Long-watch: live price > rising 20DMA and <= 3% above 20DMA; 200DMA not blocking overhead.",
        "- Short-watch: live price < falling 20DMA and <= 3% below 20DMA; 200DMA not blocking below.",
        "- Extended: aligned with 20DMA trend but more than 3% away from 20DMA.",
        "- Blocked-200: 200DMA is within 3% against the trade direction.",
        "",
    ]
    latest_hist = max(
        (str(r.get("last_hist")) for r in rows if r.get("last_hist")),
        default="NA",
    )
    lines.append(f"Latest completed historical bar in cache: {latest_hist}")
    lines.append("")

    if quote_failed:
        lines.append(f"Kotak quote failures: {', '.join(sorted(set(quote_failed)))}")
        lines.append("")

    lines += [
        "| Symbol | Status | LTP | 20DMA | 200DMA | Dist20 | Dist200 | Last hist | Note |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        if r["status"] == "DATA-FAIL":
            lines.append(f"| {r['symbol']} | {r['status']} | NA | NA | NA | NA | NA | NA | {r['note']} |")
        else:
            lines.append(
                f"| {r['symbol']} | {r['status']} | {fmt(r['ltp'])} | {fmt(r['sma20'])} | "
                f"{fmt(r['sma200'])} | {r['dist20']:.2f}% | {r['dist200']:.2f}% | "
                f"{r['last_hist']} | {r['note']} |"
            )

    summary: dict[str, int] = {}
    for r in rows:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    lines += ["", "Summary:"]
    for key in sorted(summary, key=lambda k: priority.get(k, 8)):
        lines.append(f"- {key}: {summary[key]}")

    output = "\n".join(lines) + "\n"
    OUT_FILE.write_text(output, encoding="utf-8")

    # Journal every actionable recommendation at generation time (append-only;
    # deterministic ids make re-runs idempotent; failures never break the scan).
    for r in rows:
        if r["status"] in ("LONG-WATCH", "SHORT-WATCH"):
            rec_id = journal_safely(log_ma_abundance, r, now)
            if rec_id:
                print(f"[journal] recorded {rec_id}")

    return output


if __name__ == "__main__":
    print(run_scan())
