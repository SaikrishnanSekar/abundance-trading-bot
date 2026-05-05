#!/usr/bin/env python3
"""BB Squeeze: exact proposed config — bb(20,2.0), sq_min=5, vol 1.8x, body 0.5 ATR"""
import sys, io, random, math, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

random.seed(919)

CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_SIZE   = MARGIN * 0.20
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005
DAILY_LOSS_CAP = -300
BARS_PER_DAY   = 75
ENTRY_START    = 21
ENTRY_CUTOFF   = 48
FLAT_BAR       = 72

NIFTY50_TICKERS = [
    "RELIANCE","HDFCBANK","ICICIBANK","INFY","TCS","SBIN","LT","ITC",
    "AXISBANK","KOTAKBANK","BAJFINANCE","HINDUNILVR","BHARTIARTL","MARUTI",
    "TITAN","ASIANPAINT","WIPRO","SUNPHARMA","NTPC","POWERGRID","ONGC",
    "COALINDIA","TATASTEEL","JSWSTEEL","HINDALCO","TATAMOTORS","ULTRACEMCO",
    "MM","HEROMOTOCO","BAJAJ_AUTO","BRITANNIA","NESTLEIND","CIPLA","DRREDDY",
    "ADANIENT","ADANIPORTS","BPCL","GRASIM","HCLTECH","TECHM","LTIM",
    "EICHERMOT","TATACONSUM","SBILIFE","HDFCLIFE","BAJAJFINSV","DIVISLAB",
    "APOLLOHOSP","BEL","TRENT"
]

TICKER_PRICES = {
    "RELIANCE":1420,"HDFCBANK":1720,"ICICIBANK":1290,"INFY":1650,"TCS":3800,
    "SBIN":820,"LT":3620,"ITC":465,"AXISBANK":1180,"KOTAKBANK":1960,
    "BAJFINANCE":7100,"HINDUNILVR":2440,"BHARTIARTL":1720,"MARUTI":12800,
    "TITAN":3300,"ASIANPAINT":2380,"WIPRO":280,"SUNPHARMA":1780,"NTPC":360,
    "POWERGRID":320,"ONGC":270,"COALINDIA":430,"TATASTEEL":160,"JSWSTEEL":870,
    "HINDALCO":640,"TATAMOTORS":730,"ULTRACEMCO":11200,"MM":2980,
    "HEROMOTOCO":5100,"BAJAJ_AUTO":8900,"BRITANNIA":5400,"NESTLEIND":2230,
    "CIPLA":1500,"DRREDDY":1320,"ADANIENT":2300,"ADANIPORTS":1300,"BPCL":310,
    "GRASIM":2780,"HCLTECH":1680,"TECHM":1680,"LTIM":4600,"EICHERMOT":5600,
    "TATACONSUM":1090,"SBILIFE":1680,"HDFCLIFE":760,"BAJAJFINSV":1920,
    "DIVISLAB":5400,"APOLLOHOSP":7200,"BEL":290,"TRENT":5700
}


def generate_day_candles(base_price, regime):
    gap_pct = random.gauss(0, 0.003)
    price = base_price * (1 + gap_pct)
    drift = random.choice([0.0002, -0.0002]) if regime == "trending" else random.gauss(0, 0.00003)
    has_squeeze = (regime in ("trending", "gap_and_go")) and random.random() < 0.55
    squeeze_end = random.randint(15, 35) if has_squeeze else 999
    burst_dir = random.choice([1, -1]) if has_squeeze else 0
    avg_vol = base_price * 50_000
    candles = []
    for i in range(BARS_PER_DAY):
        vf = 1.8 if i < 3 else (1.1 if i < 18 else (0.8 if i > 60 else 1.0))
        base_atr = 0.004 if (has_squeeze and i < squeeze_end) else 0.008
        base_atr *= base_price * vf * random.uniform(0.4, 1.4)
        ob = price
        if has_squeeze and i == squeeze_end:
            d = burst_dir
            scale = 3.0 * random.uniform(1.0, 2.0)
        elif has_squeeze and i > squeeze_end and i < squeeze_end + 5:
            d = burst_dir
            scale = 1.5
        else:
            d = 1 if random.random() > 0.5 else -1
            scale = 1.0
        cb = price + drift * price + d * base_atr * 0.45 * scale * random.random()
        hb = max(ob, cb) + base_atr * 0.2 * random.random()
        lb = min(ob, cb) - base_atr * 0.2 * random.random()
        vol_mult = 3.0 if (has_squeeze and abs(i - squeeze_end) <= 1) else 1.0
        vol = avg_vol * vf * vol_mult * random.uniform(0.5, 2.0)
        candles.append({"i": i, "open": ob, "high": hb, "low": lb, "close": cb, "vol": vol,
                        "is_burst": has_squeeze and abs(i - squeeze_end) <= 1})
        price = cb
    return candles


def compute_bb(closes, period=20, mult=2.0):
    if len(closes) < period:
        c = closes[-1]
        return c * 1.01, c, c * 0.99, c * 0.02
    w = closes[-period:]
    sma = sum(w) / period
    std = statistics.stdev(w) if len(w) >= 2 else w[0] * 0.005
    upper = sma + mult * std
    lower = sma - mult * std
    return upper, sma, lower, upper - lower


def compute_atr(candles, period=14):
    if len(candles) < 2:
        return candles[-1]["high"] - candles[-1]["low"] if candles else 1.0
    trs = []
    for i in range(1, min(len(candles), period + 1)):
        c = candles[i]
        p = candles[i - 1]
        tr = max(c["high"] - c["low"], abs(c["high"] - p["close"]), abs(c["low"] - p["close"]))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 1.0


def simulate_day_bb_squeeze_proposed(ticker, base_price, regime):
    # Proposed: bb(20,2.0), sq_min=5, vol 1.8x, body 0.5 ATR, ATR stop 1.0, target 2.0R
    candles = generate_day_candles(base_price, regime)
    bb_period   = 20
    bb_mult     = 2.0
    squeeze_min = 5
    stop_atr_m  = 1.0
    target_r    = 2.0
    vol_thresh  = 1.8

    vols = [c["vol"] for c in candles]
    avg_vol = sum(vols[:20]) / 20 if len(vols) >= 20 else sum(vols) / len(vols)

    trades = []
    long_taken = False
    short_taken = False
    position = None
    closes_hist = []
    bb_widths = []
    squeeze_count = 0

    for i, bar in enumerate(candles):
        closes_hist.append(bar["close"])
        upper, mid, lower, width = compute_bb(closes_hist, bb_period, bb_mult)
        bb_widths.append(width)

        if len(bb_widths) > 3:
            if width < bb_widths[-4]:
                squeeze_count += 1
            else:
                squeeze_count = 0
        else:
            squeeze_count = 0

        if position is not None:
            direction = position["direction"]
            entry = position["entry"]
            stop  = position["stop"]
            target = position["target"]
            if i >= FLAT_BAR:
                ep = bar["close"] * (1 + (-SLIPPAGE_PCT if direction == "long" else SLIPPAGE_PCT))
                pnl = ((ep - entry) if direction == "long" else (entry - ep)) * int(MAX_POS_SIZE / entry) - 2 * COMMISSION_PCT * entry * int(MAX_POS_SIZE / entry)
                trades.append({"exit_reason": "EOD", "pnl": pnl, "direction": direction})
                position = None
            else:
                hit_stop = bar["low"] <= stop if direction == "long" else bar["high"] >= stop
                hit_tp   = bar["high"] >= target if direction == "long" else bar["low"] <= target
                if hit_stop:
                    pnl = ((stop - entry) if direction == "long" else (entry - stop)) * int(MAX_POS_SIZE / entry) - 2 * COMMISSION_PCT * entry * int(MAX_POS_SIZE / entry)
                    trades.append({"exit_reason": "SL", "pnl": pnl, "direction": direction})
                    position = None
                elif hit_tp:
                    pnl = ((target - entry) if direction == "long" else (entry - target)) * int(MAX_POS_SIZE / entry) - 2 * COMMISSION_PCT * entry * int(MAX_POS_SIZE / entry)
                    trades.append({"exit_reason": "TP", "pnl": pnl, "direction": direction})
                    position = None
            continue

        if i < ENTRY_START or i > ENTRY_CUTOFF:
            continue
        if squeeze_count < squeeze_min:
            continue

        atr = compute_atr(candles[:i + 1])
        bar_body = abs(bar["close"] - bar["open"])

        # Long breakout
        if not long_taken and bar["close"] > upper:
            if bar["vol"] >= vol_thresh * avg_vol and bar_body >= 0.5 * atr:
                entry_price  = bar["close"] * (1 + SLIPPAGE_PCT)
                stop_price   = entry_price - stop_atr_m * atr
                target_price = entry_price + target_r * stop_atr_m * atr
                position = {"direction": "long", "entry": entry_price, "stop": stop_price, "target": target_price}
                long_taken = True

        # Short breakout
        elif not short_taken and position is None and bar["close"] < lower:
            if bar["vol"] >= vol_thresh * avg_vol and bar_body >= 0.5 * atr:
                entry_price  = bar["close"] * (1 - SLIPPAGE_PCT)
                stop_price   = entry_price + stop_atr_m * atr
                target_price = entry_price - target_r * stop_atr_m * atr
                position = {"direction": "short", "entry": entry_price, "stop": stop_price, "target": target_price}
                short_taken = True

    return trades


def main():
    regimes = (["trending"] * 88 + ["range"] * 75 + ["gap_and_go"] * 62 + ["trending"] * 25)
    random.shuffle(regimes)
    all_trades = []
    daily_pnls = []

    for day_idx in range(250):
        regime = regimes[day_idx]
        day_pnl = 0.0
        tickers_today = random.sample(NIFTY50_TICKERS, 10)
        for ticker in tickers_today:
            base = TICKER_PRICES[ticker] * random.uniform(0.88, 1.12)
            day_trades = simulate_day_bb_squeeze_proposed(ticker, base, regime)
            for t in day_trades:
                all_trades.append(t)
                day_pnl += t["pnl"]
                if day_pnl <= DAILY_LOSS_CAP:
                    break
            if day_pnl <= DAILY_LOSS_CAP:
                break
        daily_pnls.append(day_pnl)

    if not all_trades:
        print("No trades generated")
        return

    wins   = [t for t in all_trades if t["pnl"] > 0]
    losses = [t for t in all_trades if t["pnl"] <= 0]
    total  = len(all_trades)
    win_rate  = len(wins) / total * 100
    total_pnl = sum(t["pnl"] for t in all_trades)
    avg_win   = statistics.mean(t["pnl"] for t in wins) if wins else 0
    avg_loss  = statistics.mean(t["pnl"] for t in losses) if losses else 0
    avg_r     = abs(avg_win / avg_loss) if avg_loss else float("inf")
    std_daily = statistics.stdev(daily_pnls)
    sharpe    = (statistics.mean(daily_pnls) / std_daily * math.sqrt(252)) if std_daily > 0 else 0

    equity = peak = max_dd_abs = 0.0
    for dp in daily_pnls:
        equity += dp
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd_abs:
            max_dd_abs = dd
    max_dd_pct = (max_dd_abs / CAPITAL) * 100

    tp  = sum(1 for t in all_trades if t["exit_reason"] == "TP")
    sl  = sum(1 for t in all_trades if t["exit_reason"] == "SL")
    eod = sum(1 for t in all_trades if t["exit_reason"] == "EOD")

    print("=" * 60)
    print("  BB Squeeze — Proposed Config")
    print("  bb(20,2.0) | sq_min=5 | vol 1.8x | body 0.5 ATR | R=2.0")
    print("=" * 60)
    print(f"  Trades   : {total}")
    print(f"  Win Rate : {win_rate:.1f}%")
    print(f"  RW adj WR: {win_rate * 0.65:.1f}%  (synth x 0.65 discount)")
    print(f"  Avg Win  : Rs{avg_win:.0f}   Avg Loss: Rs{avg_loss:.0f}")
    print(f"  Avg R    : {avg_r:.2f}")
    print(f"  Total PnL: Rs{total_pnl:.0f}")
    print(f"  Max DD   : {max_dd_pct:.2f}%")
    print(f"  Sharpe   : {sharpe:.2f}")
    print(f"  Exits    : TP={tp}  SL={sl}  EOD={eod}")


main()
