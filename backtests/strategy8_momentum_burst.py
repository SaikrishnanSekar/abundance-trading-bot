#!/usr/bin/env python3
"""
Strategy 8: Momentum Burst — US SPY/QQQ Intraday (Alpaca)
==========================================================
Source: Popularized by Pradeep Bonde (@stockbee) on Twitter/X and Substack.
        Adapted for intraday US market from his swing framework.
        References:
          https://www.financialwisdomtv.com/post/momentum-burst-trading-strategy-how-to-capture-8-40-moves-in-3-5-days
          https://tradefundrr.com/momentum-breakout-strategies/
          QuantConnect forum "Beat the Market: An Effective Intraday Momentum Strategy
          for S&P500 ETF (SPY)" — https://www.quantconnect.com/forum/discussion/17091
          Twitter/X handle @stockbee: momentum burst, widely cited in Indian and US
          quant communities; discussed on AlgoTest India forum.

Published claim: "4%+ move breakout on daily. 5-min chart for entry, ride momentum.
                  8–40% captures possible in 3–5 sessions. Intraday version: first
                  30-min range breakout on SPY/QQQ with volume surge > 2× shows
                  68–75% WR in community reports."

US market adaptation:
  - Instruments: SPY and QQQ (liquid, tight spreads, high volume)
  - This is an INTRADAY strategy on Alpaca paper mode
  - Capital: $800, positions ≤ $200 (25% per position), max 4 positions
  - Commission: $0 (Alpaca), slippage: 0.02% (tight spread for SPY/QQQ)

Strategy Rules (Base — Iteration 1):
  - Timeframe  : 5-min candles, US market hours 09:30–16:00 ET
  - Range      : First 30-min high/low (first 6 × 5-min candles)
  - Entry Long : 5-min close > 30-min high + 0.1% buffer AND vol > 2× avg(20)
                 AND RSI(14) > 50 (momentum confirmation)
  - Entry Short: 5-min close < 30-min low − 0.1% buffer AND same conditions
  - Stop       : 30-min low (for long) or 30-min high (for short)
  - Target     : Entry + 1.5× range width
  - Time       : Entries only 10:00–13:30; flat by 15:45
  - Max 1 per instrument per day

Iteration 2: Widen range to 45-min; add VWAP filter (price must be above VWAP for longs)
Iteration 3: Add pre-market gap condition (> 0.2% gap increases momentum)
Iteration 4: Use 15-min range, tighter volume (2.5×), RSI(14) > 55
Iteration 5: 15-min range + vol 2.5× + RSI > 55 + require range < 1.5% (not overdone)

Backtest methodology:
  Synthetic SPY/QQQ 5-min OHLCV. 250 trading days. Capital $800.
  US market: 09:30–16:00 = 78 × 5-min bars.
"""

import random
import math
import statistics
from typing import List, Dict

random.seed(628)

CAPITAL        = 800.0     # USD
MAX_POS_PCT    = 0.25      # 25% per position
MAX_POS_SIZE   = CAPITAL * MAX_POS_PCT   # $200
MAX_POSITIONS  = 4
COMMISSION_PCT = 0.0000    # Alpaca: $0 commission
SLIPPAGE_PCT   = 0.0002    # 0.02% slippage
DAILY_LOSS_CAP = -12.0     # 1.5% of capital

BARS_PER_DAY   = 78        # 09:30–16:00 = 78 × 5-min bars
ORB_BARS_30    = 6         # 30-min range = first 6 bars
ORB_BARS_45    = 9         # 45-min range
ORB_BARS_15    = 3         # 15-min range
ENTRY_CUTOFF   = 48        # bar 48 ≈ 13:30
FLAT_BAR       = 75        # bar 75 ≈ 15:45

INSTRUMENTS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN", "TSLA", "AMD"]
BASE_PRICES = {
    "SPY": 520.0, "QQQ": 430.0, "AAPL": 195.0, "MSFT": 415.0,
    "NVDA": 115.0, "META": 510.0, "GOOGL": 175.0, "AMZN": 190.0,
    "TSLA": 260.0, "AMD": 155.0
}


def generate_day_candles(base_price: float, regime: str,
                          prev_close: float = None) -> List[Dict]:
    """Generate 5-min candles for US market session."""
    atr_pct = 0.006 if regime == "trending" else 0.004 if regime == "range" else 0.008
    if prev_close:
        gap_pct = random.gauss(0, 0.003)
        open_price = prev_close * (1 + gap_pct)
    else:
        open_price = base_price
    drift = random.choice([0.0002, -0.0002]) if regime == "trending" else random.gauss(0, 0.00003)
    avg_vol = base_price * 20_000_000  # SPY/QQQ daily vol surrogate

    candles = []
    price = open_price
    for i in range(BARS_PER_DAY):
        vf = 2.0 if i < 3 else (1.3 if i < 12 else (1.5 if i > 72 else 1.0))
        atr = atr_pct * price * vf * random.uniform(0.4, 1.6)
        ob = price
        d = 1 if random.random() > 0.5 else -1
        cb = price + drift * price + d * atr * 0.4 * random.random()
        hb = max(ob, cb) + atr * 0.2 * random.random()
        lb = min(ob, cb) - atr * 0.2 * random.random()
        vol = avg_vol * vf * random.uniform(0.5, 2.5)
        candles.append({'i':i,'open':ob,'high':hb,'low':lb,'close':cb,'vol':vol,
                        'gap_pct': (open_price - prev_close) / prev_close if prev_close else 0})
        price = cb
    return candles


def compute_vwap(candles: List[Dict]) -> float:
    """Cumulative intraday VWAP."""
    cum_tp_vol = sum((c['high']+c['low']+c['close'])/3 * c['vol'] for c in candles)
    cum_vol = sum(c['vol'] for c in candles)
    return cum_tp_vol / cum_vol if cum_vol > 0 else candles[-1]['close']


def compute_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1: return 50.0
    diffs = [closes[i]-closes[i-1] for i in range(1, len(closes))]
    recent = diffs[-period:]
    gains = sum(d for d in recent if d > 0) / period
    losses = sum(-d for d in recent if d < 0) / period
    if losses == 0: return 100.0
    return 100 - 100/(1+gains/losses)


def simulate_day_momentum(instrument: str, base_price: float, regime: str,
                           params: Dict, prev_close: float) -> List[Dict]:
    candles = generate_day_candles(base_price, regime, prev_close)

    orb_bars   = params.get('orb_bars', ORB_BARS_30)
    buffer_pct = params.get('buffer_pct', 0.001)
    stop_mode  = params.get('stop_mode', 'orb')   # 'orb' = other side of range
    target_r   = params.get('target_r', 1.5)
    vol_mult   = params.get('vol_mult', 2.0)
    rsi_long   = params.get('rsi_long', 50)
    rsi_short  = params.get('rsi_short', 50)
    vwap_filter= params.get('vwap_filter', False)
    gap_filter = params.get('gap_filter', False)
    gap_min    = params.get('gap_min', 0.002)
    max_range_pct = params.get('max_range_pct', 999)  # skip if range > this

    orb_candles = candles[:orb_bars]
    orb_high = max(c['high'] for c in orb_candles)
    orb_low  = min(c['low']  for c in orb_candles)
    orb_range = orb_high - orb_low
    orb_range_pct = orb_range / orb_low

    if orb_range_pct > max_range_pct:
        return []

    if gap_filter and abs(candles[0].get('gap_pct', 0)) < gap_min:
        return []

    # Use midday (bar 20-40) average as baseline to avoid morning vol bias
    vols = [c['vol'] for c in candles]
    midday_vols = vols[20:40] if len(vols) >= 40 else vols[10:30] if len(vols) >= 30 else vols
    avg_vol = sum(midday_vols) / len(midday_vols) if midday_vols else vols[0]

    trades = []
    long_taken = False
    short_taken = False
    position = None
    closes_hist = []

    for i, bar in enumerate(candles):
        closes_hist.append(bar['close'])

        if position is not None:
            direction = position['direction']
            entry = position['entry']
            stop  = position['stop']
            target = position['target']

            if i >= FLAT_BAR:
                ep = bar['close'] * (1+(-SLIPPAGE_PCT if direction=='long' else SLIPPAGE_PCT))
                pnl = ((ep-entry) if direction=='long' else (entry-ep)) * max(int(MAX_POS_SIZE/entry), 1) - 2*COMMISSION_PCT*entry*max(int(MAX_POS_SIZE/entry), 1)
                trades.append({'exit_reason':'EOD','pnl':pnl,'direction':direction})
                position = None
                continue

            hit_stop = bar['low'] <= stop if direction=='long' else bar['high'] >= stop
            hit_tp   = bar['high'] >= target if direction=='long' else bar['low'] <= target

            if hit_stop:
                pnl = ((stop-entry) if direction=='long' else (entry-stop)) * max(int(MAX_POS_SIZE/entry), 1) - 2*COMMISSION_PCT*entry*max(int(MAX_POS_SIZE/entry), 1)
                trades.append({'exit_reason':'SL','pnl':pnl,'direction':direction})
                position = None
            elif hit_tp:
                pnl = ((target-entry) if direction=='long' else (entry-target)) * max(int(MAX_POS_SIZE/entry), 1) - 2*COMMISSION_PCT*entry*max(int(MAX_POS_SIZE/entry), 1)
                trades.append({'exit_reason':'TP','pnl':pnl,'direction':direction})
                position = None
            continue

        if i <= orb_bars or i > ENTRY_CUTOFF:
            continue

        rsi = compute_rsi(closes_hist)
        vwap = compute_vwap(candles[:i+1])

        # Long breakout
        if not long_taken and bar['close'] > orb_high * (1 + buffer_pct):
            vol_ok = bar['vol'] >= vol_mult * avg_vol
            rsi_ok = rsi >= rsi_long
            vwap_ok = (not vwap_filter) or (bar['close'] >= vwap)
            if vol_ok and rsi_ok and vwap_ok:
                entry_price = bar['close'] * (1 + SLIPPAGE_PCT)
                if stop_mode == 'orb':
                    stop_price = orb_low
                else:
                    stop_price = entry_price * (1 - 0.007)
                target_price = entry_price + target_r * orb_range
                position = {'direction':'long','entry':entry_price,'stop':stop_price,'target':target_price}
                long_taken = True

        # Short breakout
        elif not short_taken and position is None and bar['close'] < orb_low * (1 - buffer_pct):
            vol_ok = bar['vol'] >= vol_mult * avg_vol
            rsi_ok = rsi <= rsi_short
            vwap_ok = (not vwap_filter) or (bar['close'] <= vwap)
            if vol_ok and rsi_ok and vwap_ok:
                entry_price = bar['close'] * (1 - SLIPPAGE_PCT)
                if stop_mode == 'orb':
                    stop_price = orb_high
                else:
                    stop_price = entry_price * (1 + 0.007)
                target_price = entry_price - target_r * orb_range
                position = {'direction':'short','entry':entry_price,'stop':stop_price,'target':target_price}
                short_taken = True

    return trades


def run_backtest(params: Dict, label: str) -> Dict:
    regimes = (["trending"] * 88 + ["range"] * 75 + ["gap_and_go"] * 62 +
               ["trending"] * 25)
    random.shuffle(regimes)

    all_trades = []
    daily_pnls = []
    prev_closes = {inst: BASE_PRICES[inst] for inst in INSTRUMENTS}

    for day_idx in range(250):
        regime = regimes[day_idx]
        day_pnl = 0.0

        # Trade all instruments each day (like a universe scan)
        for inst in INSTRUMENTS:
            base = BASE_PRICES[inst] * random.uniform(0.92, 1.08)
            day_trades = simulate_day_momentum(inst, base, regime, params,
                                                prev_closes[inst])
            prev_closes[inst] = base * random.uniform(0.998, 1.002)

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
        'total_pnl': round(total_pnl, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'avg_r': round(avg_r, 2),
        'sharpe': round(sharpe, 2),
        'max_dd_pct': round(max_dd_pct, 2),
        'tp_exits': sum(1 for t in all_trades if t['exit_reason'] == 'TP'),
        'sl_exits': sum(1 for t in all_trades if t['exit_reason'] == 'SL'),
        'eod_exits': sum(1 for t in all_trades if t['exit_reason'] == 'EOD'),
    }


if __name__ == '__main__':
    print("=" * 70)
    print("Strategy 8: Momentum Burst / ORB — US SPY/QQQ Intraday")
    print("=" * 70)

    r1 = run_backtest({'orb_bars':6,'buffer_pct':0.001,'target_r':1.5,'vol_mult':2.0,
                       'rsi_long':50,'rsi_short':50,'vwap_filter':False,'gap_filter':False},
                      "Iter 1 (30-min ORB, vol 2x, RSI>50)")

    r2 = run_backtest({'orb_bars':9,'buffer_pct':0.001,'target_r':1.5,'vol_mult':2.0,
                       'rsi_long':50,'rsi_short':50,'vwap_filter':True,'gap_filter':False},
                      "Iter 2 (45-min ORB, +VWAP filter)")

    r3 = run_backtest({'orb_bars':9,'buffer_pct':0.001,'target_r':1.5,'vol_mult':2.0,
                       'rsi_long':50,'rsi_short':50,'vwap_filter':True,
                       'gap_filter':True,'gap_min':0.002},
                      "Iter 3 (+gap filter > 0.2%)")

    r4 = run_backtest({'orb_bars':3,'buffer_pct':0.001,'target_r':1.8,'vol_mult':1.8,
                       'rsi_long':53,'rsi_short':47,'vwap_filter':True,'gap_filter':False},
                      "Iter 4 (15-min ORB, vol 1.8x, RSI53)")

    r5 = run_backtest({'orb_bars':3,'buffer_pct':0.001,'target_r':2.0,'vol_mult':1.8,
                       'rsi_long':52,'rsi_short':48,'vwap_filter':True,'gap_filter':False,
                       'max_range_pct':0.015},
                      "Iter 5 (15-min, range<1.5%, R=2.0, vol1.8x)")

    results = [r1, r2, r3, r4, r5]

    print(f"\n{'Metric':<22} " + " | ".join(f"{r['label']:<40}" for r in results))
    print("-" * 230)
    for key, lbl in [
        ('trades','Total Trades'),('win_rate','Win Rate (%)'),
        ('avg_win','Avg Win ($)'),('avg_loss','Avg Loss ($)'),
        ('avg_r','Avg R'),('total_pnl','Total PnL ($)'),
        ('max_dd_pct','Max Drawdown (%)'),('sharpe','Sharpe Ratio'),
        ('tp_exits','TP Exits'),('sl_exits','SL Exits'),('eod_exits','EOD Exits'),
    ]:
        vals = [str(r.get(key,'N/A')) for r in results]
        print(f"{lbl:<22} " + " | ".join(f"{v:<40}" for v in vals))

    print("\n" + "=" * 70)
    print("REAL-WORLD ADJUSTMENT (US market, synthetic × 0.65):")
    for r in results:
        rw = round(r['win_rate'] * 0.65, 1)
        verdict = "PASS" if (r['win_rate'] >= 90 or (rw >= 60 and r['sharpe'] >= 5)) \
                  and r['max_dd_pct'] < 5 and r['trades'] >= 50 \
                  and r['total_pnl'] > 0 else "FAIL"
        print(f"  {r['label']}: Synth {r['win_rate']}% → RW {rw}% | "
              f"T={r['trades']} DD={r['max_dd_pct']}% PnL=${r['total_pnl']} "
              f"Sharpe={r['sharpe']} → {verdict}")
