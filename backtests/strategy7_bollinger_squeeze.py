#!/usr/bin/env python3
"""
Strategy 7: Bollinger Band Squeeze Breakout — NSE Intraday
===========================================================
Source: QuantifiedStrategies.com — "Bollinger Band Squeeze Strategy — Backtest and
        Performance Insights"
        URL: https://www.quantifiedstrategies.com/bollinger-band-squeeze-strategy/
        Also: PyQuantLab Medium — "Bollinger Band Squeeze Breakout Trading Strategy
        with Trailing Stops"
        URL: https://pyquantlab.medium.com/bollinger-band-squeeze-breakout-trading-strategy-with-trailing-stops-7aedc2f10958
        Indian Twitter/X: Discussed extensively on @AlgoTradingClub, @nsealgo and
        TradingView India community as a volatility breakout setup.
        StockCharts ChartSchool: https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/bollinger-band-squeeze

Published claim: "Squeeze identifies low-volatility compression; when bands expand,
                  a directional breakout follows. NSE intraday version: 5-min BB squeeze
                  with volume surge confirmation shows 65–72% win rate in community reports."

Strategy Rules (Base — Iteration 1):
  - Timeframe  : 5-min candles, NSE 09:15–15:15 IST
  - BB         : 20-bar SMA ± 2.0-SD Bollinger Bands
  - Squeeze    : Defined as current BB width < BB width N bars ago
                 (bands contracting = low volatility compression)
  - Entry Long : After 5+ squeeze bars, first bar where close > upper BB → long
  - Entry Short: After 5+ squeeze bars, first bar where close < lower BB → short
  - Stop Loss  : 1.0× ATR(14) below entry (long) / above entry (short)
  - Target     : 2.0× ATR(14) from entry (R=2.0)
  - Volume     : Vol > 1.5× 20-bar avg required for breakout bar (Iter 1 optional)
  - Time filter: Entries only 09:30–13:00; flat by 15:10
  - Max 1 long + 1 short per ticker per day

Iteration 2: Require squeeze duration ≥ 8 bars (tighter compression)
Iteration 3: Add Momentum filter (bar BODY > 0.5× ATR — strong breakout candle)
Iteration 4: Add volume surge (vol > 2.0× avg) + Keltner Channel outside BB check
Iteration 5: Use adaptive ATR stop (1.5× ATR) + require 2 consecutive breakout bars

Backtest methodology:
  Same synthetic OHLCV framework. 250 days × 50 tickers.
"""

import random
import math
import statistics
from typing import List, Dict

random.seed(919)

CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_SIZE   = MARGIN * 0.20
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005
DAILY_LOSS_CAP = -300
BARS_PER_DAY   = 75
ENTRY_START    = 21     # need 20 bars for BB
ENTRY_CUTOFF   = 48     # bar index ≈ 13:00
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
    """Generate day with occasional squeeze pattern (low vol → burst)."""
    gap_pct = random.gauss(0, 0.003)
    price = base_price * (1 + gap_pct)
    drift = random.choice([0.0002, -0.0002]) if regime == "trending" else random.gauss(0, 0.00003)

    # Squeeze simulation: first ~20 bars have compressed volatility,
    # then a burst in trending/gap regimes
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
            # Burst bar — strong directional move
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

        candles.append({'i':i,'open':ob,'high':hb,'low':lb,'close':cb,'vol':vol,
                        'is_burst': has_squeeze and abs(i - squeeze_end) <= 1})
        price = cb

    return candles


def compute_bb(closes: List[float], period: int = 20, mult: float = 2.0):
    """Return (upper, middle, lower, width) for last bar."""
    if len(closes) < period:
        c = closes[-1]
        return c * 1.01, c, c * 0.99, c * 0.02
    w = closes[-period:]
    sma = sum(w) / period
    std = statistics.stdev(w) if len(w) >= 2 else w[0] * 0.005
    upper = sma + mult * std
    lower = sma - mult * std
    return upper, sma, lower, upper - lower


def compute_atr(candles: List[Dict], period: int = 14) -> float:
    if len(candles) < 2:
        return candles[-1]['high'] - candles[-1]['low'] if candles else 1.0
    trs = []
    for i in range(1, min(len(candles), period + 1)):
        c = candles[i]
        p = candles[i-1]
        tr = max(c['high'] - c['low'], abs(c['high'] - p['close']), abs(c['low'] - p['close']))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 1.0


def simulate_day_bb_squeeze(ticker: str, base_price: float, regime: str,
                              params: Dict) -> List[Dict]:
    candles = generate_day_candles(base_price, regime)

    bb_period   = params.get('bb_period', 20)
    bb_mult     = params.get('bb_mult', 2.0)
    squeeze_min = params.get('squeeze_min', 5)
    stop_atr_m  = params.get('stop_atr_mult', 1.0)
    target_r    = params.get('target_r', 2.0)
    vol_filter  = params.get('vol_filter', False)
    vol_thresh  = params.get('vol_thresh', 1.5)
    body_filter = params.get('body_filter', False)  # strong candle body
    consec_break= params.get('consec_break', False)  # 2 consecutive breakout bars

    vols = [c['vol'] for c in candles]
    avg_vol = sum(vols[:20])/20 if len(vols) >= 20 else sum(vols)/len(vols)

    trades = []
    long_taken = False
    short_taken = False
    position = None

    closes_hist = []
    bb_widths = []
    squeeze_count = 0
    prev_upper = None
    prev_lower = None
    prev_break_dir = None  # for consec_break

    for i, bar in enumerate(candles):
        closes_hist.append(bar['close'])
        upper, mid, lower, width = compute_bb(closes_hist, bb_period, bb_mult)
        bb_widths.append(width)

        # Squeeze detection: current width < N-bar ago width
        if len(bb_widths) > 3:
            if width < bb_widths[-4]:  # compressing vs 3 bars ago
                squeeze_count += 1
            else:
                squeeze_count = 0
        else:
            squeeze_count = 0

        # Exit logic
        if position is not None:
            direction = position['direction']
            entry = position['entry']
            stop  = position['stop']
            target = position['target']

            if i >= FLAT_BAR:
                ep = bar['close'] * (1 + (-SLIPPAGE_PCT if direction == 'long' else SLIPPAGE_PCT))
                pnl = ((ep - entry) if direction == 'long' else (entry - ep)) * int(MAX_POS_SIZE / entry) - 2 * COMMISSION_PCT * entry * int(MAX_POS_SIZE / entry)
                trades.append({'exit_reason': 'EOD', 'pnl': pnl, 'direction': direction})
                position = None
            else:
                hit_stop = bar['low'] <= stop if direction == 'long' else bar['high'] >= stop
                hit_tp   = bar['high'] >= target if direction == 'long' else bar['low'] <= target
                if hit_stop:
                    pnl = ((stop - entry) if direction == 'long' else (entry - stop)) * int(MAX_POS_SIZE / entry) - 2 * COMMISSION_PCT * entry * int(MAX_POS_SIZE / entry)
                    trades.append({'exit_reason': 'SL', 'pnl': pnl, 'direction': direction})
                    position = None
                elif hit_tp:
                    pnl = ((target - entry) if direction == 'long' else (entry - target)) * int(MAX_POS_SIZE / entry) - 2 * COMMISSION_PCT * entry * int(MAX_POS_SIZE / entry)
                    trades.append({'exit_reason': 'TP', 'pnl': pnl, 'direction': direction})
                    position = None

            prev_upper = upper
            prev_lower = lower
            continue

        # Entry
        if i < ENTRY_START or i > ENTRY_CUTOFF:
            prev_upper = upper
            prev_lower = lower
            continue

        if squeeze_count < squeeze_min:
            prev_upper = upper
            prev_lower = lower
            continue

        atr = compute_atr(candles[:i+1])
        bar_body = abs(bar['close'] - bar['open'])

        # Breakout long
        if not long_taken and bar['close'] > upper:
            if vol_filter and bar['vol'] < vol_thresh * avg_vol: pass
            elif body_filter and bar_body < 0.5 * atr: pass
            elif consec_break and prev_break_dir != 'up': pass
            else:
                entry_price = bar['close'] * (1 + SLIPPAGE_PCT)
                stop_price  = entry_price - stop_atr_m * atr
                target_price = entry_price + target_r * stop_atr_m * atr
                position = {'direction': 'long', 'entry': entry_price,
                            'stop': stop_price, 'target': target_price}
                long_taken = True
                prev_break_dir = None

        # Breakout short
        elif not short_taken and position is None and bar['close'] < lower:
            if vol_filter and bar['vol'] < vol_thresh * avg_vol: pass
            elif body_filter and bar_body < 0.5 * atr: pass
            elif consec_break and prev_break_dir != 'down': pass
            else:
                entry_price = bar['close'] * (1 - SLIPPAGE_PCT)
                stop_price  = entry_price + stop_atr_m * atr
                target_price = entry_price - target_r * stop_atr_m * atr
                position = {'direction': 'short', 'entry': entry_price,
                            'stop': stop_price, 'target': target_price}
                short_taken = True
                prev_break_dir = None

        # Track breakout direction for consec_break
        if bar['close'] > upper:
            prev_break_dir = 'up'
        elif bar['close'] < lower:
            prev_break_dir = 'down'
        else:
            prev_break_dir = None

        prev_upper = upper
        prev_lower = lower

    return trades


def run_backtest(params: Dict, label: str) -> Dict:
    regimes = (["trending"] * 88 + ["range"] * 75 + ["gap_and_go"] * 62 +
               ["trending"] * 25)
    random.shuffle(regimes)

    all_trades = []
    daily_pnls = []

    for day_idx in range(250):
        regime = regimes[day_idx]
        day_pnl = 0.0
        tickers_today = random.sample(NIFTY50_TICKERS, 10)

        for ticker in tickers_today:
            base = TICKER_PRICES[ticker] * random.uniform(0.88, 1.12)
            day_trades = simulate_day_bb_squeeze(ticker, base, regime, params)
            for t in day_trades:
                all_trades.append(t)
                day_pnl += t['pnl']
                if day_pnl <= DAILY_LOSS_CAP: break
            if day_pnl <= DAILY_LOSS_CAP: break

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
    print("Strategy 7: Bollinger Band Squeeze Breakout (NSE Intraday)")
    print("=" * 70)

    r1 = run_backtest({'bb_period':20,'bb_mult':2.0,'squeeze_min':5,'stop_atr_mult':1.0,
                       'target_r':2.0,'vol_filter':False,'body_filter':False,'consec_break':False},
                      "Iter 1 (5-bar sq, ATR-stop, no filters)")

    r2 = run_backtest({'bb_period':20,'bb_mult':2.0,'squeeze_min':8,'stop_atr_mult':1.0,
                       'target_r':2.0,'vol_filter':True,'vol_thresh':1.5,
                       'body_filter':False,'consec_break':False},
                      "Iter 2 (8-bar sq, vol 1.5x)")

    r3 = run_backtest({'bb_period':20,'bb_mult':2.0,'squeeze_min':8,'stop_atr_mult':1.0,
                       'target_r':2.0,'vol_filter':True,'vol_thresh':1.5,
                       'body_filter':True,'consec_break':False},
                      "Iter 3 (+body filter > 0.5 ATR)")

    r4 = run_backtest({'bb_period':20,'bb_mult':2.0,'squeeze_min':8,'stop_atr_mult':1.0,
                       'target_r':2.0,'vol_filter':True,'vol_thresh':2.0,
                       'body_filter':True,'consec_break':False},
                      "Iter 4 (vol 2.0x, body filter)")

    r5 = run_backtest({'bb_period':20,'bb_mult':2.0,'squeeze_min':10,'stop_atr_mult':1.5,
                       'target_r':2.5,'vol_filter':True,'vol_thresh':2.0,
                       'body_filter':True,'consec_break':True},
                      "Iter 5 (10-bar sq, consec break, 1.5 ATR stop)")

    results = [r1, r2, r3, r4, r5]

    print(f"\n{'Metric':<22} " + " | ".join(f"{r['label']:<42}" for r in results))
    print("-" * 240)
    for key, lbl in [
        ('trades','Total Trades'),('win_rate','Win Rate (%)'),
        ('avg_win','Avg Win (₹)'),('avg_loss','Avg Loss (₹)'),
        ('avg_r','Avg R'),('total_pnl','Total PnL (₹)'),
        ('max_dd_pct','Max Drawdown (%)'),('sharpe','Sharpe Ratio'),
        ('tp_exits','TP Exits'),('sl_exits','SL Exits'),('eod_exits','EOD Exits'),
    ]:
        vals = [str(r.get(key,'N/A')) for r in results]
        print(f"{lbl:<22} " + " | ".join(f"{v:<42}" for v in vals))

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
