#!/usr/bin/env python3
"""
Strategy 6: MACD + RSI Combo Mean Reversion (NSE Intraday)
===========================================================
Source: QuantifiedStrategies.com — "MACD AND RSI STRATEGY — 81.41% WIN RATE"
        URL: https://quantifiedstrategies.substack.com/p/macd-and-rsi-strategy-8141-win-rate
        Also: "MACD and RSI Strategy: 73% Win Rate" (with 3 filters, 235 trades)
        URL: https://www.quantifiedstrategies.com/macd-and-rsi-strategy/
        Twitter/X widely shared: @QuantifiedStrategies Substack post, shared by
        >50 Indian quant handles on Twitter/X in Feb 2025.

Published claim: "73–81% win rate on SPY. 235 trades. Avg gain 0.88%/trade.
                  Includes commissions and slippage. 3-filter MACD+RSI system."

Strategy Rules (Base — Iteration 1):
  - Timeframe  : 5-min candles, NSE 09:15–15:15 IST (adapted from daily SPY)
  - MACD       : (12, 26, 9) standard settings
  - RSI        : RSI(14)
  - Entry Long : MACD histogram turns positive (crosses above 0) AND RSI(14) < 50
                 (momentum surge from below midline = mean reversion confirming)
  - Entry Short: MACD histogram turns negative (crosses below 0) AND RSI(14) > 50
  - Stop Loss  : 1.2% from entry
  - Target     : 1.5× risk (1.8% from entry) = R=1.5
  - Time filter: entries 09:45–13:30 only; flat by 15:10
  - Max 1 long + 1 short per ticker per day
  - No position sizing change; use standard MAX_POS_SIZE

Iteration 2: Add 200-bar EMA trend filter (long only above EMA, short only below)
Iteration 3: Tighten RSI to RSI(14) < 40 for longs / > 60 for shorts (more selective)
Iteration 4: Use fast MACD (6,13,5) for intraday + RSI(5) < 35 / > 65
Iteration 5: Add volume surge (vol > 1.5× avg) + RSI(5) < 30 / > 70

Backtest methodology:
  Same synthetic OHLCV framework. 250 days × 50 tickers.
"""

import random
import math
import statistics
from typing import List, Dict

random.seed(718)

CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_SIZE   = MARGIN * 0.20
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005
DAILY_LOSS_CAP = -300
BARS_PER_DAY   = 75
ENTRY_START    = 12     # need MACD history (~26 bars minimum; start at bar 12 with warmup)
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
    price = base_price * (1 + gap_pct)
    drift = random.choice([0.0002, -0.0002]) if regime == "trending" else random.gauss(0, 0.00005)
    avg_vol = base_price * 50_000
    candles = []
    for i in range(BARS_PER_DAY):
        vf = 1.8 if i < 6 else (1.2 if i < 18 else (0.8 if i > 60 else 1.0))
        atr = atr_pct * price * vf * random.uniform(0.4, 1.6)
        ob = price
        d = 1 if random.random() > 0.5 else -1
        cb = price + drift * price + d * atr * 0.4 * random.random()
        hb = max(ob, cb) + atr * 0.25 * random.random()
        lb = min(ob, cb) - atr * 0.25 * random.random()
        vol = avg_vol * vf * random.uniform(0.5, 2.2)
        candles.append({'i':i,'open':ob,'high':hb,'low':lb,'close':cb,'vol':vol})
        price = cb
    return candles


def compute_ema_series(closes: List[float], period: int) -> List[float]:
    if not closes: return []
    k = 2.0 / (period + 1)
    emas = []
    ema = closes[0]
    for c in closes:
        ema = c * k + ema * (1 - k)
        emas.append(ema)
    return emas


def compute_macd(closes: List[float], fast: int, slow: int, signal: int):
    """Return (macd_line, signal_line, histogram) for last bar."""
    if len(closes) < slow + signal:
        return 0.0, 0.0, 0.0
    ema_fast = compute_ema_series(closes, fast)
    ema_slow = compute_ema_series(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    if len(macd_line) < signal:
        return macd_line[-1], 0.0, macd_line[-1]
    signal_line_series = compute_ema_series(macd_line, signal)
    sig = signal_line_series[-1]
    hist = macd_line[-1] - sig
    return macd_line[-1], sig, hist


def compute_rsi(closes: List[float], period: int) -> float:
    if len(closes) < period + 1:
        return 50.0
    diffs = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    recent = diffs[-(period):]
    gains = sum(d for d in recent if d > 0) / period
    losses = sum(-d for d in recent if d < 0) / period
    if losses == 0: return 100.0
    return 100 - (100 / (1 + gains / losses))


def compute_ema_val(closes: List[float], period: int) -> float:
    if len(closes) < period:
        return closes[-1] if closes else 0
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema


def simulate_day_macd_rsi(ticker: str, base_price: float, regime: str,
                           params: Dict, prev_closes: List[float]) -> List[Dict]:
    candles = generate_day_candles(base_price, regime)

    macd_fast  = params.get('macd_fast', 12)
    macd_slow  = params.get('macd_slow', 26)
    macd_sig   = params.get('macd_signal', 9)
    rsi_period = params.get('rsi_period', 14)
    rsi_lo     = params.get('rsi_lo', 50)   # long when RSI < rsi_lo
    rsi_hi     = params.get('rsi_hi', 50)   # short when RSI > rsi_hi
    stop_pct   = params.get('stop_pct', 0.012)
    target_r   = params.get('target_r', 1.5)
    trend_filter = params.get('trend_filter', False)
    ema_period = params.get('ema_period', 200)
    vol_filter = params.get('vol_filter', False)
    vol_thresh = params.get('vol_thresh', 1.5)

    history = list(prev_closes[-300:])
    vols = [c['vol'] for c in candles]
    avg_vol = sum(vols[:20])/20 if len(vols) >= 20 else sum(vols)/len(vols)

    trades = []
    long_taken = False
    short_taken = False
    position = None
    prev_hist = None  # previous bar's MACD histogram

    for i, bar in enumerate(candles):
        history.append(bar['close'])
        closes_now = history

        _, _, macd_hist = compute_macd(closes_now, macd_fast, macd_slow, macd_sig)
        rsi = compute_rsi(closes_now, rsi_period)
        ema_val = compute_ema_val(closes_now, ema_period) if trend_filter else bar['close']

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
                prev_hist = macd_hist
                continue

            hit_stop = (bar['low'] <= stop if direction == 'long' else bar['high'] >= stop)
            hit_tp   = (bar['high'] >= target if direction == 'long' else bar['low'] <= target)

            if hit_stop:
                pnl = ((stop - entry) if direction == 'long' else (entry - stop)) * int(MAX_POS_SIZE / entry) - 2 * COMMISSION_PCT * entry * int(MAX_POS_SIZE / entry)
                trades.append({'exit_reason': 'SL', 'pnl': pnl, 'direction': direction})
                position = None
            elif hit_tp:
                pnl = ((target - entry) if direction == 'long' else (entry - target)) * int(MAX_POS_SIZE / entry) - 2 * COMMISSION_PCT * entry * int(MAX_POS_SIZE / entry)
                trades.append({'exit_reason': 'TP', 'pnl': pnl, 'direction': direction})
                position = None

            prev_hist = macd_hist
            continue

        # Entry
        if i < ENTRY_START or i > ENTRY_CUTOFF or prev_hist is None:
            prev_hist = macd_hist
            continue

        # MACD histogram cross
        hist_cross_up = prev_hist < 0 and macd_hist >= 0
        hist_cross_dn = prev_hist > 0 and macd_hist <= 0

        # Long entry
        if not long_taken and hist_cross_up and rsi < rsi_lo:
            if trend_filter and bar['close'] < ema_val:
                prev_hist = macd_hist
                continue
            if vol_filter and bar['vol'] < vol_thresh * avg_vol:
                prev_hist = macd_hist
                continue
            entry_price = bar['close'] * (1 + SLIPPAGE_PCT)
            stop_price  = entry_price * (1 - stop_pct)
            risk = entry_price - stop_price
            target_price = entry_price + target_r * risk
            position = {'direction': 'long', 'entry': entry_price,
                        'stop': stop_price, 'target': target_price}
            long_taken = True

        # Short entry
        elif not short_taken and hist_cross_dn and rsi > rsi_hi and position is None:
            if trend_filter and bar['close'] > ema_val:
                prev_hist = macd_hist
                continue
            if vol_filter and bar['vol'] < vol_thresh * avg_vol:
                prev_hist = macd_hist
                continue
            entry_price = bar['close'] * (1 - SLIPPAGE_PCT)
            stop_price  = entry_price * (1 + stop_pct)
            risk = stop_price - entry_price
            target_price = entry_price - target_r * risk
            position = {'direction': 'short', 'entry': entry_price,
                        'stop': stop_price, 'target': target_price}
            short_taken = True

        prev_hist = macd_hist

    return trades


def run_backtest(params: Dict, label: str) -> Dict:
    regimes = (["trending"] * 88 + ["range"] * 75 + ["gap_and_go"] * 62 +
               ["trending"] * 25)
    random.shuffle(regimes)

    all_trades = []
    daily_pnls = []
    ticker_history: Dict[str, List[float]] = {t: [TICKER_PRICES[t]] * 50 for t in NIFTY50_TICKERS}

    for day_idx in range(250):
        regime = regimes[day_idx]
        day_pnl = 0.0
        tickers_today = random.sample(NIFTY50_TICKERS, 10)

        for ticker in tickers_today:
            base = TICKER_PRICES[ticker] * random.uniform(0.88, 1.12)
            day_trades = simulate_day_macd_rsi(ticker, base, regime, params,
                                                ticker_history[ticker])
            new_c = [base * random.uniform(0.997, 1.003) for _ in range(BARS_PER_DAY)]
            ticker_history[ticker].extend(new_c)
            ticker_history[ticker] = ticker_history[ticker][-400:]

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
    print("Strategy 6: MACD + RSI Combo Mean Reversion (NSE Intraday)")
    print("=" * 70)

    r1 = run_backtest({'macd_fast':12,'macd_slow':26,'macd_signal':9,
                       'rsi_period':14,'rsi_lo':50,'rsi_hi':50,
                       'stop_pct':0.012,'target_r':1.5,
                       'trend_filter':False,'vol_filter':False},
                      "Iter 1 (12/26/9, RSI14<50, no filters)")

    r2 = run_backtest({'macd_fast':12,'macd_slow':26,'macd_signal':9,
                       'rsi_period':14,'rsi_lo':50,'rsi_hi':50,
                       'stop_pct':0.012,'target_r':1.5,
                       'trend_filter':True,'ema_period':200,'vol_filter':False},
                      "Iter 2 (+200EMA trend filter)")

    r3 = run_backtest({'macd_fast':12,'macd_slow':26,'macd_signal':9,
                       'rsi_period':14,'rsi_lo':40,'rsi_hi':60,
                       'stop_pct':0.012,'target_r':1.8,
                       'trend_filter':True,'ema_period':200,'vol_filter':False},
                      "Iter 3 (RSI14<40/>60, R=1.8)")

    r4 = run_backtest({'macd_fast':6,'macd_slow':13,'macd_signal':5,
                       'rsi_period':5,'rsi_lo':35,'rsi_hi':65,
                       'stop_pct':0.010,'target_r':1.8,
                       'trend_filter':True,'ema_period':200,'vol_filter':False},
                      "Iter 4 (fast MACD 6/13/5, RSI5<35)")

    r5 = run_backtest({'macd_fast':6,'macd_slow':13,'macd_signal':5,
                       'rsi_period':5,'rsi_lo':30,'rsi_hi':70,
                       'stop_pct':0.010,'target_r':2.0,
                       'trend_filter':True,'ema_period':200,
                       'vol_filter':True,'vol_thresh':1.5},
                      "Iter 5 (RSI5<30, vol 1.5x, R=2.0)")

    results = [r1, r2, r3, r4, r5]

    print(f"\n{'Metric':<22} " + " | ".join(f"{r['label']:<40}" for r in results))
    print("-" * 230)
    for key, lbl in [
        ('trades','Total Trades'),('win_rate','Win Rate (%)'),
        ('avg_win','Avg Win (₹)'),('avg_loss','Avg Loss (₹)'),
        ('avg_r','Avg R'),('total_pnl','Total PnL (₹)'),
        ('max_dd_pct','Max Drawdown (%)'),('sharpe','Sharpe Ratio'),
        ('tp_exits','TP Exits'),('sl_exits','SL Exits'),('eod_exits','EOD Exits'),
    ]:
        vals = [str(r.get(key,'N/A')) for r in results]
        print(f"{lbl:<22} " + " | ".join(f"{v:<40}" for v in vals))

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
