#!/usr/bin/env python3
"""
Real-data backtest using NSE bhavcopy (daily OHLCV, free, no auth).
Downloads up to 500 trading days of data for Nifty 50 universe.

Strategies tested on REAL daily data:
  P1 ORB     — NOT testable on daily bars (needs 5-min intraday)
  P2 GapFill — fully testable: gap-down 0.4-1.0%, stop 0.6%, target=prev_close
  P3 BBSq    — fully testable: BB(20,2) squeeze ≥5 days, ATR stop, 2R target

Run: python3 backtests/real_daily_backtest.py
First run downloads bhavcopy files (~500 day's CSV ZIPs). Subsequent runs use cache.
"""
import sys, io, csv, math, statistics, urllib.request, zipfile
from datetime import date, timedelta
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR    = PROJECT_ROOT / "data" / "bhavcopy"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_SIZE   = MARGIN * 0.20
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005
DAILY_LOSS_CAP = -300

BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{date_str}_F_0000.csv.zip"
)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

NIFTY50 = [
    "RELIANCE","HDFCBANK","ICICIBANK","INFY","TCS","SBIN","LT","ITC",
    "AXISBANK","KOTAKBANK","BAJFINANCE","HINDUNILVR","BHARTIARTL","MARUTI",
    "TITAN","ASIANPAINT","WIPRO","SUNPHARMA","NTPC","POWERGRID","ONGC",
    "COALINDIA","TATASTEEL","JSWSTEEL","HINDALCO","TATAMOTORS","ULTRACEMCO",
    "MM","HEROMOTOCO","BAJAJ-AUTO","BRITANNIA","NESTLEIND","CIPLA","DRREDDY",
    "ADANIENT","ADANIPORTS","BPCL","GRASIM","HCLTECH","TECHM","LTIM",
    "EICHERMOT","TATACONSUM","SBILIFE","HDFCLIFE","BAJAJFINSV","DIVISLAB",
    "APOLLOHOSP","BEL","TRENT",
]

# ── Bhavcopy download + parse ─────────────────────────────────────────────────

def _cache_path(d: date) -> Path:
    return CACHE_DIR / f"{d.strftime('%Y%m%d')}.csv"


def _download(d: date) -> bool:
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
        out.write_text(data, encoding="utf-8")
        return True
    except Exception:
        return False


def _read_day(d: date) -> dict:
    """Return {symbol: {open,high,low,close}} for all EQ stocks on date d."""
    path = _cache_path(d)
    if not path.exists():
        return {}
    result = {}
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("SctySrs", "").strip().upper() != "EQ":
                continue
            sym = row.get("TckrSymb", "").strip().upper()
            if not sym:
                continue
            try:
                result[sym] = {
                    "open":  float(row["OpnPric"]),
                    "high":  float(row["HghPric"]),
                    "low":   float(row["LwPric"]),
                    "close": float(row["ClsPric"]),
                    "vol":   float(row.get("TtlTradgVol", 0) or 0),
                }
            except (KeyError, ValueError):
                pass
    return result


def prefetch(n_days: int):
    """Download bhavcopy ZIPs for last n_days trading days (skips already cached)."""
    d = date.today() - timedelta(days=1)
    fetched = 0
    skipped = 0
    total   = n_days + 30  # buffer for weekends + holidays
    tried   = 0
    while fetched < n_days and tried < total:
        if d.weekday() < 5:
            tried += 1
            if _cache_path(d).exists():
                skipped += 1
                fetched += 1
            else:
                ok = _download(d)
                if ok:
                    fetched += 1
                    if fetched % 50 == 0:
                        print(f"  ... {fetched}/{n_days} days downloaded", flush=True)
        d -= timedelta(days=1)
    print(f"  Prefetch done: {fetched} days ({skipped} from cache)")


def load_universe(n_days: int = 500) -> list[tuple[date, dict]]:
    """
    Return list of (date, {sym: ohlcv}) for last n_days trading days, oldest first.
    Downloads any missing bhavcopy files.
    """
    d     = date.today() - timedelta(days=1)
    days  = []
    tried = 0
    while len(days) < n_days and tried < n_days + 100:
        if d.weekday() < 5:
            tried += 1
            if not _cache_path(d).exists():
                _download(d)
            data = _read_day(d)
            if data:
                days.append((d, data))
        d -= timedelta(days=1)
    days.reverse()
    return days


# ── BB helpers ────────────────────────────────────────────────────────────────

def bb(closes: list, period: int = 20, mult: float = 2.0):
    if len(closes) < period:
        c = closes[-1]
        return c * 1.01, c, c * 0.99, c * 0.02
    w = closes[-period:]
    sma = sum(w) / period
    std = statistics.stdev(w) if len(w) >= 2 else w[0] * 0.005
    u = sma + mult * std
    l = sma - mult * std
    return u, sma, l, u - l


def wilder_atr(rows: list, period: int = 14) -> float:
    if len(rows) < 2:
        return rows[-1]["high"] - rows[-1]["low"] if rows else 1.0
    trs = []
    for i in range(1, min(len(rows), period + 1)):
        h, lo, pc = rows[i]["high"], rows[i]["low"], rows[i-1]["close"]
        trs.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return sum(trs) / len(trs) if trs else 1.0


# ── Strategy runners (per ticker across all days) ─────────────────────────────

def run_gap_fill(ticker: str, universe: list) -> list:
    """
    Gap Fill Down-Long on daily bars.
    Rules adapted from proposal:
      - Gap-down 0.4–1.0% (open vs prev_close)
      - Vol filter: today's vol ≥ 2× 20-day avg vol
      - No-fall proxy: today's close > today's open (price recovered intraday)
      - Stop  = open × 0.994
      - Target = prev_close (full gap fill)
      - Win: high ≥ prev_close
      - Loss: low ≤ stop (worst-case ambiguity: if both hit, count as loss)
    """
    trades = []
    vol_history: list[float] = []

    for i, (d, day_data) in enumerate(universe):
        row = day_data.get(ticker)
        if row is None:
            continue
        vol_history.append(row["vol"])
        if len(vol_history) > 20:
            vol_history.pop(0)

        if i == 0:
            continue
        prev_row = None
        for j in range(i - 1, -1, -1):
            pr = universe[j][1].get(ticker)
            if pr:
                prev_row = pr
                break
        if prev_row is None:
            continue

        prev_close = prev_row["close"]
        open_px    = row["open"]
        gap        = (open_px - prev_close) / prev_close

        # Only gap-downs 0.4–1.0%
        if gap > -0.004 or gap < -0.010:
            continue

        # Volume filter: today ≥ 2× 20-day average
        if len(vol_history) >= 5:
            avg_vol = sum(vol_history[-20:]) / len(vol_history[-20:])
            if avg_vol > 0 and row["vol"] < 2.0 * avg_vol:
                continue

        # No-fall proxy: close > open (recovered during day)
        if row["close"] < row["open"]:
            continue

        stop_px   = open_px * 0.994
        target_px = prev_close
        entry_px  = open_px * (1 + SLIPPAGE_PCT)
        shares    = max(1, int(MAX_POS_SIZE / entry_px))

        hit_stop   = row["low"]  <= stop_px
        hit_target = row["high"] >= target_px

        # Worst-case ambiguity: if both hit, count as loss
        if hit_stop:
            pnl = (stop_px - entry_px) * shares - 2 * COMMISSION_PCT * entry_px * shares
            trades.append({"pnl": round(pnl, 2), "exit": "SL", "date": d})
        elif hit_target:
            pnl = (target_px - entry_px) * shares - 2 * COMMISSION_PCT * entry_px * shares
            trades.append({"pnl": round(pnl, 2), "exit": "TP", "date": d})
        else:
            eod_px = row["close"] * (1 - SLIPPAGE_PCT)
            pnl    = (eod_px - entry_px) * shares - 2 * COMMISSION_PCT * entry_px * shares
            trades.append({"pnl": round(pnl, 2), "exit": "EOD", "date": d})

    return trades


def run_bb_squeeze(ticker: str, universe: list) -> list:
    """
    BB Squeeze Breakout on daily bars.
    Rules: BB(20, 2.0) | squeeze ≥5 days compressing | vol 1.8× 20-day avg |
           bar body ≥ 0.5 ATR | stop 1.0 ATR | target 2.0 ATR
    """
    trades = []
    closes_hist: list[float] = []
    rows_hist:   list[dict]  = []
    bb_widths:   list[float] = []
    squeeze_count = 0
    vol_history:  list[float] = []
    in_trade = False
    position: dict = {}

    for i, (d, day_data) in enumerate(universe):
        row = day_data.get(ticker)
        if row is None:
            squeeze_count = 0
            continue

        closes_hist.append(row["close"])
        rows_hist.append(row)
        vol_history.append(row["vol"])
        if len(vol_history) > 20:
            vol_history.pop(0)

        upper, mid, lower, width = bb(closes_hist)
        bb_widths.append(width)

        if len(bb_widths) > 3:
            squeeze_count = squeeze_count + 1 if width < bb_widths[-4] else 0
        else:
            squeeze_count = 0

        # Exit open position
        if in_trade:
            d_type = position["direction"]
            entry  = position["entry"]
            stop   = position["stop"]
            tgt    = position["target"]
            qty    = position["qty"]

            hit_sl = row["low"]  <= stop if d_type == "long" else row["high"] >= stop
            hit_tp = row["high"] >= tgt  if d_type == "long" else row["low"]  <= tgt
            cost   = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2

            if hit_sl:
                pnl = ((stop - entry) if d_type == "long" else (entry - stop)) * qty - cost
                trades.append({"pnl": round(pnl, 2), "exit": "SL", "date": d, "dir": d_type})
                in_trade = False
            elif hit_tp:
                pnl = ((tgt - entry) if d_type == "long" else (entry - tgt)) * qty - cost
                trades.append({"pnl": round(pnl, 2), "exit": "TP", "date": d, "dir": d_type})
                in_trade = False
            # else hold
            continue

        if len(closes_hist) < 22 or squeeze_count < 5:
            continue

        atr  = wilder_atr(rows_hist[-15:])
        body = abs(row["close"] - row["open"])
        avg_vol = sum(vol_history) / len(vol_history) if vol_history else 1
        vol_ok  = row["vol"] >= 1.8 * avg_vol
        body_ok = body >= 0.5 * atr

        # Long breakout
        if row["close"] > upper and vol_ok and body_ok:
            ep  = row["close"] * (1 + SLIPPAGE_PCT)
            qty = max(1, int(MAX_POS_SIZE / ep))
            position = {"direction": "long", "entry": ep,
                        "stop": ep - atr, "target": ep + 2 * atr, "qty": qty}
            in_trade = True

        # Short breakout
        elif row["close"] < lower and vol_ok and body_ok:
            ep  = row["close"] * (1 - SLIPPAGE_PCT)
            qty = max(1, int(MAX_POS_SIZE / ep))
            position = {"direction": "short", "entry": ep,
                        "stop": ep + atr, "target": ep - 2 * atr, "qty": qty}
            in_trade = True

    return trades


# ── Metrics ───────────────────────────────────────────────────────────────────

def metrics(trades: list) -> dict:
    if not trades:
        return {"n": 0, "wr": 0, "pnl": 0, "sharpe": 0, "max_dd": 0,
                "avg_win": 0, "avg_loss": 0, "avg_r": 0,
                "tp": 0, "sl": 0, "eod": 0}
    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    pnls   = [t["pnl"] for t in trades]
    wr     = len(wins) / len(trades) * 100
    total  = sum(pnls)
    avg_w  = statistics.mean(t["pnl"] for t in wins)  if wins   else 0
    avg_l  = statistics.mean(t["pnl"] for t in losses) if losses else 0
    avg_r  = abs(avg_w / avg_l) if avg_l else float("inf")
    sharpe = (statistics.mean(pnls) / statistics.stdev(pnls) * math.sqrt(250)
              if len(pnls) > 1 and statistics.stdev(pnls) > 0 else 0)
    equity = peak = dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak: peak = equity
        if peak - equity > dd: dd = peak - equity
    max_dd = dd / CAPITAL * 100
    return {
        "n": len(trades), "wr": round(wr, 1), "pnl": round(total, 0),
        "avg_win": round(avg_w, 0), "avg_loss": round(avg_l, 0),
        "avg_r": round(avg_r, 2), "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
        "tp":  sum(1 for t in trades if t.get("exit") == "TP"),
        "sl":  sum(1 for t in trades if t.get("exit") == "SL"),
        "eod": sum(1 for t in trades if t.get("exit") == "EOD"),
    }


def print_m(label: str, m: dict):
    if m["n"] == 0:
        print(f"\n  {label}: NO TRADES generated")
        return
    print(f"\n{'='*62}")
    print(f"  {label}")
    print(f"{'='*62}")
    print(f"  Trades    : {m['n']}  (REAL NSE daily data — no synthetic adjustment)")
    print(f"  Win Rate  : {m['wr']:.1f}%")
    print(f"  Avg Win   : Rs{m['avg_win']:.0f}   Avg Loss: Rs{m['avg_loss']:.0f}")
    print(f"  Avg R     : {m['avg_r']:.2f}  {'✅ positive' if m['avg_r'] >= 1.0 else '❌ negative'} expectancy")
    print(f"  Total PnL : Rs{m['pnl']:.0f}  {'✅' if m['pnl'] > 0 else '❌'}")
    print(f"  Max DD    : {m['max_dd']:.2f}%")
    print(f"  Sharpe    : {m['sharpe']:.2f}  {'✅' if m['sharpe'] >= 1.0 else '⚠️' if m['sharpe'] >= 0 else '❌'}")
    print(f"  Exits     : TP={m['tp']}  SL={m['sl']}  EOD={m['eod']}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    N_DAYS = 500  # ~2 years of trading days

    print("=" * 62)
    print("  REAL-DATA BACKTEST — NSE Bhavcopy (Daily OHLCV)")
    print(f"  Universe: {len(NIFTY50)} Nifty 50 stocks | {N_DAYS} trading days")
    print("  Capital: Rs20,000 | MIS 5x | 20% margin/pos")
    print("=" * 62)

    print(f"\nDownloading/verifying {N_DAYS} days of bhavcopy files...")
    prefetch(N_DAYS)

    print("\nLoading universe into memory...", flush=True)
    universe = load_universe(N_DAYS)
    actual_days = len(universe)
    print(f"Loaded {actual_days} trading days")
    if actual_days < 20:
        print("ERROR: Too few days loaded — check internet connection")
        sys.exit(1)

    print(f"\nRunning strategies across {len(NIFTY50)} tickers...")
    gf_all = []
    bb_all = []
    ticker_results = {}

    for ticker in NIFTY50:
        gf_trades = run_gap_fill(ticker, universe)
        bb_trades = run_bb_squeeze(ticker, universe)
        gf_all.extend(gf_trades)
        bb_all.extend(bb_trades)
        if gf_trades or bb_trades:
            ticker_results[ticker] = {"gf": len(gf_trades), "bb": len(bb_trades)}

    print(f"  Tickers with trades: {len(ticker_results)}")

    gm = metrics(gf_all)
    bm = metrics(bb_all)

    print("\n\n" + "=" * 62)
    print("  RESULTS")
    print("=" * 62)
    print("\n  P1: ORB — CANNOT backtest on daily bars (needs 5-min intraday)")
    print("      Synthetic backtest remains the only reference: 89% WR, RW adj 57.9%")
    print_m("P2: Gap Fill Down-Long (daily bars approximation)", gm)
    print_m("P3: BB Squeeze Breakout (daily bars)", bm)

    print("\n\n" + "=" * 62)
    print("  COMPARISON vs SYNTHETIC BACKTEST")
    print("=" * 62)
    print(f"{'Metric':<22} {'P2 GapFill (synth)':>20} {'P2 GapFill (REAL)':>20}")
    print(f"  {'Trades':<20} {'106':>20} {str(gm['n']):>20}")
    print(f"  {'Win Rate %':<20} {'51.9':>20} {str(gm['wr']):>20}")
    print(f"  {'Total PnL Rs':<20} {'-374':>20} {str(gm['pnl']):>20}")
    print(f"  {'Sharpe':<20} {'-0.32':>20} {str(gm['sharpe']):>20}")
    print(f"  {'Max DD %':<20} {'9.14':>20} {str(gm['max_dd']):>20}")

    print(f"\n{'Metric':<22} {'P3 BBSq (synth)':>20} {'P3 BBSq (REAL)':>20}")
    print(f"  {'Trades':<20} {'36':>20} {str(bm['n']):>20}")
    print(f"  {'Win Rate %':<20} {'77.8':>20} {str(bm['wr']):>20}")
    print(f"  {'Total PnL Rs':<20} {'1277':>20} {str(bm['pnl']):>20}")
    print(f"  {'Sharpe':<20} {'3.69':>20} {str(bm['sharpe']):>20}")
    print(f"  {'Max DD %':<20} {'0.43':>20} {str(bm['max_dd']):>20}")

    print("\n" + "=" * 62)
    print("  VERDICT")
    print("=" * 62)

    for name, m in [("P2 Gap Fill", gm), ("P3 BB Squeeze", bm)]:
        if m["n"] == 0:
            verdict = "INCONCLUSIVE (no trades)"
        elif m["pnl"] > 0 and m["wr"] >= 55 and m["avg_r"] >= 1.0:
            verdict = "CONFIRMED — real data supports the strategy"
        elif m["pnl"] > 0 and m["wr"] >= 50:
            verdict = "MARGINAL — positive but weak edge on real data"
        elif m["pnl"] <= 0:
            verdict = "REJECTED — negative PnL on real data"
        else:
            verdict = "CAUTION — mixed signals"
        print(f"  {name}: {verdict}")

    print()


if __name__ == "__main__":
    main()
