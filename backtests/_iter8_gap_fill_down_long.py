#!/usr/bin/env python3
"""Gap Fill Iter 8: Down-Long Only — exact proposal params"""
import sys, io, random, math, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

random.seed(314)

CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_SIZE   = MARGIN * 0.20
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005
DAILY_LOSS_CAP = -300
BARS_PER_DAY   = 75
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


def generate_day_candles_with_gap(base_price, prev_close, regime):
    atr_pct = 0.008 if regime == "trending" else 0.005 if regime == "range" else 0.010
    open_price = base_price
    drift = random.gauss(0, 0.00005) if regime == "range" else random.choice([1, -1]) * 0.0001
    fill_prob = 0.75 if regime == "range" else (0.45 if regime == "trending" else 0.20)
    will_fill = random.random() < fill_prob
    candles = []
    price = open_price
    avg_vol = base_price * 50_000
    for i in range(BARS_PER_DAY):
        vol_factor = 2.0 if i < 3 else (1.4 if i < 10 else (0.9 if i > 60 else 1.0))
        bar_atr = atr_pct * price * vol_factor * random.uniform(0.5, 1.5)
        open_bar = price
        if will_fill and i < 30:
            fill_direction = 1 if prev_close > open_price else -1
            direction = fill_direction if random.random() < 0.65 else -fill_direction
        else:
            direction = 1 if random.random() > 0.5 else -1
        close_bar = price + drift * price + direction * bar_atr * 0.4 * random.random()
        high_bar = max(open_bar, close_bar) + bar_atr * 0.2 * random.random()
        low_bar  = min(open_bar, close_bar) - bar_atr * 0.2 * random.random()
        vol = avg_vol * vol_factor * random.uniform(0.5, 2.5)
        candles.append({
            "i": i, "open": open_bar, "high": high_bar, "low": low_bar,
            "close": close_bar, "vol": vol, "will_fill": will_fill
        })
        price = close_bar
    return candles


def simulate_gap_fill_down_long(ticker, base_price, prev_close, regime):
    # Only gap-downs in 0.4%-1.0% range
    gap_size = (base_price - prev_close) / prev_close
    if gap_size > -0.004 or gap_size < -0.010:
        return []

    candles = generate_day_candles_with_gap(base_price, prev_close, regime)

    # Vol filter: first bar >= 2.0x expected morning volume
    avg_open_vol = base_price * 50_000 * 2.0
    if candles[0]["vol"] < 2.0 * avg_open_vol:
        return []

    # No-fall confirm: skip if first 5 bars ALL show continued decline
    first5 = candles[:5]
    continuing_down = all(c["close"] < c["open"] for c in first5)
    if continuing_down:
        return []

    # Partial fill: price must reach >= 30% of gap distance within first 15 bars
    gap_abs = abs(prev_close - base_price)
    partial_target = base_price + 0.30 * gap_abs
    first15 = candles[:15]
    touched = any(c["high"] >= partial_target for c in first15)
    if not touched:
        return []

    # Enter at bar 5 (after no-fall + partial-fill confirmed)
    entry_idx = 5
    if entry_idx >= len(candles):
        return []

    entry_bar = candles[entry_idx]
    entry_price = entry_bar["open"] * (1 + SLIPPAGE_PCT)
    stop_price  = entry_price * (1 - 0.006)
    target_price = prev_close

    shares = int(MAX_POS_SIZE / entry_price)
    if shares <= 0:
        return []

    for i in range(entry_idx, BARS_PER_DAY):
        bar = candles[i]
        if i >= FLAT_BAR:
            ep = bar["close"] * (1 - SLIPPAGE_PCT)
            pnl = (ep - entry_price) * shares - 2 * COMMISSION_PCT * entry_price * shares
            return [{"exit_reason": "EOD", "pnl": pnl}]
        if bar["low"] <= stop_price:
            pnl = (stop_price - entry_price) * shares - 2 * COMMISSION_PCT * entry_price * shares
            return [{"exit_reason": "SL", "pnl": pnl}]
        if bar["high"] >= target_price:
            pnl = (target_price - entry_price) * shares - 2 * COMMISSION_PCT * entry_price * shares
            return [{"exit_reason": "TP", "pnl": pnl}]
    return []


def main():
    regimes = (["trending"] * 88 + ["range"] * 75 + ["gap_and_go"] * 62 + ["trending"] * 25)
    random.shuffle(regimes)
    all_trades = []
    daily_pnls = []
    ticker_prev_close = {t: TICKER_PRICES[t] for t in NIFTY50_TICKERS}

    for day_idx in range(250):
        regime = regimes[day_idx]
        day_pnl = 0.0
        tickers_today = random.sample(NIFTY50_TICKERS, 10)
        for ticker in tickers_today:
            prev_close = ticker_prev_close[ticker]
            gap_roll = random.gauss(0, 0.008)
            base_price = prev_close * (1 + gap_roll)
            day_trades = simulate_gap_fill_down_long(ticker, base_price, prev_close, regime)
            ticker_prev_close[ticker] = base_price * random.uniform(0.995, 1.005)
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
    print("  Gap Fill Iter 8 — Down-Long Only (proposal params)")
    print("  gap 0.4-1.0% | vol 2x | 5-bar no-fall | 30% partial | stop 0.6%")
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
