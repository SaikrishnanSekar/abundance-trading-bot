#!/usr/bin/env python3
"""
Real-data backtest — 3 proposals vs actual NSE 5-min OHLCV (yfinance).
Covers last ~60 trading days for 15 liquid Nifty 50 tickers.

Run: python3 backtests/real_data_backtest.py
"""
import sys, io, math, statistics, json, time
from datetime import datetime, timedelta, date
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    print("ERROR: pip install yfinance pandas")
    sys.exit(1)

CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_SIZE   = MARGIN * 0.20
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005
DAILY_LOSS_CAP = -300
CACHE_DIR      = Path(__file__).parent.parent / "data" / "history_cache"

TICKERS = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
    "SBIN", "AXISBANK", "BHARTIARTL", "WIPRO", "TATASTEEL",
    "TATAMOTORS", "ONGC", "NTPC", "COALINDIA", "BAJFINANCE",
]

YF_SUFFIX = ".NS"
IST_OFFSET = timedelta(hours=5, minutes=30)


# ── Data fetch + cache ─────────────────────────────────────────────────────────

def fetch_5min(ticker: str, days: int = 58) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{ticker}_5min.parquet"
    today = date.today()

    if cache_file.exists():
        age_hours = (datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)).total_seconds() / 3600
        if age_hours < 12:
            return pd.read_parquet(cache_file)

    sym = ticker + YF_SUFFIX
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(10 * attempt)
            tkr = yf.Ticker(sym)
            df  = tkr.history(period=f"{days}d", interval="5m", auto_adjust=True)
            break
        except Exception as e:
            if attempt == 2:
                print(f"  [WARN] {ticker}: download failed after 3 attempts: {e}", file=sys.stderr)
                return pd.DataFrame()
            time.sleep(5)

    if df.empty:
        return df

    # Flatten multi-level columns if present (download() returns MultiIndex)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns=str.lower)
    # Drop extra columns from Ticker.history()
    df = df[[c for c in df.columns if c in {"open", "high", "low", "close", "volume"}]]

    required = {"open", "high", "low", "close", "volume"}
    if not required.issubset(df.columns):
        print(f"  [WARN] {ticker}: missing columns {required - set(df.columns)}", file=sys.stderr)
        return pd.DataFrame()

    # Ensure IST timezone
    if df.index.tzinfo is None:
        df.index = df.index.tz_localize("UTC").tz_convert("Asia/Kolkata")
    elif str(df.index.tzinfo) != "Asia/Kolkata":
        df.index = df.index.tz_convert("Asia/Kolkata")

    # Keep only NSE market hours 09:15 – 15:15
    df = df.between_time("09:15", "15:15")
    df = df[df["volume"] > 0].copy()
    df.to_parquet(cache_file)
    return df


def split_by_day(df: pd.DataFrame) -> list:
    """Return list of per-day DataFrames sorted by date."""
    if df.empty:
        return []
    days = []
    for d, grp in df.groupby(df.index.date):
        grp = grp.sort_index()
        if len(grp) >= 20:  # skip days with too few bars
            days.append(grp)
    return days


# ── Strategy 1: ORB ────────────────────────────────────────────────────────────

def run_orb_day(day_df: pd.DataFrame) -> dict | None:
    """15-min range (first 3 bars), vol 1.5×, 0.1% buf, 2× range target."""
    bars = day_df.reset_index()
    if len(bars) < 10:
        return None

    orh = bars["high"].iloc[:3].max()
    orl = bars["low"].iloc[:3].min()
    orb_width = orh - orl
    if orb_width <= 0:
        return None

    long_entry_px  = orh * 1.001
    short_entry_px = orl * 0.999
    vol_avgs = bars["volume"].rolling(20, min_periods=1).mean()
    flat_bar = len(bars) - 4  # ~15:10

    for i in range(3, len(bars)):
        bar = bars.iloc[i]
        t = bar.name if isinstance(bar.name, int) else i
        if i >= flat_bar:
            break
        # time gate: entries only 09:30–13:00
        ts = bar["Datetime"] if "Datetime" in bars.columns else day_df.index[i]
        try:
            h = ts.hour if hasattr(ts, "hour") else 0
            m = ts.minute if hasattr(ts, "minute") else 0
            if h < 9 or (h == 9 and m < 30) or h > 13:
                continue
        except Exception:
            pass

        vol_ok = bar["volume"] > 1.5 * vol_avgs.iloc[i]

        # Long
        if bar["close"] > long_entry_px and vol_ok:
            entry  = long_entry_px
            stop   = orl
            target = entry + 2.0 * orb_width
            entry  *= (1 + SLIPPAGE_PCT)
            qty    = max(1, int(MAX_POS_SIZE / entry))
            for j in range(i + 1, len(bars)):
                fb = bars.iloc[j]
                if j >= flat_bar:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (fb["open"] * (1 - SLIPPAGE_PCT) - entry) * qty - cost
                    return {"dir": "L", "pnl": round(pnl, 2), "exit": "EOD"}
                if fb["low"] <= stop:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (stop - entry) * qty - cost
                    return {"dir": "L", "pnl": round(pnl, 2), "exit": "SL"}
                if fb["high"] >= target:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (target - entry) * qty - cost
                    return {"dir": "L", "pnl": round(pnl, 2), "exit": "TP"}
            return None

        # Short
        if bar["close"] < short_entry_px and vol_ok:
            entry  = short_entry_px
            stop   = orh
            target = entry - 2.0 * orb_width
            entry  *= (1 - SLIPPAGE_PCT)
            qty    = max(1, int(MAX_POS_SIZE / entry))
            for j in range(i + 1, len(bars)):
                fb = bars.iloc[j]
                if j >= flat_bar:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (entry - fb["open"] * (1 + SLIPPAGE_PCT)) * qty - cost
                    return {"dir": "S", "pnl": round(pnl, 2), "exit": "EOD"}
                if fb["high"] >= stop:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (entry - stop) * qty - cost
                    return {"dir": "S", "pnl": round(pnl, 2), "exit": "SL"}
                if fb["low"] <= target:
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    pnl  = (entry - target) * qty - cost
                    return {"dir": "S", "pnl": round(pnl, 2), "exit": "TP"}
            return None
    return None


# ── Strategy 2: Gap Fill Down-Long ────────────────────────────────────────────

def run_gap_fill_day(day_df: pd.DataFrame, prev_close: float) -> dict | None:
    """Gap-down 0.4–1.0%, vol 2×, 5-bar no-fall, 30% partial-fill, stop 0.6%."""
    bars = day_df.reset_index()
    if len(bars) < 20 or prev_close <= 0:
        return None

    open_price = float(bars["open"].iloc[0])
    gap = (open_price - prev_close) / prev_close

    if gap > -0.004 or gap < -0.010:
        return None

    avg_open_vol = float(bars["volume"].iloc[:10].mean()) * 2.0
    if float(bars["volume"].iloc[0]) < 2.0 * avg_open_vol:
        return None

    # No-fall confirm: skip if first 5 bars all close below open (continuing decline)
    first5 = bars.iloc[:5]
    if all(first5["close"].values < first5["open"].values):
        return None

    # Partial fill: price must touch >= 30% of gap within first 15 bars
    gap_abs = abs(prev_close - open_price)
    partial_target = open_price + 0.30 * gap_abs
    first15 = bars.iloc[:15]
    if not any(first15["high"] >= partial_target):
        return None

    entry_idx = 5
    if entry_idx >= len(bars):
        return None

    entry_price = float(bars["open"].iloc[entry_idx]) * (1 + SLIPPAGE_PCT)
    stop_price  = entry_price * 0.994
    target_price = prev_close
    qty = max(1, int(MAX_POS_SIZE / entry_price))
    flat_bar = len(bars) - 4

    for j in range(entry_idx, len(bars)):
        fb = bars.iloc[j]
        if j >= flat_bar:
            cost = entry_price * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
            pnl  = (float(fb["close"]) * (1 - SLIPPAGE_PCT) - entry_price) * qty - cost
            return {"pnl": round(pnl, 2), "exit": "EOD"}
        if float(fb["low"]) <= stop_price:
            cost = entry_price * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
            pnl  = (stop_price - entry_price) * qty - cost
            return {"pnl": round(pnl, 2), "exit": "SL"}
        if float(fb["high"]) >= target_price:
            cost = entry_price * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
            pnl  = (target_price - entry_price) * qty - cost
            return {"pnl": round(pnl, 2), "exit": "TP"}
    return None


# ── Strategy 3: BB Squeeze ────────────────────────────────────────────────────

def compute_bb(closes: list, period: int = 20, mult: float = 2.0):
    if len(closes) < period:
        c = closes[-1]
        return c * 1.01, c, c * 0.99, c * 0.02
    w = closes[-period:]
    sma = sum(w) / period
    std = statistics.stdev(w) if len(w) >= 2 else w[0] * 0.005
    upper = sma + mult * std
    lower = sma - mult * std
    return upper, sma, lower, upper - lower


def compute_atr_bars(bars, period: int = 14) -> float:
    trs = []
    for i in range(1, min(len(bars), period + 1)):
        h = float(bars["high"].iloc[i])
        l = float(bars["low"].iloc[i])
        pc = float(bars["close"].iloc[i - 1])
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs) / len(trs) if trs else 1.0


def run_bb_squeeze_day(day_df: pd.DataFrame) -> dict | None:
    """BB(20,2) squeeze ≥5 bars, vol 1.8×, body ≥ 0.5 ATR, ATR stop, 2× R target."""
    bars = day_df.reset_index()
    if len(bars) < 25:
        return None

    closes_hist = []
    bb_widths   = []
    squeeze_count = 0
    vols = bars["volume"].tolist()
    avg_vol = sum(vols[:20]) / 20 if len(vols) >= 20 else sum(vols) / len(vols)
    position = None
    ENTRY_START  = 21
    ENTRY_CUTOFF = 48
    FLAT_BAR     = len(bars) - 4
    long_taken = short_taken = False

    for i in range(len(bars)):
        bar = bars.iloc[i]
        closes_hist.append(float(bar["close"]))
        upper, mid, lower, width = compute_bb(closes_hist)
        bb_widths.append(width)

        if len(bb_widths) > 3:
            squeeze_count = squeeze_count + 1 if width < bb_widths[-4] else 0
        else:
            squeeze_count = 0

        # Exit
        if position is not None:
            d     = position["direction"]
            entry = position["entry"]
            stop  = position["stop"]
            tgt   = position["target"]
            qty   = position["qty"]
            if i >= FLAT_BAR:
                cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                ep   = float(bar["close"]) * (1 + (-SLIPPAGE_PCT if d == "long" else SLIPPAGE_PCT))
                pnl  = ((ep - entry) if d == "long" else (entry - ep)) * qty - cost
                return {"pnl": round(pnl, 2), "exit": "EOD", "dir": d}
            hit_sl = float(bar["low"]) <= stop if d == "long" else float(bar["high"]) >= stop
            hit_tp = float(bar["high"]) >= tgt  if d == "long" else float(bar["low"])  <= tgt
            if hit_sl:
                cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                pnl  = ((stop - entry) if d == "long" else (entry - stop)) * qty - cost
                return {"pnl": round(pnl, 2), "exit": "SL", "dir": d}
            if hit_tp:
                cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                pnl  = ((tgt - entry) if d == "long" else (entry - tgt)) * qty - cost
                return {"pnl": round(pnl, 2), "exit": "TP", "dir": d}
            continue

        if i < ENTRY_START or i > ENTRY_CUTOFF:
            continue
        if squeeze_count < 5:
            continue

        atr  = compute_atr_bars(bars.iloc[:i + 1])
        body = abs(float(bar["close"]) - float(bar["open"]))
        vol_ok   = float(bar["volume"]) >= 1.8 * avg_vol
        body_ok  = body >= 0.5 * atr

        # Long breakout
        if not long_taken and float(bar["close"]) > upper and vol_ok and body_ok:
            ep  = float(bar["close"]) * (1 + SLIPPAGE_PCT)
            qty = max(1, int(MAX_POS_SIZE / ep))
            position = {"direction": "long", "entry": ep,
                        "stop": ep - atr, "target": ep + 2 * atr, "qty": qty}
            long_taken = True

        # Short breakout
        elif not short_taken and position is None and float(bar["close"]) < lower and vol_ok and body_ok:
            ep  = float(bar["close"]) * (1 - SLIPPAGE_PCT)
            qty = max(1, int(MAX_POS_SIZE / ep))
            position = {"direction": "short", "entry": ep,
                        "stop": ep + atr, "target": ep - 2 * atr, "qty": qty}
            short_taken = True

    return None


# ── Runner ────────────────────────────────────────────────────────────────────

def run_strategy(name: str, ticker: str, days: list, strategy_fn, extra_arg=None) -> list:
    trades = []
    day_pnl = 0.0
    for i, day_df in enumerate(days):
        if extra_arg == "gap":
            # pass prev close
            if i == 0:
                continue
            prev_df = days[i - 1]
            prev_close = float(prev_df["close"].iloc[-1])
            result = strategy_fn(day_df, prev_close)
        else:
            result = strategy_fn(day_df)

        if result is not None:
            day_pnl += result["pnl"]
            if day_pnl <= DAILY_LOSS_CAP:
                break
            trades.append({**result, "ticker": ticker, "day": i})
    return trades


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
    # Sharpe on per-trade PnL series (annualized assuming 250 trading days)
    if len(pnls) > 1 and statistics.stdev(pnls) > 0:
        sharpe = statistics.mean(pnls) / statistics.stdev(pnls) * math.sqrt(250)
    else:
        sharpe = 0.0
    # Max drawdown on cumulative equity
    equity = peak = dd_abs = 0.0
    for p in pnls:
        equity += p
        if equity > peak: peak = equity
        dd = peak - equity
        if dd > dd_abs: dd_abs = dd
    max_dd = dd_abs / CAPITAL * 100
    return {
        "n": len(trades), "wr": round(wr, 1), "pnl": round(total, 0),
        "avg_win": round(avg_w, 0), "avg_loss": round(avg_l, 0),
        "avg_r": round(avg_r, 2), "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
        "tp":  sum(1 for t in trades if t.get("exit") == "TP"),
        "sl":  sum(1 for t in trades if t.get("exit") == "SL"),
        "eod": sum(1 for t in trades if t.get("exit") == "EOD"),
    }


def print_metrics(label: str, m: dict):
    if m["n"] == 0:
        print(f"\n  {label}: NO TRADES")
        return
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(f"  Trades    : {m['n']}")
    print(f"  Win Rate  : {m['wr']:.1f}%  (real data — no discount needed)")
    print(f"  Avg Win   : Rs{m['avg_win']:.0f}   Avg Loss: Rs{m['avg_loss']:.0f}")
    print(f"  Avg R     : {m['avg_r']:.2f}")
    print(f"  Total PnL : Rs{m['pnl']:.0f}")
    print(f"  Max DD    : {m['max_dd']:.2f}%")
    print(f"  Sharpe    : {m['sharpe']:.2f}")
    print(f"  Exits     : TP={m['tp']}  SL={m['sl']}  EOD={m['eod']}")


def main():
    print("=" * 60)
    print("REAL-DATA BACKTEST — NSE 5-min via yfinance")
    print(f"Tickers: {len(TICKERS)} | Coverage: last ~58 trading days")
    print("Capital: Rs20,000 | MIS 5x | 20% margin/pos")
    print("=" * 60)

    orb_all  = []
    gf_all   = []
    bb_all   = []

    for idx, ticker in enumerate(TICKERS):
        if idx > 0:
            time.sleep(4)  # avoid yfinance rate limit
        print(f"\n  Fetching {ticker}...", end="", flush=True)
        df = fetch_5min(ticker)
        if df.empty:
            print(" SKIP (no data)")
            continue
        days = split_by_day(df)
        print(f" {len(days)} trading days", flush=True)

        # ORB
        for day_df in days:
            r = run_orb_day(day_df)
            if r:
                orb_all.append({**r, "ticker": ticker})

        # Gap Fill Down-Long
        for i in range(1, len(days)):
            prev_close = float(days[i - 1]["close"].iloc[-1])
            r = run_gap_fill_day(days[i], prev_close)
            if r:
                gf_all.append({**r, "ticker": ticker})

        # BB Squeeze
        for day_df in days:
            r = run_bb_squeeze_day(day_df)
            if r:
                bb_all.append({**r, "ticker": ticker})

    print("\n\n" + "=" * 60)
    print("RESULTS — REAL NSE 5-min DATA")
    print("=" * 60)

    om = metrics(orb_all)
    gm = metrics(gf_all)
    bm = metrics(bb_all)

    print_metrics("P1: ORB (15min, vol 1.5x, 2x target)", om)
    print_metrics("P2: Gap Fill Down-Long (0.4-1.0%, vol 2x, 5-bar, 30% partial, stop 0.6%)", gm)
    print_metrics("P3: BB Squeeze (bb20, sq5, vol 1.8x, body 0.5 ATR)", bm)

    print("\n\n" + "=" * 60)
    print("COMPARISON TABLE")
    print("=" * 60)
    print(f"{'Metric':<22} {'P1 ORB':>12} {'P2 GapFill':>12} {'P3 BBSq':>12}")
    print("-" * 60)
    rows = [
        ("Trades",     om['n'],      gm['n'],      bm['n']),
        ("Win Rate %", om['wr'],     gm['wr'],     bm['wr']),
        ("Avg Win Rs", om['avg_win'],gm['avg_win'],bm['avg_win']),
        ("Avg Loss Rs",om['avg_loss'],gm['avg_loss'],bm['avg_loss']),
        ("Avg R",      om['avg_r'],  gm['avg_r'],  bm['avg_r']),
        ("Total PnL",  om['pnl'],    gm['pnl'],    bm['pnl']),
        ("Max DD %",   om['max_dd'], gm['max_dd'], bm['max_dd']),
        ("Sharpe",     om['sharpe'], gm['sharpe'], bm['sharpe']),
    ]
    for row in rows:
        print(f"  {row[0]:<20} {str(row[1]):>12} {str(row[2]):>12} {str(row[3]):>12}")

    # Rankings
    scores = {"P1 ORB": 0, "P2 GapFill": 0, "P3 BBSq": 0}
    pairs = [("P1 ORB", om), ("P2 GapFill", gm), ("P3 BBSq", bm)]
    for metric in ("wr", "pnl", "sharpe", "avg_r"):
        ranked = sorted(pairs, key=lambda x: x[1].get(metric, 0) if x[1]["n"] > 0 else -9999, reverse=True)
        for pos, (name, _) in enumerate(ranked):
            scores[name] += [3, 2, 1][pos]
    for metric in ("max_dd",):
        ranked = sorted(pairs, key=lambda x: x[1].get(metric, 999) if x[1]["n"] > 0 else 999)
        for pos, (name, _) in enumerate(ranked):
            scores[name] += [3, 2, 1][pos]

    print(f"\n  Ranking (WR + PnL + Sharpe + AvgR + DD): ", end="")
    rank = sorted(scores.items(), key=lambda x: -x[1])
    print(" > ".join(f"{n}({s}pts)" for n, s in rank))

    print("\nDone. Real-data results saved (no synthetic adjustments needed).\n")


if __name__ == "__main__":
    main()
