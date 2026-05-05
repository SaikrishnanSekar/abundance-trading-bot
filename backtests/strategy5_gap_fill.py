#!/usr/bin/env python3
"""
Strategy 5: Gap Fill Mean Reversion — NSE Intraday
===================================================
Source: QuantifiedStrategies.com — "Gap Fill Trading Strategies 2025 – Analyzing
        Opening Gaps [Backtest]" (shared widely on Twitter/X).
        URL: https://www.quantifiedstrategies.com/gap-fill-trading-strategies/
        Also: TrueData India blog "Gap up and gap down intraday trading strategy"
        URL: https://www.truedata.in/blog/Gap-up-and-gap-down-intraday-trading-strategy
        Community: Medium/@FMZQuant "Dynamic Gap-Fill Mean Reversion Strategy"
        URL: https://medium.com/@FMZQuant/dynamic-gap-fill-mean-reversion-strategy-trend-volume-filters-2f41a9b3bcc1

Published claim: "Small gaps (< 1%) fill intraday ~65–70% of the time on NSE equities.
                  Gap fill strategies consistently outperform on liquid large-caps."

Strategy Rules (Base — Iteration 1):
  - Timeframe  : 5-min candles, NSE 09:15–15:15 IST
  - Gap detection: today's open vs yesterday's close
  - Gap-Down trade (fade the gap DOWN): if open < prev_close × (1 - gap_min)
    AND open > prev_close × (1 - gap_max) → BUY at 09:15 open
    Target: prev_close (gap fill level)
    Stop: open × (1 - stop_pct) — initial stop below open
  - Gap-Up trade (fade the gap UP): if open > prev_close × (1 + gap_min)
    AND open < prev_close × (1 + gap_max) → SHORT at 09:15 open
    Target: prev_close (gap fill level)
    Stop: open × (1 + stop_pct)
  - Gap range: 0.3% – 2.0% (avoids overnight news bombs; targets mean-reversion only)
  - Volume confirmation: first 5-bar volume > 1.5× 20-day avg first-bar volume (approx)
  - Direction filter: none in Iter 1 (both gap-up shorts AND gap-down longs)
  - Time filter: enter at open only; no new entries after 10:00; flat by 15:10
  - Max 1 trade per ticker per day

Iteration 2: Narrow gap range to 0.4% – 1.5%; add 5-bar confirmation (don't enter if
             first 5 bars all go in gap direction — likely trending not filling)
Iteration 3: Add trend alignment filter (gap-down long only if prev-day close > 5d EMA)
Iteration 4: Add volume filter (day's opening bar vol > 1.5x average)
Iteration 5: Further narrow gap to 0.5% – 1.2% + require partial fill within first 15 bars

Backtest methodology:
  Same synthetic framework. ₹20k cash, MIS 5×, 250 days × 50 tickers.
"""

import random
import math
import statistics
from typing import List, Dict, Optional

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


def generate_day_candles_with_gap(base_price: float, prev_close: float,
                                   regime: str) -> List[Dict]:
    """Generate candles where first candle open = forced gap level."""
    atr_pct = 0.008 if regime == "trending" else 0.005 if regime == "range" else 0.010
    open_price = base_price  # base_price IS the gapped open for gap days
    drift = random.gauss(0, 0.00005) if regime == "range" else random.choice([1,-1]) * 0.0001

    # Gap fill probability: range-bound=75%, trending=45%, gap_and_go=20%
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
            # Bias toward fill direction
            fill_direction = 1 if prev_close > open_price else -1
            direction = fill_direction if random.random() < 0.65 else -fill_direction
        else:
            direction = 1 if random.random() > 0.5 else -1

        close_bar = price + drift * price + direction * bar_atr * 0.4 * random.random()
        high_bar = max(open_bar, close_bar) + bar_atr * 0.2 * random.random()
        low_bar  = min(open_bar, close_bar) - bar_atr * 0.2 * random.random()
        vol = avg_vol * vol_factor * random.uniform(0.5, 2.5)

        candles.append({'i': i, 'open': open_bar, 'high': high_bar,
                        'low': low_bar, 'close': close_bar, 'vol': vol,
                        'will_fill': will_fill})
        price = close_bar

    return candles


def compute_5d_ema(price_history: List[float], period: int = 25) -> float:
    """Approximate 5-day EMA using recent close history (5d × ~5 bars = 25 bars)."""
    if len(price_history) < period:
        return price_history[-1] if price_history else 0
    k = 2.0 / (period + 1)
    ema = sum(price_history[:period]) / period
    for p in price_history[period:]:
        ema = p * k + ema * (1 - k)
    return ema


def simulate_day_gap_fill(ticker: str, base_price: float, prev_close: float,
                           regime: str, params: Dict,
                           price_history: List[float]) -> List[Dict]:
    gap_min = params.get('gap_min', 0.003)
    gap_max = params.get('gap_max', 0.020)
    stop_pct = params.get('stop_pct', 0.010)
    vol_filter = params.get('vol_filter', False)
    direction_filter = params.get('direction_filter', False)
    confirm_bars = params.get('confirm_bars', 0)  # 0 = immediate entry
    partial_fill_req = params.get('partial_fill_req', False)

    gap_size = (base_price - prev_close) / prev_close  # positive = gap up
    abs_gap = abs(gap_size)

    # Check if gap is in the target range
    if abs_gap < gap_min or abs_gap > gap_max:
        return []

    is_gap_up = gap_size > 0
    trade_direction = 'short' if is_gap_up else 'long'  # fade the gap

    # Direction filter: only fade gaps aligned with trend reversal
    if direction_filter and price_history:
        ema5d = compute_5d_ema(price_history)
        if trade_direction == 'long' and prev_close < ema5d:
            return []  # gap-down but already in downtrend — skip
        if trade_direction == 'short' and prev_close > ema5d:
            return []  # gap-up but already in uptrend — skip

    candles = generate_day_candles_with_gap(base_price, prev_close, regime)

    # Volume filter: first bar volume vs average
    avg_open_vol = base_price * 50_000 * 2.0  # morning vol is typically 2× avg
    if vol_filter and candles[0]['vol'] < 1.5 * avg_open_vol:
        return []

    # Confirmation: check first N bars don't continue gap direction
    if confirm_bars > 0 and len(candles) >= confirm_bars:
        first_n = candles[:confirm_bars]
        if is_gap_up:
            continuing = all(c['close'] > c['open'] for c in first_n)
        else:
            continuing = all(c['close'] < c['open'] for c in first_n)
        if continuing:
            return []  # trending, not filling

    # Partial fill requirement: price must touch at least 30% of gap within first 15 bars
    if partial_fill_req:
        gap_abs = abs(prev_close - base_price)
        partial_target = base_price + 0.3 * gap_abs * (1 if not is_gap_up else -1)
        first_15 = candles[:15]
        touched = any((c['high'] >= partial_target if not is_gap_up else c['low'] <= partial_target)
                      for c in first_15)
        if not touched:
            return []

    # Enter at open of bar `confirm_bars` (or bar 0 if no confirmation)
    entry_idx = confirm_bars if confirm_bars > 0 else 0
    if entry_idx >= len(candles):
        return []

    entry_bar = candles[entry_idx]
    if trade_direction == 'long':
        entry_price = entry_bar['open'] * (1 + SLIPPAGE_PCT)
        stop_price  = entry_price * (1 - stop_pct)
        target_price = prev_close  # gap fill target
    else:
        entry_price = entry_bar['open'] * (1 - SLIPPAGE_PCT)
        stop_price  = entry_price * (1 + stop_pct)
        target_price = prev_close  # gap fill target

    shares = int(MAX_POS_SIZE / entry_price)
    if shares <= 0:
        return []

    # Simulate trade through remaining bars
    for i in range(entry_idx, BARS_PER_DAY):
        bar = candles[i]

        if i >= FLAT_BAR:
            exit_price = bar['close'] * (1 + (-SLIPPAGE_PCT if trade_direction == 'long' else SLIPPAGE_PCT))
            pnl = ((exit_price - entry_price) if trade_direction == 'long'
                   else (entry_price - exit_price)) * shares - 2 * COMMISSION_PCT * entry_price * shares
            return [{'exit_reason': 'EOD', 'pnl': pnl, 'direction': trade_direction}]

        hit_stop = (bar['low'] <= stop_price if trade_direction == 'long'
                    else bar['high'] >= stop_price)
        hit_target = (bar['high'] >= target_price if trade_direction == 'long'
                      else bar['low'] <= target_price)

        if hit_stop:
            pnl = ((stop_price - entry_price) if trade_direction == 'long'
                   else (entry_price - stop_price)) * shares - 2 * COMMISSION_PCT * entry_price * shares
            return [{'exit_reason': 'SL', 'pnl': pnl, 'direction': trade_direction}]
        if hit_target:
            pnl = ((target_price - entry_price) if trade_direction == 'long'
                   else (entry_price - target_price)) * shares - 2 * COMMISSION_PCT * entry_price * shares
            return [{'exit_reason': 'TP', 'pnl': pnl, 'direction': trade_direction}]

    return []


def run_backtest(params: Dict, label: str) -> Dict:
    regimes = (["trending"] * 88 + ["range"] * 75 + ["gap_and_go"] * 62 +
               ["trending"] * 25)
    random.shuffle(regimes)

    all_trades = []
    daily_pnls = []
    ticker_history: Dict[str, List[float]] = {t: [] for t in NIFTY50_TICKERS}
    ticker_prev_close: Dict[str, float] = {t: TICKER_PRICES[t] for t in NIFTY50_TICKERS}

    for day_idx in range(250):
        regime = regimes[day_idx]
        day_pnl = 0.0
        tickers_today = random.sample(NIFTY50_TICKERS, 10)

        for ticker in tickers_today:
            prev_close = ticker_prev_close[ticker]
            # Generate a gapped open
            gap_roll = random.gauss(0, 0.008)  # typical NSE intraday gap distribution
            base_price = prev_close * (1 + gap_roll)

            day_trades = simulate_day_gap_fill(
                ticker, base_price, prev_close, regime, params,
                ticker_history[ticker]
            )

            # Update prev_close
            ticker_history[ticker].append(prev_close)
            ticker_history[ticker] = ticker_history[ticker][-50:]
            ticker_prev_close[ticker] = base_price * random.uniform(0.995, 1.005)

            for t in day_trades:
                all_trades.append(t)
                day_pnl += t['pnl']
                if day_pnl <= DAILY_LOSS_CAP:
                    break
            if day_pnl <= DAILY_LOSS_CAP:
                break

        daily_pnls.append(day_pnl)

    if not all_trades:
        return {'label': label, 'trades': 0, 'win_rate': 0, 'total_pnl': 0,
                'sharpe': 0, 'max_dd_pct': 0, 'avg_r': 0,
                'tp_exits': 0, 'sl_exits': 0, 'eod_exits': 0}

    wins   = [t for t in all_trades if t['pnl'] > 0]
    losses = [t for t in all_trades if t['pnl'] <= 0]
    win_rate  = len(wins) / len(all_trades) * 100
    total_pnl = sum(t['pnl'] for t in all_trades)
    avg_win   = statistics.mean(t['pnl'] for t in wins) if wins else 0
    avg_loss  = statistics.mean(t['pnl'] for t in losses) if losses else 0
    avg_r     = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

    if len(daily_pnls) > 1 and statistics.stdev(daily_pnls) > 0:
        sharpe = (statistics.mean(daily_pnls) / statistics.stdev(daily_pnls)) * math.sqrt(252)
    else:
        sharpe = 0.0

    equity = peak = max_dd_abs = 0.0
    for dp in daily_pnls:
        equity += dp
        if equity > peak: peak = equity
        dd = peak - equity
        if dd > max_dd_abs: max_dd_abs = dd
    max_dd_pct = (max_dd_abs / CAPITAL) * 100

    return {
        'label': label,
        'trades': len(all_trades),
        'win_rate': round(win_rate, 1),
        'total_pnl': round(total_pnl, 0),
        'avg_win': round(avg_win, 0),
        'avg_loss': round(avg_loss, 0),
        'avg_r': round(avg_r, 2),
        'sharpe': round(sharpe, 2),
        'max_dd_pct': round(max_dd_pct, 2),
        'tp_exits': sum(1 for t in all_trades if t['exit_reason'] == 'TP'),
        'sl_exits': sum(1 for t in all_trades if t['exit_reason'] == 'SL'),
        'eod_exits': sum(1 for t in all_trades if t['exit_reason'] == 'EOD'),
    }


if __name__ == '__main__':
    print("=" * 70)
    print("Strategy 5: Gap Fill Mean Reversion (NSE Intraday)")
    print("=" * 70)

    r1 = run_backtest({'gap_min':0.003,'gap_max':0.020,'stop_pct':0.010,
                       'vol_filter':False,'direction_filter':False,
                       'confirm_bars':0,'partial_fill_req':False},
                      "Iter 1 (0.3-2%, no filters)")

    r2 = run_backtest({'gap_min':0.004,'gap_max':0.015,'stop_pct':0.010,
                       'vol_filter':False,'direction_filter':False,
                       'confirm_bars':5,'partial_fill_req':False},
                      "Iter 2 (0.4-1.5%, 5-bar confirm)")

    r3 = run_backtest({'gap_min':0.004,'gap_max':0.015,'stop_pct':0.008,
                       'vol_filter':False,'direction_filter':True,
                       'confirm_bars':5,'partial_fill_req':False},
                      "Iter 3 (+direction/trend filter)")

    r4 = run_backtest({'gap_min':0.004,'gap_max':0.015,'stop_pct':0.008,
                       'vol_filter':True,'direction_filter':True,
                       'confirm_bars':5,'partial_fill_req':False},
                      "Iter 4 (+vol filter 1.5x)")

    r5 = run_backtest({'gap_min':0.005,'gap_max':0.012,'stop_pct':0.008,
                       'vol_filter':True,'direction_filter':True,
                       'confirm_bars':3,'partial_fill_req':True},
                      "Iter 5 (0.5-1.2%, partial fill req)")

    results = [r1, r2, r3, r4, r5]

    print(f"\n{'Metric':<22} " + " | ".join(f"{r['label']:<38}" for r in results))
    print("-" * 220)
    for key, lbl in [
        ('trades','Total Trades'),('win_rate','Win Rate (%)'),
        ('avg_win','Avg Win (₹)'),('avg_loss','Avg Loss (₹)'),
        ('avg_r','Avg R'),('total_pnl','Total PnL (₹)'),
        ('max_dd_pct','Max Drawdown (%)'),('sharpe','Sharpe Ratio'),
        ('tp_exits','TP Exits'),('sl_exits','SL Exits'),('eod_exits','EOD Exits'),
    ]:
        vals = [str(r.get(key,'N/A')) for r in results]
        print(f"{lbl:<22} " + " | ".join(f"{v:<38}" for v in vals))

    print("\n" + "=" * 70)
    print("REAL-WORLD ADJUSTMENT:")
    for r in results:
        rw = round(r['win_rate'] * 0.65, 1)
        verdict = "PASS" if (r['win_rate'] >= 90 or (rw >= 60 and r['sharpe'] >= 5)) \
                  and r['max_dd_pct'] < 5 and r['trades'] >= 50 \
                  and r['total_pnl'] > 0 else "FAIL"
        print(f"  {r['label']}: Synth {r['win_rate']}% → RW {rw}% | "
              f"T={r['trades']} DD={r['max_dd_pct']}% PnL=₹{r['total_pnl']} "
              f"Sharpe={r['sharpe']} → {verdict}")
