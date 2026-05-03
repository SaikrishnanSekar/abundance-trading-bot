#!/usr/bin/env python3
"""
Strategy 2: Supertrend + EMA Crossover — NSE intraday 5-min
=============================================================
Source: Widely shared on TradingView India and Twitter/X by systematic traders
        including @TraderRahulPal (9-21 EMA Nifty chart, May 2025),
        and multiple algo trading communities.
        Combined system from Medium article by @redsword_23261 (Quantitative Trading).

Strategy Rules:
  - Timeframe  : 5-min candles, NSE market hours 09:15–15:15 IST
  - Supertrend  : period=7, multiplier=3.0 (ATR-based)
  - EMA fast    : 9-bar EMA
  - EMA slow    : 21-bar EMA
  - Entry Long  : Supertrend bullish (green / price above ST line)
                  AND EMA9 crosses ABOVE EMA21 on current or prev bar
                  AND close > EMA21
  - Entry Short : Supertrend bearish (price below ST line)
                  AND EMA9 crosses BELOW EMA21
                  AND close < EMA21
  - Stop        : Supertrend line value at entry bar (dynamic)
                  Minimum stop = 1.5× ATR
  - Target      : 2× risk (R-multiple based)
  - Time filter : entries only 09:45–13:30; flat by 15:10
  - Max 1 trade per ticker per day; position closed if ST flips against it

Backtest methodology:
  - Same synthetic OHLCV framework as Strategy 1 (shared seed)
  - 1-year simulation: 250 trading days × Nifty 50 tickers (rotating 10/day)
  - Capital: ₹20,000; MIS 5× → ₹1,00,000 margin; max 20% per position; max 3 open
  - Commission: 0.03% per side; slippage: 0.05% per side

Iteration 1: Base parameters
  - ST period=7, multiplier=3.0
  - EMA fast=9, slow=21
  - Target = 2.0× risk

Iteration 2: Refined parameters
  - ST period=10, multiplier=2.5 — tighter trend definition
  - EMA fast=9, slow=21 (retained; good at identifying momentum)
  - Added: RSI(14) < 70 for longs, > 30 for shorts (avoids overextended entries)
  - Target = 2.5× risk (improved R-ratio)
  - Added: minimum ATR-based stop floor (0.5% of price) to avoid noise
"""

import random
import math
import statistics
from typing import List, Dict, Optional

# ── Reproducible seed ────────────────────────────────────────────────────────
random.seed(42)

# ── Constants ─────────────────────────────────────────────────────────────────
CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_PCT    = 0.20
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005
DAILY_LOSS_CAP = -300

NIFTY50_TICKERS = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS",
    "SBIN", "LT", "ITC", "AXISBANK", "KOTAKBANK",
    "BAJFINANCE", "HINDUNILVR", "BHARTIARTL", "MARUTI", "TITAN",
    "ASIANPAINT", "WIPRO", "SUNPHARMA", "NTPC", "POWERGRID",
    "ONGC", "COALINDIA", "TATASTEEL", "JSWSTEEL", "HINDALCO",
    "TATAMOTORS", "ULTRACEMCO", "MM", "HEROMOTOCO", "BAJAJ_AUTO",
    "BRITANNIA", "NESTLEIND", "CIPLA", "DRREDDY", "ADANIENT",
    "ADANIPORTS", "BPCL", "GRASIM", "HCLTECH", "TECHM",
    "LTIM", "EICHERMOT", "TATACONSUM", "SBILIFE", "HDFCLIFE",
    "BAJAJFINSV", "DIVISLAB", "APOLLOHOSP", "BEL", "TRENT"
]

TICKER_PRICES = {
    "RELIANCE": 1420, "HDFCBANK": 1720, "ICICIBANK": 1290, "INFY": 1650, "TCS": 3800,
    "SBIN": 820,  "LT": 3620, "ITC": 465, "AXISBANK": 1180, "KOTAKBANK": 1960,
    "BAJFINANCE": 7100, "HINDUNILVR": 2440, "BHARTIARTL": 1720, "MARUTI": 12800, "TITAN": 3300,
    "ASIANPAINT": 2380, "WIPRO": 280, "SUNPHARMA": 1780, "NTPC": 360, "POWERGRID": 320,
    "ONGC": 270, "COALINDIA": 430, "TATASTEEL": 160, "JSWSTEEL": 870, "HINDALCO": 640,
    "TATAMOTORS": 730, "ULTRACEMCO": 11200, "MM": 2980, "HEROMOTOCO": 5100, "BAJAJ_AUTO": 8900,
    "BRITANNIA": 5400, "NESTLEIND": 2230, "CIPLA": 1500, "DRREDDY": 1320, "ADANIENT": 2300,
    "ADANIPORTS": 1300, "BPCL": 310, "GRASIM": 2780, "HCLTECH": 1680, "TECHM": 1680,
    "LTIM": 4600, "EICHERMOT": 5600, "TATACONSUM": 1090, "SBILIFE": 1680, "HDFCLIFE": 760,
    "BAJAJFINSV": 1920, "DIVISLAB": 5400, "APOLLOHOSP": 7200, "BEL": 290, "TRENT": 5700
}

TICKER_ATR_PCT = {t: random.uniform(0.012, 0.025) for t in NIFTY50_TICKERS}


def generate_intraday_candles(base_price: float, atr_pct: float,
                               day_seed: int, regime: str = "trend") -> List[Dict]:
    """Generate 75 synthetic 5-min candles for one NSE trading day."""
    rng = random.Random(day_seed)
    candles = []
    daily_atr = base_price * atr_pct
    bar_vol   = daily_atr / math.sqrt(75)

    gap_pct   = rng.gauss(0, 0.008) if regime == "gap" else rng.gauss(0, 0.003)
    open_price = base_price * (1 + gap_pct)
    direction  = rng.choice([1, -1])
    trend_str  = rng.uniform(0.3, 1.0) if regime == "trend" else rng.uniform(0.0, 0.3)

    price = open_price
    for i in range(75):
        time_slot = 915 + i * 5
        if i < 6:
            vol_mult = rng.uniform(2.0, 4.0)
        elif i > 65:
            vol_mult = rng.uniform(1.2, 2.0)
        else:
            vol_mult = rng.uniform(0.6, 1.4)
        base_vol = int(base_price * 500 * vol_mult)

        trend_bias = direction * trend_str * bar_vol * 0.3
        noise = rng.gauss(0, bar_vol)
        step  = trend_bias + noise
        if regime == "range" and i > 40:
            step *= -0.3

        o = round(price, 2)
        c = round(price + step, 2)
        h = round(max(o, c) + abs(rng.gauss(0, bar_vol * 0.5)), 2)
        l = round(min(o, c) - abs(rng.gauss(0, bar_vol * 0.5)), 2)

        candles.append({"time": time_slot, "open": o, "high": h, "low": l, "close": c, "volume": base_vol})
        price = c

    return candles


def calc_ema(prices: List[float], period: int) -> List[float]:
    """Calculate EMA series. Returns same length with None for warmup."""
    if not prices:
        return []
    k = 2.0 / (period + 1)
    emas = [None] * len(prices)
    # seed first EMA with SMA
    if len(prices) >= period:
        emas[period - 1] = sum(prices[:period]) / period
        for i in range(period, len(prices)):
            emas[i] = prices[i] * k + emas[i-1] * (1 - k)
    return emas


def calc_atr(candles: List[Dict], period: int) -> List[Optional[float]]:
    """Calculate Wilder ATR."""
    trs = []
    for i, c in enumerate(candles):
        if i == 0:
            trs.append(c["high"] - c["low"])
        else:
            prev_close = candles[i-1]["close"]
            tr = max(c["high"] - c["low"],
                     abs(c["high"] - prev_close),
                     abs(c["low"]  - prev_close))
            trs.append(tr)

    atrs = [None] * len(trs)
    if len(trs) >= period:
        atrs[period-1] = sum(trs[:period]) / period
        for i in range(period, len(trs)):
            atrs[i] = (atrs[i-1] * (period - 1) + trs[i]) / period
    return atrs


def calc_supertrend(candles: List[Dict], period: int, multiplier: float) -> List[Dict]:
    """
    Calculate Supertrend indicator.
    Returns list of {'value': float, 'direction': 1 (bullish) or -1 (bearish)}
    """
    atrs = calc_atr(candles, period)
    results = [{"value": None, "direction": None}] * len(candles)

    upper_band = [None] * len(candles)
    lower_band = [None] * len(candles)
    st = [None] * len(candles)
    direction = [None] * len(candles)

    for i in range(period, len(candles)):
        if atrs[i] is None:
            continue

        hl2 = (candles[i]["high"] + candles[i]["low"]) / 2
        atr_val = atrs[i]
        ub = hl2 + multiplier * atr_val
        lb = hl2 - multiplier * atr_val

        if i == period:
            upper_band[i] = ub
            lower_band[i] = lb
        else:
            prev_ub = upper_band[i-1] if upper_band[i-1] is not None else ub
            prev_lb = lower_band[i-1] if lower_band[i-1] is not None else lb
            prev_close = candles[i-1]["close"]

            upper_band[i] = ub if (ub < prev_ub or prev_close > prev_ub) else prev_ub
            lower_band[i] = lb if (lb > prev_lb or prev_close < prev_lb) else prev_lb

        if st[i-1] is None:
            st[i] = upper_band[i]
            direction[i] = -1
        else:
            prev_st = st[i-1]
            prev_dir = direction[i-1]
            curr_close = candles[i]["close"]

            if prev_st == upper_band[i-1]:
                # was bearish
                if curr_close > upper_band[i]:
                    st[i] = lower_band[i]
                    direction[i] = 1
                else:
                    st[i] = upper_band[i]
                    direction[i] = -1
            else:
                # was bullish
                if curr_close < lower_band[i]:
                    st[i] = upper_band[i]
                    direction[i] = -1
                else:
                    st[i] = lower_band[i]
                    direction[i] = 1

        results[i] = {"value": round(st[i], 2) if st[i] else None, "direction": direction[i]}

    return results


def calc_rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Calculate RSI series."""
    rsi = [None] * len(closes)
    if len(closes) <= period:
        return rsi

    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    for i in range(period, len(closes)):
        if i == period:
            pass
        else:
            diff = closes[i] - closes[i-1]
            g = max(diff, 0)
            l = max(-diff, 0)
            avg_gain = (avg_gain * (period - 1) + g) / period
            avg_loss = (avg_loss * (period - 1) + l) / period

        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i] = round(100 - 100 / (1 + rs), 2)

    return rsi


def st_ema_backtest(
    st_period: int = 7,
    st_mult: float = 3.0,
    ema_fast: int = 9,
    ema_slow: int = 21,
    target_r_mult: float = 2.0,
    use_rsi_filter: bool = False,
    min_stop_pct: float = 0.003,
    trading_days: int = 250,
    label: str = "ST-EMA-Iter1"
) -> Dict:
    """Run Supertrend + EMA Crossover backtest."""

    all_trades = []
    daily_pnls = []

    for day_idx in range(trading_days):
        day_pnl = 0.0
        open_positions = 0

        day_seed_base = day_idx * 1000
        regime_roll = random.Random(day_idx).random()
        regime = "trend" if regime_roll < 0.45 else ("range" if regime_roll < 0.75 else "gap")

        vix = random.Random(day_idx + 9999).gauss(15, 4)
        if vix >= 20:
            daily_pnls.append(0.0)
            continue

        tickers_today = random.Random(day_idx).sample(NIFTY50_TICKERS, k=min(10, len(NIFTY50_TICKERS)))

        for ticker in tickers_today:
            if open_positions >= 3:
                break

            base_price = TICKER_PRICES.get(ticker, 1000)
            atr_pct    = TICKER_ATR_PCT.get(ticker, 0.018)
            candles    = generate_intraday_candles(base_price, atr_pct, day_seed_base + hash(ticker) % 997, regime)

            closes     = [c["close"] for c in candles]
            ema_f_list = calc_ema(closes, ema_fast)
            ema_s_list = calc_ema(closes, ema_slow)
            st_list    = calc_supertrend(candles, st_period, st_mult)
            rsi_list   = calc_rsi(closes, 14) if use_rsi_filter else [None]*len(closes)

            warmup = max(st_period + 5, ema_slow + 2, 20)
            trade_taken = False

            for i in range(warmup, len(candles)):
                c = candles[i]

                # Time gate: 09:45 to 13:30 only
                if c["time"] < 945 or c["time"] > 1330:
                    continue
                if trade_taken:
                    break
                if day_pnl <= DAILY_LOSS_CAP:
                    break

                ef_curr = ema_f_list[i]
                es_curr = ema_s_list[i]
                ef_prev = ema_f_list[i-1]
                es_prev = ema_s_list[i-1]
                st_curr = st_list[i]
                rsi_curr = rsi_list[i]

                if any(v is None for v in [ef_curr, es_curr, ef_prev, es_prev,
                                           st_curr.get("direction"), st_curr.get("value")]):
                    continue

                st_dir   = st_curr["direction"]
                st_val   = st_curr["value"]

                # Crossover detection
                bull_cross = (ef_curr > es_curr) and (ef_prev <= es_prev)
                bear_cross = (ef_curr < es_curr) and (ef_prev >= es_prev)

                # Also allow entry if cross happened in last 2 bars (cross-and-hold)
                if i >= 2:
                    ef_p2, es_p2 = ema_f_list[i-2], ema_s_list[i-2]
                    if ef_p2 is not None and es_p2 is not None:
                        bull_cross = bull_cross or ((ef_prev > es_prev) and (ef_p2 <= es_p2) and st_dir == 1)
                        bear_cross = bear_cross or ((ef_prev < es_prev) and (ef_p2 >= es_p2) and st_dir == -1)

                # Long condition
                if (st_dir == 1 and bull_cross and c["close"] > es_curr):
                    if use_rsi_filter and rsi_curr is not None and rsi_curr >= 70:
                        continue  # overextended

                    entry  = c["close"]
                    stop   = max(st_val, entry * (1 - 0.07))  # capped at 7%
                    stop_dist = entry - stop
                    if stop_dist < entry * min_stop_pct:
                        stop_dist = entry * min_stop_pct
                        stop = entry - stop_dist
                    target = entry + target_r_mult * stop_dist

                    max_cost = MARGIN * MAX_POS_PCT
                    qty = max(1, int(max_cost / entry))

                    exit_price = None
                    exit_reason = "EOD"
                    for j in range(i + 1, len(candles)):
                        fc = candles[j]
                        if fc["time"] >= 1510:
                            exit_price = fc["open"]
                            exit_reason = "EOD"
                            break
                        if fc["low"] <= stop:
                            exit_price = stop
                            exit_reason = "SL"
                            break
                        if fc["high"] >= target:
                            exit_price = target
                            exit_reason = "TP"
                            break
                        # Supertrend flip exit
                        st_j = st_list[j]
                        if st_j.get("direction") == -1:
                            exit_price = fc["close"]
                            exit_reason = "ST_FLIP"
                            break

                    if exit_price is None:
                        exit_price = candles[-1]["close"]
                        exit_reason = "EOD"

                    gross_pnl = (exit_price - entry) * qty
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    net_pnl = gross_pnl - cost

                    all_trades.append({
                        "day": day_idx, "ticker": ticker, "dir": "L",
                        "entry": entry, "exit": exit_price, "qty": qty,
                        "gross_pnl": round(gross_pnl, 2),
                        "net_pnl":   round(net_pnl, 2),
                        "exit_reason": exit_reason,
                        "regime": regime
                    })
                    day_pnl += net_pnl
                    open_positions += 1
                    trade_taken = True

                # Short condition
                elif (st_dir == -1 and bear_cross and c["close"] < es_curr):
                    if use_rsi_filter and rsi_curr is not None and rsi_curr <= 30:
                        continue

                    entry  = c["close"]
                    stop   = min(st_val, entry * (1 + 0.07))
                    stop_dist = stop - entry
                    if stop_dist < entry * min_stop_pct:
                        stop_dist = entry * min_stop_pct
                        stop = entry + stop_dist
                    target = entry - target_r_mult * stop_dist

                    max_cost = MARGIN * MAX_POS_PCT
                    qty = max(1, int(max_cost / entry))

                    exit_price = None
                    exit_reason = "EOD"
                    for j in range(i + 1, len(candles)):
                        fc = candles[j]
                        if fc["time"] >= 1510:
                            exit_price = fc["open"]
                            exit_reason = "EOD"
                            break
                        if fc["high"] >= stop:
                            exit_price = stop
                            exit_reason = "SL"
                            break
                        if fc["low"] <= target:
                            exit_price = target
                            exit_reason = "TP"
                            break
                        st_j = st_list[j]
                        if st_j.get("direction") == 1:
                            exit_price = fc["close"]
                            exit_reason = "ST_FLIP"
                            break

                    if exit_price is None:
                        exit_price = candles[-1]["close"]
                        exit_reason = "EOD"

                    gross_pnl = (entry - exit_price) * qty
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    net_pnl = gross_pnl - cost

                    all_trades.append({
                        "day": day_idx, "ticker": ticker, "dir": "S",
                        "entry": entry, "exit": exit_price, "qty": qty,
                        "gross_pnl": round(gross_pnl, 2),
                        "net_pnl":   round(net_pnl, 2),
                        "exit_reason": exit_reason,
                        "regime": regime
                    })
                    day_pnl += net_pnl
                    open_positions += 1
                    trade_taken = True

        daily_pnls.append(round(day_pnl, 2))

    # ── Metrics ────────────────────────────────────────────────────────────────
    total_trades = len(all_trades)
    if total_trades == 0:
        return {"label": label, "error": "no trades generated"}

    winners = [t for t in all_trades if t["net_pnl"] > 0]
    losers  = [t for t in all_trades if t["net_pnl"] <= 0]
    win_rate = len(winners) / total_trades * 100

    avg_win  = statistics.mean(t["net_pnl"] for t in winners) if winners else 0
    avg_loss = statistics.mean(t["net_pnl"] for t in losers)  if losers  else 0
    avg_r    = avg_win / abs(avg_loss) if avg_loss != 0 else float("inf")

    total_pnl = sum(t["net_pnl"] for t in all_trades)

    equity = CAPITAL
    peak   = CAPITAL
    max_dd = 0.0
    for dp in daily_pnls:
        equity += dp
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd

    non_zero = [p for p in daily_pnls if p != 0]
    if len(non_zero) > 1:
        mu    = statistics.mean(non_zero)
        sigma = statistics.stdev(non_zero)
        sharpe = (mu / sigma * math.sqrt(250)) if sigma > 0 else 0
    else:
        sharpe = 0.0

    gross_profit = sum(t["net_pnl"] for t in winners) if winners else 0
    gross_loss   = abs(sum(t["net_pnl"] for t in losers)) if losers else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    tp_count    = sum(1 for t in all_trades if t["exit_reason"] == "TP")
    sl_count    = sum(1 for t in all_trades if t["exit_reason"] == "SL")
    eod_count   = sum(1 for t in all_trades if t["exit_reason"] == "EOD")
    flip_count  = sum(1 for t in all_trades if t["exit_reason"] == "ST_FLIP")

    # Regime breakdown
    trend_wr = None
    range_wr = None
    trend_trades = [t for t in all_trades if t["regime"] == "trend"]
    range_trades = [t for t in all_trades if t["regime"] == "range"]
    if trend_trades:
        trend_wr = round(sum(1 for t in trend_trades if t["net_pnl"] > 0) / len(trend_trades) * 100, 1)
    if range_trades:
        range_wr = round(sum(1 for t in range_trades if t["net_pnl"] > 0) / len(range_trades) * 100, 1)

    return {
        "label":          label,
        "params": {
            "st_period":      st_period,
            "st_mult":        st_mult,
            "ema_fast":       ema_fast,
            "ema_slow":       ema_slow,
            "target_r_mult":  target_r_mult,
            "rsi_filter":     use_rsi_filter,
            "min_stop_pct":   min_stop_pct,
        },
        "total_trades":   total_trades,
        "win_rate_pct":   round(win_rate, 2),
        "avg_win_inr":    round(avg_win, 2),
        "avg_loss_inr":   round(avg_loss, 2),
        "avg_R":          round(avg_r, 3),
        "total_pnl_inr":  round(total_pnl, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio":   round(sharpe, 3),
        "profit_factor":  round(profit_factor, 3),
        "tp_exits":       tp_count,
        "sl_exits":       sl_count,
        "eod_exits":      eod_count,
        "st_flip_exits":  flip_count,
        "win_rate_in_trend": trend_wr,
        "win_rate_in_range": range_wr,
        "trading_days":   trading_days,
        "days_with_trades": sum(1 for p in daily_pnls if p != 0),
    }


def print_results(res: Dict):
    print(f"\n{'='*60}")
    print(f"  {res['label']}")
    print(f"{'='*60}")
    if "error" in res:
        print(f"  ERROR: {res['error']}")
        return
    p = res["params"]
    print(f"  Params   : ST({p['st_period']},{p['st_mult']}), EMA({p['ema_fast']}/{p['ema_slow']}), "
          f"tgt={p['target_r_mult']}R, RSI_filter={p['rsi_filter']}")
    print(f"  Trades   : {res['total_trades']} ({res['days_with_trades']} active days)")
    print(f"  Win Rate : {res['win_rate_pct']:.1f}%")
    print(f"  Avg Win  : ₹{res['avg_win_inr']:.0f}   Avg Loss: ₹{res['avg_loss_inr']:.0f}")
    print(f"  Avg R    : {res['avg_R']:.2f}")
    print(f"  Total PnL: ₹{res['total_pnl_inr']:.0f}")
    print(f"  Max DD   : {res['max_drawdown_pct']:.2f}%")
    print(f"  Sharpe   : {res['sharpe_ratio']:.3f}")
    print(f"  ProfitFactor: {res['profit_factor']:.3f}")
    print(f"  Exits    : TP={res['tp_exits']}  SL={res['sl_exits']}  EOD={res['eod_exits']}  ST_Flip={res['st_flip_exits']}")
    if res.get("win_rate_in_trend") is not None:
        print(f"  Regime WR: Trend={res['win_rate_in_trend']}%  Range={res['win_rate_in_range']}%")
    print()


if __name__ == "__main__":
    print("Running Supertrend + EMA Strategy Backtest — 250 trading days, Nifty 50 universe")
    print("Capital: ₹20,000 | MIS 5× | Max 20% margin/position | Max 3 simultaneous\n")

    # Iteration 1: Base parameters
    r1 = st_ema_backtest(
        st_period=7, st_mult=3.0,
        ema_fast=9, ema_slow=21,
        target_r_mult=2.0, use_rsi_filter=False,
        min_stop_pct=0.003,
        label="ST-EMA-Iter1 (ST(7,3.0), EMA9/21, 2.0R target, no RSI filter)"
    )
    print_results(r1)

    # Iteration 2: Refined
    r2 = st_ema_backtest(
        st_period=10, st_mult=2.5,
        ema_fast=9, ema_slow=21,
        target_r_mult=2.5, use_rsi_filter=True,
        min_stop_pct=0.005,
        label="ST-EMA-Iter2 (ST(10,2.5), EMA9/21, 2.5R target, RSI<70 filter)"
    )
    print_results(r2)

    print("\nKey insight:")
    print(f"  Iter1 → Iter2 Win Rate    : {r1['win_rate_pct']:.1f}% → {r2['win_rate_pct']:.1f}%")
    print(f"  Iter1 → Iter2 Sharpe      : {r1['sharpe_ratio']:.3f} → {r2['sharpe_ratio']:.3f}")
    print(f"  Iter1 → Iter2 MaxDD       : {r1['max_drawdown_pct']:.2f}% → {r2['max_drawdown_pct']:.2f}%")
    print(f"  Iter1 → Iter2 PnL         : ₹{r1['total_pnl_inr']:.0f} → ₹{r2['total_pnl_inr']:.0f}")
    print(f"  Iter1 → Iter2 ProfitFactor: {r1['profit_factor']:.3f} → {r2['profit_factor']:.3f}")
