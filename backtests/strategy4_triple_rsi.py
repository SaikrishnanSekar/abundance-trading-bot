#!/usr/bin/env python3
"""
Strategy 4: Triple RSI Mean Reversion (adapted for NSE intraday)
=================================================================
Source: QuantifiedStrategies.com — "Triple RSI Trading Strategy: Boost Your Win
        Rate to 90%" (widely shared on Twitter/X quant community).
        URL: https://www.quantifiedstrategies.com/triple-rsi-trading-strategy/
        Also: https://quantifiedstrategies.substack.com/p/triple-rsi-trading-strategy-elevate-a14
        LinkedIn post by @QuantifiedStrategies went viral (>10k impressions).

Published claim: "91% win rate. 83 trades since 1993 on SPY daily. Avg gain 1.4%.
                  Profit factor 5. Uses RSI(4), RSI(14), RSI(40)."

Adaptation for NSE intraday:
  - Original is daily-bar mean reversion on US equities (SPY).
  - Adapted to 5-min bars with three RSI periods scaled to intraday rhythm.
  - RSI periods adapted: RSI(4), RSI(14), RSI(40) → kept as-is (work on bar count).
  - Trend filter: price above 200-bar EMA of intraday closes (long-only bias).
  - Exit: RSI(14) crosses above 50 (mean reversion complete) or EOD.
  - All three RSIs must be in oversold zone (< 30) for a long entry.
  - Short entry: all three RSIs > 70 AND price below 200-bar EMA.

Strategy Rules (Base — Iteration 1):
  - Timeframe  : 5-min candles, NSE 09:15–15:15 IST
  - Indicators : RSI(4), RSI(14), RSI(40) on 5-min close prices
  - Trend      : 200-bar EMA of 5-min closes (approx 16+ hours; uses prior days' data
                 carry-forward; simulated as prev-day bias here)
  - Entry Long : ALL of RSI(4) < 30, RSI(14) < 30, RSI(40) < 30
                 AND price above 200-bar EMA (uptrend)
  - Entry Short: ALL of RSI(4) > 70, RSI(14) > 70, RSI(40) > 70
                 AND price below 200-bar EMA (downtrend)
  - Stop Loss  : 1.5% below entry (long) / above entry (short)
  - Target     : RSI(14) crosses above 50 (long) or below 50 (short)
  - Time filter: Entries only 09:45–13:30; flat by 15:10
  - Max 1 long + 1 short per ticker per day

Iteration 2: Lower RSI thresholds to RSI(4)<25, RSI(14)<35, RSI(40)<40 (triple tiered)
Iteration 3: Add minimum consecutive RSI decline condition (all 3 RSIs falling for 2 bars)
Iteration 4: Add volume surge filter (vol > 1.5× 20-bar avg at entry bar)
Iteration 5: Scale RSI thresholds back to (30/35/40 buy, 70/65/60 sell) to increase trades

Backtest methodology:
  Same synthetic OHLCV framework as Strategy 3. 250 days × 50 tickers.
"""

import random
import math
import statistics
from typing import List, Dict, Optional

random.seed(251)

CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_SIZE   = MARGIN * 0.20
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005
DAILY_LOSS_CAP = -300
BARS_PER_DAY   = 75
ENTRY_START    = 6     # bar index 6 ≈ 09:45 (need history for RSI)
ENTRY_CUTOFF   = 53
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


def generate_day_candles(base_price: float, regime: str) -> List[Dict]:
    atr_pct = 0.008 if regime == "trending" else 0.005 if regime == "range" else 0.010
    gap_pct = random.gauss(0, 0.004)
    open_price = base_price * (1 + gap_pct)
    drift = random.choice([0.0002, -0.0002]) if regime == "trending" else random.gauss(0, 0.00005)

    candles = []
    price = open_price
    avg_vol = base_price * 50_000

    for i in range(BARS_PER_DAY):
        vol_factor = 1.8 if i < 6 else (1.2 if i < 18 else (0.8 if i > 60 else 1.0))
        bar_atr = atr_pct * price * vol_factor * random.uniform(0.4, 1.6)
        open_bar = price
        direction = 1 if random.random() > 0.5 else -1
        close_bar = price + drift * price + direction * bar_atr * 0.45 * random.random()
        high_bar = max(open_bar, close_bar) + bar_atr * 0.25 * random.random()
        low_bar  = min(open_bar, close_bar) - bar_atr * 0.25 * random.random()
        vol = avg_vol * vol_factor * random.uniform(0.5, 2.2)
        candles.append({'i': i, 'open': open_bar, 'high': high_bar,
                        'low': low_bar, 'close': close_bar, 'vol': vol})
        price = close_bar
    return candles


def compute_rsi(closes: List[float], period: int) -> float:
    if len(closes) < period + 1:
        return 50.0
    diffs = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    recent = diffs[-(period):]
    gains = sum(d for d in recent if d > 0) / period
    losses = sum(-d for d in recent if d < 0) / period
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100 - (100 / (1 + rs))


def compute_ema(closes: List[float], period: int) -> float:
    if len(closes) < period:
        return closes[-1] if closes else 0
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def simulate_day_triple_rsi(ticker: str, base_price: float, regime: str,
                             params: Dict, prev_closes: List[float]) -> List[Dict]:
    candles = generate_day_candles(base_price, regime)

    long_rsi4_thresh  = params.get('long_rsi4', 30)
    long_rsi14_thresh = params.get('long_rsi14', 30)
    long_rsi40_thresh = params.get('long_rsi40', 30)
    short_rsi4_thresh  = params.get('short_rsi4', 70)
    short_rsi14_thresh = params.get('short_rsi14', 70)
    short_rsi40_thresh = params.get('short_rsi40', 70)
    stop_pct   = params.get('stop_pct', 0.015)
    vol_filter = params.get('vol_filter', False)
    vol_thresh = params.get('vol_thresh', 1.5)
    consec_decline = params.get('consec_decline', False)

    # Use previous closes as history (carry-forward for 200-bar EMA)
    history = list(prev_closes[-200:])
    vols = [c['vol'] for c in candles]
    avg_vol_20 = sum(vols[:20]) / 20 if len(vols) >= 20 else sum(vols) / len(vols)

    trades = []
    long_taken = False
    short_taken = False
    position = None
    prev_rsi14_list = []  # track RSI(14) for exit condition

    # Prebuild RSI history from prev_closes
    rsi4_hist = []
    rsi14_hist = []

    for i, bar in enumerate(candles):
        history.append(bar['close'])
        rsi4  = compute_rsi(history, 4)
        rsi14 = compute_rsi(history, 14)
        rsi40 = compute_rsi(history, 40)
        rsi4_hist.append(rsi4)
        rsi14_hist.append(rsi14)
        ema200 = compute_ema(history, 200)

        # Exit open position
        if position is not None:
            direction = position['direction']
            entry = position['entry']
            stop  = position['stop']

            if i >= FLAT_BAR:
                exit_price = bar['close'] * (1 + (-SLIPPAGE_PCT if direction == 'long' else SLIPPAGE_PCT))
                pnl = ((exit_price - entry) if direction == 'long' else (entry - exit_price)) * int(MAX_POS_SIZE / entry) - 2 * COMMISSION_PCT * entry * int(MAX_POS_SIZE / entry)
                trades.append({'exit_reason': 'EOD', 'pnl': pnl, 'direction': direction})
                position = None
                continue

            # RSI exit: RSI(14) crosses 50 in direction of trade
            rsi14_exit = (direction == 'long' and rsi14 > 50) or (direction == 'short' and rsi14 < 50)
            hit_stop = (bar['low'] <= stop if direction == 'long' else bar['high'] >= stop)

            if hit_stop:
                pnl = ((stop - entry) if direction == 'long' else (entry - stop)) * int(MAX_POS_SIZE / entry) - 2 * COMMISSION_PCT * entry * int(MAX_POS_SIZE / entry)
                trades.append({'exit_reason': 'SL', 'pnl': pnl, 'direction': direction})
                position = None
            elif rsi14_exit:
                exit_price = bar['close'] * (1 + (-SLIPPAGE_PCT if direction == 'long' else SLIPPAGE_PCT))
                pnl = ((exit_price - entry) if direction == 'long' else (entry - exit_price)) * int(MAX_POS_SIZE / entry) - 2 * COMMISSION_PCT * entry * int(MAX_POS_SIZE / entry)
                trades.append({'exit_reason': 'RSI_EXIT', 'pnl': pnl, 'direction': direction})
                position = None
            continue

        # Entry
        if i < ENTRY_START or i > ENTRY_CUTOFF:
            continue

        # Long entry
        if not long_taken:
            long_cond = (rsi4 < long_rsi4_thresh and
                         rsi14 < long_rsi14_thresh and
                         rsi40 < long_rsi40_thresh and
                         bar['close'] > ema200)
            if consec_decline and len(rsi14_hist) >= 3:
                long_cond = long_cond and (rsi14_hist[-1] < rsi14_hist[-2] < rsi14_hist[-3])
            if vol_filter:
                long_cond = long_cond and (bar['vol'] > vol_thresh * avg_vol_20)
            if long_cond:
                entry_price = bar['close'] * (1 + SLIPPAGE_PCT)
                stop_price = entry_price * (1 - stop_pct)
                position = {'direction': 'long', 'entry': entry_price, 'stop': stop_price}
                long_taken = True

        # Short entry
        if not short_taken and position is None:
            short_cond = (rsi4 > short_rsi4_thresh and
                          rsi14 > short_rsi14_thresh and
                          rsi40 > short_rsi40_thresh and
                          bar['close'] < ema200)
            if consec_decline and len(rsi14_hist) >= 3:
                short_cond = short_cond and (rsi14_hist[-1] > rsi14_hist[-2] > rsi14_hist[-3])
            if vol_filter:
                short_cond = short_cond and (bar['vol'] > vol_thresh * avg_vol_20)
            if short_cond:
                entry_price = bar['close'] * (1 - SLIPPAGE_PCT)
                stop_price = entry_price * (1 + stop_pct)
                position = {'direction': 'short', 'entry': entry_price, 'stop': stop_price}
                short_taken = True

    return trades


def run_backtest(params: Dict, label: str) -> Dict:
    regimes = (["trending"] * 88 + ["range"] * 75 + ["gap_and_go"] * 62 +
               ["trending"] * 25)
    random.shuffle(regimes)

    all_trades = []
    daily_pnls = []
    # Carry-forward closes per ticker (simulate 200-bar EMA history)
    ticker_history: Dict[str, List[float]] = {t: [] for t in NIFTY50_TICKERS}

    for day_idx in range(250):
        regime = regimes[day_idx]
        day_pnl = 0.0
        tickers_today = random.sample(NIFTY50_TICKERS, 10)

        for ticker in tickers_today:
            base = TICKER_PRICES[ticker] * random.uniform(0.88, 1.12)
            prev_closes = ticker_history[ticker]
            day_trades = simulate_day_triple_rsi(ticker, base, regime, params, prev_closes)

            # Update history
            new_closes = [base * random.uniform(0.995, 1.005) for _ in range(BARS_PER_DAY)]
            ticker_history[ticker].extend(new_closes)
            ticker_history[ticker] = ticker_history[ticker][-300:]  # keep last 300 bars

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
                'sharpe': 0, 'max_dd_pct': 0, 'avg_r': 0}

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
        'tp_exits': sum(1 for t in all_trades if t['exit_reason'] == 'RSI_EXIT'),
        'sl_exits': sum(1 for t in all_trades if t['exit_reason'] == 'SL'),
        'eod_exits': sum(1 for t in all_trades if t['exit_reason'] == 'EOD'),
    }


if __name__ == '__main__':
    print("=" * 70)
    print("Strategy 4: Triple RSI Mean Reversion (NSE Intraday)")
    print("=" * 70)

    # Iter 1 — base: RSI(4,14,40) all < 30 / > 70
    r1 = run_backtest({'long_rsi4':30,'long_rsi14':30,'long_rsi40':30,
                       'short_rsi4':70,'short_rsi14':70,'short_rsi40':70,
                       'stop_pct':0.015,'vol_filter':False,'consec_decline':False},
                      "Iter 1 (30/30/30 OS, no filters)")

    # Iter 2 — tiered thresholds (4<25, 14<35, 40<40)
    r2 = run_backtest({'long_rsi4':25,'long_rsi14':35,'long_rsi40':40,
                       'short_rsi4':75,'short_rsi14':65,'short_rsi40':60,
                       'stop_pct':0.015,'vol_filter':False,'consec_decline':False},
                      "Iter 2 (tiered 25/35/40)")

    # Iter 3 — add consecutive decline requirement
    r3 = run_backtest({'long_rsi4':25,'long_rsi14':35,'long_rsi40':40,
                       'short_rsi4':75,'short_rsi14':65,'short_rsi40':60,
                       'stop_pct':0.012,'vol_filter':False,'consec_decline':True},
                      "Iter 3 (+consec decline, tighter stop)")

    # Iter 4 — add volume filter
    r4 = run_backtest({'long_rsi4':25,'long_rsi14':35,'long_rsi40':40,
                       'short_rsi4':75,'short_rsi14':65,'short_rsi40':60,
                       'stop_pct':0.012,'vol_filter':True,'vol_thresh':1.5,
                       'consec_decline':True},
                      "Iter 4 (+vol 1.5x filter)")

    # Iter 5 — relax thresholds to get more trades (30/35/40 buy, 70/65/60 sell)
    r5 = run_backtest({'long_rsi4':30,'long_rsi14':35,'long_rsi40':40,
                       'short_rsi4':70,'short_rsi14':65,'short_rsi40':60,
                       'stop_pct':0.015,'vol_filter':True,'vol_thresh':1.2,
                       'consec_decline':False},
                      "Iter 5 (relaxed 30/35/40, vol 1.2x)")

    results = [r1, r2, r3, r4, r5]

    print(f"\n{'Metric':<22} " + " | ".join(f"{r['label']:<38}" for r in results))
    print("-" * 220)
    for key, lbl in [
        ('trades','Total Trades'),('win_rate','Win Rate (%)'),
        ('avg_win','Avg Win (₹)'),('avg_loss','Avg Loss (₹)'),
        ('avg_r','Avg R'),('total_pnl','Total PnL (₹)'),
        ('max_dd_pct','Max Drawdown (%)'),('sharpe','Sharpe Ratio'),
        ('tp_exits','RSI Exits'),('sl_exits','SL Exits'),('eod_exits','EOD Exits'),
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
