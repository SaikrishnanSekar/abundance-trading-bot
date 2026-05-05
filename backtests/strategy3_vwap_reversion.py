#!/usr/bin/env python3
"""
Strategy 3: VWAP Standard-Deviation Band Mean Reversion — NSE Intraday
=======================================================================
Source: Heavily discussed on Twitter/X by Indian quant handles including
        @AlgoTradingClub, @PyQuantLab (Medium), and international quant
        communities. Referenced on LinkedIn by @shubham.chaudhary, and
        verified by QuantifiedStrategies.com VWAP backtest (Profit Factor 1.692).
        Also described at https://www.fmz.com/lang/en/strategy/474675
        and https://www.trade2win.com/threads/vwap-deviation-reversion-strategy.237956/

Community claim: "Mean reversion to VWAP from 2-SD extension has ~63% reversion rate
                  intraday. Buying at lower 2-SD band: 61% WR with 1.4:1 reward/risk."

Strategy Rules (Base — Iteration 1):
  - Timeframe  : 5-min candles, NSE market hours 09:15–15:15 IST
  - VWAP       : Cumulative VWAP from session open (standard intraday VWAP)
  - Bands      : VWAP ± 2×(rolling 20-bar std of closes from session open)
  - Entry Long : Price closes BELOW lower 2-SD band → buy at next open
                 (price extended; mean-reversion expected)
  - Entry Short: Price closes ABOVE upper 2-SD band → short at next open
  - Stop Loss  : 1.5× the band width beyond entry (i.e., ~3-SD from VWAP)
  - Target     : VWAP (full reversion target)
  - Exit       : Close at VWAP reversion OR stop OR EOD flat at 15:10
  - Volume filter: None in base (Iter 1); added in Iter 2
  - Trend filter : None in base (Iter 1); added in Iter 2
  - Max entries  : 1 long + 1 short per ticker per day
  - No entries after 13:30; forced flat at 15:10

Backtest methodology:
  - Synthetic OHLCV data: 250 trading days × 50 Nifty 50 tickers
  - Realistic intraday VWAP and SD bands generated per session
  - Regime mix: 40% range/choppy (VWAP reversion works best), 35% trending
    (reversion may fail), 25% gap-and-go
  - Capital: ₹20,000 cash; MIS 5× = ₹1,00,000 margin
  - Position sizing: 20% of margin = ₹20,000 per position
  - Costs: 0.03% commission + 0.05% slippage each side
  - Daily loss cap: -₹300

Iteration 1: Base VWAP 2-SD reversion (no filters)
Iteration 2: Add volume confirmation (vol > 1.2× avg) + no-trend-day filter
             (skip if price walked the bands for 3+ consecutive bars same direction)
Iteration 3: Add RSI(14) < 35 for longs / RSI(14) > 65 for shorts as entry confirmation
             (requires genuine oversold/overbought condition beyond just band touch)
"""

import random
import math
import statistics
from typing import List, Dict, Tuple, Optional

random.seed(137)

# ── Constants ─────────────────────────────────────────────────────────────────
CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_PCT    = 0.20
MAX_POS_SIZE   = MARGIN * MAX_POS_PCT      # ₹20,000
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005
DAILY_LOSS_CAP = -300
BARS_PER_DAY   = 75     # 09:15–15:15 = 75 × 5-min bars (incl. 09:15 bar)
ENTRY_CUTOFF   = 53     # bar index 53 ≈ 13:30 (09:15 + 53×5min = 13:40)
FLAT_BAR       = 72     # bar index 72 ≈ 15:10 → force flat

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

# ── Data generation ───────────────────────────────────────────────────────────

def generate_day_candles(base_price: float, regime: str) -> List[Dict]:
    """Generate realistic 5-min OHLCV candles for one trading day."""
    atr_pct = 0.008 if regime == "trending" else 0.005 if regime == "range" else 0.010
    gap_pct = random.gauss(0, 0.004)
    open_price = base_price * (1 + gap_pct)

    # Intraday drift
    if regime == "trending":
        drift = random.choice([0.0002, -0.0002]) * random.uniform(0.5, 1.5)
    elif regime == "gap_and_go":
        drift = gap_pct * 0.03
    else:
        drift = random.gauss(0, 0.00005)

    candles = []
    price = open_price
    avg_vol = base_price * 50_000  # surrogate volume units

    for i in range(BARS_PER_DAY):
        # Morning volatility premium
        vol_factor = 1.8 if i < 6 else (1.2 if i < 18 else (0.8 if i > 60 else 1.0))
        bar_atr = atr_pct * price * vol_factor * random.uniform(0.5, 1.5)

        open_bar = price
        direction = 1 if random.random() > 0.5 else -1
        close_bar = price + drift * price + direction * bar_atr * 0.4 * random.random()
        high_bar = max(open_bar, close_bar) + bar_atr * 0.3 * random.random()
        low_bar  = min(open_bar, close_bar) - bar_atr * 0.3 * random.random()

        vol = avg_vol * vol_factor * random.uniform(0.6, 2.0)
        candles.append({
            'i': i, 'open': open_bar, 'high': high_bar,
            'low': low_bar, 'close': close_bar, 'vol': vol
        })
        price = close_bar

    return candles


def compute_vwap_bands(candles: List[Dict]) -> List[Dict]:
    """Compute cumulative intraday VWAP and 2-SD bands for each bar."""
    cum_tp_vol = 0.0
    cum_vol = 0.0
    closes = []
    result = []

    for c in candles:
        tp = (c['high'] + c['low'] + c['close']) / 3.0
        cum_tp_vol += tp * c['vol']
        cum_vol += c['vol']
        vwap = cum_tp_vol / cum_vol if cum_vol > 0 else c['close']
        closes.append(c['close'])

        # Rolling 20-bar std (or all bars if < 20 available)
        window = closes[-20:] if len(closes) >= 3 else closes
        std = statistics.stdev(window) if len(window) >= 2 else c['close'] * 0.001
        band_width = 2.0 * std

        result.append({
            **c,
            'vwap': vwap,
            'band_upper': vwap + band_width,
            'band_lower': vwap - band_width,
            'std': std
        })
    return result


def compute_rsi(closes: List[float], period: int = 14) -> float:
    """Compute RSI for the most recent bar."""
    if len(closes) < period + 1:
        return 50.0
    diffs = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    recent = diffs[-(period):]
    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]
    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 1e-9
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def is_band_walking(candles_with_bands: List[Dict], direction: str, lookback: int = 3) -> bool:
    """Check if price has been consistently walking a band (trending day signal)."""
    if len(candles_with_bands) < lookback:
        return False
    recent = candles_with_bands[-lookback:]
    if direction == "up":
        return all(c['close'] > c['band_upper'] for c in recent)
    else:
        return all(c['close'] < c['band_lower'] for c in recent)


# ── Single day simulation ─────────────────────────────────────────────────────

def simulate_day_vwap(ticker: str, base_price: float, regime: str,
                      params: Dict) -> List[Dict]:
    """Simulate VWAP reversion trades for one ticker on one day."""
    candles = generate_day_candles(base_price, regime)
    data = compute_vwap_bands(candles)

    sd_mult    = params.get('sd_mult', 2.0)
    stop_mult  = params.get('stop_mult', 1.5)   # extra std beyond entry
    vol_filter = params.get('vol_filter', False)
    vol_thresh = params.get('vol_thresh', 1.2)
    rsi_filter = params.get('rsi_filter', False)
    rsi_lo     = params.get('rsi_lo', 35)
    rsi_hi     = params.get('rsi_hi', 65)
    trend_filter = params.get('trend_filter', False)

    # Compute avg volume for vol filter
    vols = [c['vol'] for c in data]
    avg_vol_20 = sum(vols[:20]) / 20 if len(vols) >= 20 else sum(vols) / len(vols)

    trades = []
    long_taken = False
    short_taken = False
    position = None  # {'direction','entry','stop','target','entry_bar'}
    closes_so_far = []

    for idx, bar in enumerate(data):
        closes_so_far.append(bar['close'])

        # Check for open position exit
        if position is not None:
            direction = position['direction']
            entry = position['entry']
            stop = position['stop']
            target = position['target']

            # Force flat at FLAT_BAR
            if idx >= FLAT_BAR:
                exit_price = bar['close'] * (1 + (-SLIPPAGE_PCT if direction == 'long' else SLIPPAGE_PCT))
                raw_pnl = (exit_price - entry) if direction == 'long' else (entry - exit_price)
                shares = int(MAX_POS_SIZE / entry)
                pnl = raw_pnl * shares - 2 * COMMISSION_PCT * entry * shares
                trades.append({'exit_reason': 'EOD', 'pnl': pnl, 'direction': direction})
                position = None
                continue

            # Check stop
            hit_stop = (bar['low'] <= stop) if direction == 'long' else (bar['high'] >= stop)
            hit_target = (bar['high'] >= target) if direction == 'long' else (bar['low'] <= target)

            if hit_stop:
                exit_price = stop
                raw_pnl = (exit_price - entry) if direction == 'long' else (entry - exit_price)
                shares = int(MAX_POS_SIZE / entry)
                pnl = raw_pnl * shares - 2 * COMMISSION_PCT * entry * shares
                trades.append({'exit_reason': 'SL', 'pnl': pnl, 'direction': direction})
                position = None
            elif hit_target:
                exit_price = target
                raw_pnl = (exit_price - entry) if direction == 'long' else (entry - exit_price)
                shares = int(MAX_POS_SIZE / entry)
                pnl = raw_pnl * shares - 2 * COMMISSION_PCT * entry * shares
                trades.append({'exit_reason': 'TP', 'pnl': pnl, 'direction': direction})
                position = None
            continue

        # Entry logic — only when no open position
        if idx < 5 or idx > ENTRY_CUTOFF:
            continue

        # Recompute bands with sd_mult
        band_upper = bar['vwap'] + sd_mult * bar['std']
        band_lower = bar['vwap'] - sd_mult * bar['std']
        band_width = sd_mult * bar['std']

        # Long setup: close below lower band
        if not long_taken and bar['close'] < band_lower:
            # Trend filter: avoid band-walking days
            if trend_filter and is_band_walking(data[:idx+1], "down", 3):
                continue
            # Volume filter
            if vol_filter and bar['vol'] < vol_thresh * avg_vol_20:
                continue
            # RSI filter
            if rsi_filter:
                rsi = compute_rsi(closes_so_far, 14)
                if rsi >= rsi_lo:
                    continue

            entry_price = data[idx+1]['open'] * (1 + SLIPPAGE_PCT) if idx+1 < len(data) else bar['close'] * (1 + SLIPPAGE_PCT)
            stop_price = entry_price - stop_mult * band_width
            target_price = bar['vwap']  # full reversion to VWAP

            if target_price <= entry_price:
                continue

            position = {'direction': 'long', 'entry': entry_price,
                        'stop': stop_price, 'target': target_price,
                        'entry_bar': idx+1}
            long_taken = True

        # Short setup: close above upper band
        elif not short_taken and bar['close'] > band_upper:
            if trend_filter and is_band_walking(data[:idx+1], "up", 3):
                continue
            if vol_filter and bar['vol'] < vol_thresh * avg_vol_20:
                continue
            if rsi_filter:
                rsi = compute_rsi(closes_so_far, 14)
                if rsi <= rsi_hi:
                    continue

            entry_price = data[idx+1]['open'] * (1 - SLIPPAGE_PCT) if idx+1 < len(data) else bar['close'] * (1 - SLIPPAGE_PCT)
            stop_price = entry_price + stop_mult * band_width
            target_price = bar['vwap']

            if target_price >= entry_price:
                continue

            position = {'direction': 'short', 'entry': entry_price,
                        'stop': stop_price, 'target': target_price,
                        'entry_bar': idx+1}
            short_taken = True

    return trades


# ── Full backtest ─────────────────────────────────────────────────────────────

def run_backtest(params: Dict, label: str) -> Dict:
    """Run the full VWAP reversion backtest across 250 days × 50 tickers."""
    regimes = (["trending"] * 88 + ["range"] * 75 + ["gap_and_go"] * 62 +
               ["trending"] * 25)  # total = 250
    random.shuffle(regimes)

    all_trades = []
    daily_pnls = []

    for day_idx in range(250):
        regime = regimes[day_idx]
        day_pnl = 0.0

        # Simulate 10 tickers per day (capital constraint)
        tickers_today = random.sample(NIFTY50_TICKERS, 10)
        for ticker in tickers_today:
            base = TICKER_PRICES[ticker] * random.uniform(0.85, 1.15)
            day_trades = simulate_day_vwap(ticker, base, regime, params)
            for t in day_trades:
                all_trades.append(t)
                day_pnl += t['pnl']
                if day_pnl <= DAILY_LOSS_CAP:
                    break  # daily loss cap hit
            if day_pnl <= DAILY_LOSS_CAP:
                break

        daily_pnls.append(day_pnl)

    # ── Metrics ───────────────────────────────────────────────────────────────
    if not all_trades:
        return {'label': label, 'trades': 0, 'win_rate': 0, 'total_pnl': 0,
                'sharpe': 0, 'max_dd_pct': 0, 'avg_r': 0,
                'avg_win': 0, 'avg_loss': 0, 'tp_exits': 0, 'sl_exits': 0, 'eod_exits': 0}

    wins = [t for t in all_trades if t['pnl'] > 0]
    losses = [t for t in all_trades if t['pnl'] <= 0]

    win_rate = len(wins) / len(all_trades) * 100
    total_pnl = sum(t['pnl'] for t in all_trades)
    avg_win = statistics.mean(t['pnl'] for t in wins) if wins else 0
    avg_loss = statistics.mean(t['pnl'] for t in losses) if losses else 0
    avg_r = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

    # Sharpe (daily PnL)
    if len(daily_pnls) > 1 and statistics.stdev(daily_pnls) > 0:
        sharpe = (statistics.mean(daily_pnls) / statistics.stdev(daily_pnls)) * math.sqrt(252)
    else:
        sharpe = 0.0

    # Max drawdown (running equity curve)
    equity = 0.0
    peak = 0.0
    max_dd_abs = 0.0
    for dp in daily_pnls:
        equity += dp
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd_abs:
            max_dd_abs = dd
    max_dd_pct = (max_dd_abs / CAPITAL) * 100 if CAPITAL > 0 else 0

    tp_exits = sum(1 for t in all_trades if t['exit_reason'] == 'TP')
    sl_exits = sum(1 for t in all_trades if t['exit_reason'] == 'SL')
    eod_exits = sum(1 for t in all_trades if t['exit_reason'] == 'EOD')

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
        'tp_exits': tp_exits,
        'sl_exits': sl_exits,
        'eod_exits': eod_exits,
    }


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("=" * 70)
    print("Strategy 3: VWAP Standard-Deviation Band Mean Reversion")
    print("=" * 70)

    # Iteration 1 — base: 2-SD bands, no filters
    params1 = {
        'sd_mult': 2.0, 'stop_mult': 1.5,
        'vol_filter': False, 'trend_filter': False, 'rsi_filter': False
    }
    r1 = run_backtest(params1, "Iter 1 (2-SD, no filters)")

    # Iteration 2 — add volume filter + trend-walk filter
    params2 = {
        'sd_mult': 2.0, 'stop_mult': 1.5,
        'vol_filter': True, 'vol_thresh': 1.2,
        'trend_filter': True, 'rsi_filter': False
    }
    r2 = run_backtest(params2, "Iter 2 (+vol 1.2x, +trend filter)")

    # Iteration 3 — add RSI oversold/overbought confirmation
    params3 = {
        'sd_mult': 2.0, 'stop_mult': 1.5,
        'vol_filter': True, 'vol_thresh': 1.2,
        'trend_filter': True,
        'rsi_filter': True, 'rsi_lo': 35, 'rsi_hi': 65
    }
    r3 = run_backtest(params3, "Iter 3 (+RSI 35/65 filter)")

    # Iteration 4 — tighter RSI threshold + wider band (2.5-SD)
    params4 = {
        'sd_mult': 2.5, 'stop_mult': 1.5,
        'vol_filter': True, 'vol_thresh': 1.5,
        'trend_filter': True,
        'rsi_filter': True, 'rsi_lo': 30, 'rsi_hi': 70
    }
    r4 = run_backtest(params4, "Iter 4 (2.5-SD, vol 1.5x, RSI 30/70)")

    # Iteration 5 — very tight entry: 3-SD, RSI 25/75, high vol
    params5 = {
        'sd_mult': 3.0, 'stop_mult': 1.0,
        'vol_filter': True, 'vol_thresh': 2.0,
        'trend_filter': True,
        'rsi_filter': True, 'rsi_lo': 25, 'rsi_hi': 75
    }
    r5 = run_backtest(params5, "Iter 5 (3-SD, vol 2.0x, RSI 25/75)")

    results = [r1, r2, r3, r4, r5]

    print(f"\n{'Metric':<22} " + " | ".join(f"{r['label']:<36}" for r in results))
    print("-" * 200)
    for key, label in [
        ('trades', 'Total Trades'), ('win_rate', 'Win Rate (%)'),
        ('avg_win', 'Avg Win (₹)'), ('avg_loss', 'Avg Loss (₹)'),
        ('avg_r', 'Avg R'), ('total_pnl', 'Total PnL (₹)'),
        ('max_dd_pct', 'Max Drawdown (%)'), ('sharpe', 'Sharpe Ratio'),
        ('tp_exits', 'TP Exits'), ('sl_exits', 'SL Exits'), ('eod_exits', 'EOD Exits'),
    ]:
        vals = [str(r.get(key, 'N/A')) for r in results]
        print(f"{label:<22} " + " | ".join(f"{v:<36}" for v in vals))

    print("\n" + "=" * 70)
    print("REAL-WORLD ADJUSTMENT (synthetic WR × 0.65 estimate):")
    for r in results:
        rw = round(r['win_rate'] * 0.65, 1)
        verdict = "PASS" if (r['win_rate'] >= 90 or (rw >= 60 and r['sharpe'] >= 5)) \
                  and r['max_dd_pct'] < 5 and r['trades'] >= 50 \
                  and r['total_pnl'] > 0 else "FAIL"
        print(f"  {r['label']}: Synthetic {r['win_rate']}% → RW est. {rw}% | "
              f"Trades={r['trades']} DD={r['max_dd_pct']}% PnL=₹{r['total_pnl']} "
              f"Sharpe={r['sharpe']} → {verdict}")
