#!/usr/bin/env python3
"""
ORB Tuning v3 — building on v2 winner (vol=2.0x, n=394, WR=56.9%, Sharpe=2.92, DD=9.96%)

New ideas tested (all stacked on the v2 base):
  P  Ticker filter: top-4 validated tickers only (BHARTIARTL, HDFCBANK, RELIANCE, AXISBANK)
  Q  Partial exit: close 50% at 1.5x target, trail rest to 2.5x (vs flat 2x)
  R  RSI(14) confirmation: RSI > 50 for longs, < 50 for shorts on breakout bar
  S  VWAP filter: price above VWAP for longs, below for shorts
  T  Stronger buffer: close > ORH*1.005 (vs 1.001) — require cleaner break
  U  Tighter entry window: 09:30-11:30 (morning momentum focus)
  V  ORB width 0.3-0.7% of price (tighter quality band)
  W  Volume acceleration: breakout bar volume > prev bar AND > 2x avg
  X  P+Q (ticker filter + partial exit)
  Y  P+R (ticker filter + RSI)
  Z  P+Q+R (all three top ideas)
  AA P+Q+U (ticker filter + partial + morning only)
  AB Q+R (partial + RSI, all tickers)
  AC Q+T (partial + stronger buffer)
"""
import sys, io, json, math, statistics, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_SIZE   = MARGIN * 0.20
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005

CACHE_DIR = Path(__file__).parent.parent / "data" / "history_cache"
IST       = timezone(timedelta(hours=5, minutes=30))

ALL_TICKERS = [
    "RELIANCE","HDFCBANK","ICICIBANK","INFY","TCS",
    "SBIN","AXISBANK","BHARTIARTL","WIPRO","TATASTEEL",
    "ONGC","NTPC","COALINDIA","BAJFINANCE",
]
TOP4 = {"BHARTIARTL", "HDFCBANK", "RELIANCE", "AXISBANK"}

YF_BASE = "https://query2.finance.yahoo.com/v8/finance/chart"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def fetch_raw(ticker: str) -> list[dict]:
    cache = CACHE_DIR / f"{ticker}_5min_v8.json"
    if cache.exists() and (time.time() - cache.stat().st_mtime) / 3600 < 48:
        return json.loads(cache.read_text())
    import urllib.request
    url = f"{YF_BASE}/{ticker}.NS?interval=5m&range=58d"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                raw = json.loads(r.read())
            break
        except Exception as e:
            if attempt == 2:
                return []
            time.sleep(3)
    try:
        res = raw["chart"]["result"][0]
        ts  = res["timestamp"]
        q   = res["indicators"]["quote"][0]
        bars = []
        for i, t in enumerate(ts):
            o,h,l,c,v = q["open"][i],q["high"][i],q["low"][i],q["close"][i],q["volume"][i]
            if None in (o,h,l,c): continue
            dt = datetime.fromtimestamp(t, tz=IST)
            hm = dt.hour*100 + dt.minute
            if hm < 915 or hm > 1515: continue
            bars.append({"ts":t,"dt":dt.isoformat(),"open":o,"high":h,"low":l,"close":c,"volume":v or 0})
        cache.write_text(json.dumps(bars))
        return bars
    except:
        return []


def split_days(bars: list[dict]) -> list[list[dict]]:
    from collections import defaultdict
    buckets = defaultdict(list)
    for b in bars:
        buckets[datetime.fromisoformat(b["dt"]).date().isoformat()].append(b)
    return [sorted(v, key=lambda x: x["ts"]) for k, v in sorted(buckets.items()) if len(v) >= 15]


def hhmm(bar: dict) -> int:
    dt = datetime.fromisoformat(bar["dt"])
    return dt.hour * 100 + dt.minute


def rolling_vol_avg(bars: list[dict], idx: int, window: int = 20) -> float:
    start = max(0, idx - window + 1)
    vols  = [bars[j]["volume"] for j in range(start, idx+1)]
    return sum(vols) / len(vols) if vols else 1.0


def calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_vwap(bars: list[dict]) -> float:
    tv = tp = 0.0
    for b in bars:
        typical = (b["high"] + b["low"] + b["close"]) / 3
        tv += typical * b["volume"]
        tp += b["volume"]
    return tv / tp if tp > 0 else 0.0


# ── ORB runner (v3 parameterised) ────────────────────────────────────────────

def run_orb_day(day_bars: list[dict], prev_close: float, params: dict) -> dict | None:
    vol_thresh     = params.get("vol_thresh",    2.0)   # v2 default
    target_mult    = params.get("target_mult",   2.0)
    entry_cutoff   = params.get("entry_cutoff",  1300)
    buf_pct        = params.get("buf_pct",       0.001)  # breakout buffer
    partial_exit   = params.get("partial_exit",  False)  # 50% at 1.5x, rest at 2.5x
    rsi_filter     = params.get("rsi_filter",    False)  # RSI>50 long, <50 short
    vwap_filter    = params.get("vwap_filter",   False)  # price vs VWAP
    vol_accel      = params.get("vol_accel",     False)  # also > prev bar vol
    width_filter   = params.get("width_filter",  False)  # (min_pct, max_pct)

    if len(day_bars) < 10:
        return None

    orh = max(b["high"] for b in day_bars[:3])
    orl = min(b["low"]  for b in day_bars[:3])
    orb_width = orh - orl
    if orb_width <= 0:
        return None

    open_px = day_bars[0]["open"]

    if width_filter:
        wf = params["width_filter"]
        width_pct = orb_width / open_px
        if width_pct < wf[0] or width_pct > wf[1]:
            return None

    long_entry_px  = orh * (1 + buf_pct)
    short_entry_px = orl * (1 - buf_pct)

    closes_so_far = [b["close"] for b in day_bars[:3]]

    for i in range(3, len(day_bars)):
        bar = day_bars[i]
        t   = hhmm(bar)
        if t < 930:
            closes_so_far.append(bar["close"])
            continue
        if t > entry_cutoff:
            break

        vol_avg = rolling_vol_avg(day_bars, i)
        vol_ok  = bar["volume"] > vol_thresh * vol_avg
        if vol_accel and i > 0:
            vol_ok = vol_ok and (bar["volume"] > day_bars[i-1]["volume"])

        closes_so_far.append(bar["close"])

        rsi_val = calc_rsi(closes_so_far) if rsi_filter else 50.0
        vwap_val = calc_vwap(day_bars[:i+1]) if vwap_filter else 0.0

        # Long setup
        if bar["close"] > long_entry_px and vol_ok:
            if rsi_filter and rsi_val <= 50:
                continue
            if vwap_filter and bar["close"] <= vwap_val:
                continue
            entry = long_entry_px * (1 + SLIPPAGE_PCT)
            stop  = orl
            tgt1  = entry + 1.5 * orb_width  # partial exit target
            tgt2  = entry + (2.5 if partial_exit else target_mult) * orb_width
            tgt_full = entry + target_mult * orb_width
            qty   = max(1, int(MAX_POS_SIZE / entry))

            if partial_exit:
                half = max(1, qty // 2)
                rest = qty - half
                partial_done = False
                partial_pnl  = 0.0
                active_qty   = qty
                stop_adj     = stop
                for j in range(i+1, len(day_bars)):
                    fb   = day_bars[j]
                    ft   = hhmm(fb)
                    cost_rate = (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    if ft >= 1510:
                        exit_px = fb["open"] * (1 - SLIPPAGE_PCT)
                        if partial_done:
                            pnl = partial_pnl + (exit_px - entry) * rest - entry * rest * cost_rate
                        else:
                            pnl = (exit_px - entry) * qty - entry * qty * cost_rate
                        return {"dir":"L","pnl":round(pnl,2),"exit":"EOD"}
                    if fb["low"] <= stop_adj:
                        exit_px = stop_adj
                        if partial_done:
                            pnl = partial_pnl + (exit_px - entry) * rest - entry * rest * cost_rate
                        else:
                            pnl = (exit_px - entry) * qty - entry * qty * cost_rate
                        return {"dir":"L","pnl":round(pnl,2),"exit":"SL"}
                    if not partial_done and fb["high"] >= tgt1:
                        partial_pnl = (tgt1 - entry) * half - entry * half * cost_rate
                        partial_done = True
                        stop_adj = entry  # move stop to breakeven
                    if partial_done and fb["high"] >= tgt2:
                        pnl = partial_pnl + (tgt2 - entry) * rest - entry * rest * cost_rate
                        return {"dir":"L","pnl":round(pnl,2),"exit":"TP"}
                return None
            else:
                for j in range(i+1, len(day_bars)):
                    fb   = day_bars[j]
                    ft   = hhmm(fb)
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    if ft >= 1510:
                        pnl = (fb["open"] * (1 - SLIPPAGE_PCT) - entry) * qty - cost
                        return {"dir":"L","pnl":round(pnl,2),"exit":"EOD"}
                    if fb["low"] <= stop:
                        pnl = (stop - entry) * qty - cost
                        return {"dir":"L","pnl":round(pnl,2),"exit":"SL"}
                    if fb["high"] >= tgt_full:
                        pnl = (tgt_full - entry) * qty - cost
                        return {"dir":"L","pnl":round(pnl,2),"exit":"TP"}
                return None

        # Short setup
        if bar["close"] < short_entry_px and vol_ok:
            if rsi_filter and rsi_val >= 50:
                continue
            if vwap_filter and bar["close"] >= vwap_val:
                continue
            entry = short_entry_px * (1 - SLIPPAGE_PCT)
            stop  = orh
            tgt1  = entry - 1.5 * orb_width
            tgt2  = entry - (2.5 if partial_exit else target_mult) * orb_width
            tgt_full = entry - target_mult * orb_width
            qty   = max(1, int(MAX_POS_SIZE / entry))

            if partial_exit:
                half = max(1, qty // 2)
                rest = qty - half
                partial_done = False
                partial_pnl  = 0.0
                stop_adj     = stop
                for j in range(i+1, len(day_bars)):
                    fb   = day_bars[j]
                    ft   = hhmm(fb)
                    cost_rate = (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    if ft >= 1510:
                        exit_px = fb["open"] * (1 + SLIPPAGE_PCT)
                        if partial_done:
                            pnl = partial_pnl + (entry - exit_px) * rest - entry * rest * cost_rate
                        else:
                            pnl = (entry - exit_px) * qty - entry * qty * cost_rate
                        return {"dir":"S","pnl":round(pnl,2),"exit":"EOD"}
                    if fb["high"] >= stop_adj:
                        exit_px = stop_adj
                        if partial_done:
                            pnl = partial_pnl + (entry - exit_px) * rest - entry * rest * cost_rate
                        else:
                            pnl = (entry - exit_px) * qty - entry * qty * cost_rate
                        return {"dir":"S","pnl":round(pnl,2),"exit":"SL"}
                    if not partial_done and fb["low"] <= tgt1:
                        partial_pnl = (entry - tgt1) * half - entry * half * cost_rate
                        partial_done = True
                        stop_adj = entry
                    if partial_done and fb["low"] <= tgt2:
                        pnl = partial_pnl + (entry - tgt2) * rest - entry * rest * cost_rate
                        return {"dir":"S","pnl":round(pnl,2),"exit":"TP"}
                return None
            else:
                for j in range(i+1, len(day_bars)):
                    fb   = day_bars[j]
                    ft   = hhmm(fb)
                    cost = entry * qty * (COMMISSION_PCT + SLIPPAGE_PCT) * 2
                    if ft >= 1510:
                        pnl = (entry - fb["open"] * (1 + SLIPPAGE_PCT)) * qty - cost
                        return {"dir":"S","pnl":round(pnl,2),"exit":"EOD"}
                    if fb["high"] >= stop:
                        pnl = (entry - stop) * qty - cost
                        return {"dir":"S","pnl":round(pnl,2),"exit":"SL"}
                    if fb["low"] <= tgt_full:
                        pnl = (entry - tgt_full) * qty - cost
                        return {"dir":"S","pnl":round(pnl,2),"exit":"TP"}
                return None

    return None


def run_config(all_days: dict, params: dict, tickers=None) -> list[dict]:
    trades = []
    use = tickers if tickers else list(all_days.keys())
    for ticker in use:
        if ticker not in all_days:
            continue
        days = all_days[ticker]
        for i, day_bars in enumerate(days):
            prev_close = days[i-1][-1]["close"] if i > 0 else 0.0
            r = run_orb_day(day_bars, prev_close, params)
            if r:
                trades.append({**r, "ticker": ticker})
    return trades


def metrics(trades: list) -> dict:
    if not trades:
        return {"n":0,"wr":0,"pnl":0,"sharpe":0,"max_dd":0,"avg_win":0,"avg_loss":0,"avg_r":0,"tp":0,"sl":0,"eod":0}
    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    pnls   = [t["pnl"] for t in trades]
    wr     = len(wins) / len(trades) * 100
    total  = sum(pnls)
    avg_w  = statistics.mean(t["pnl"] for t in wins)  if wins   else 0
    avg_l  = statistics.mean(t["pnl"] for t in losses) if losses else 0
    avg_r  = abs(avg_w / avg_l) if avg_l else float("inf")
    sharpe = (statistics.mean(pnls) / statistics.stdev(pnls) * math.sqrt(250)
              if len(pnls) > 1 and statistics.stdev(pnls) > 0 else 0)
    equity = peak = dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak: peak = equity
        if peak - equity > dd: dd = peak - equity
    return {
        "n": len(trades), "wr": round(wr,1), "pnl": round(total,0),
        "avg_win": round(avg_w,0), "avg_loss": round(avg_l,0),
        "avg_r": round(avg_r,2), "sharpe": round(sharpe,2),
        "max_dd": round(dd/CAPITAL*100,2),
        "tp":  sum(1 for t in trades if t.get("exit")=="TP"),
        "sl":  sum(1 for t in trades if t.get("exit")=="SL"),
        "eod": sum(1 for t in trades if t.get("exit")=="EOD"),
    }


V2_BASELINE = {
    "n":394, "wr":56.9, "pnl":13531, "sharpe":2.92,
    "max_dd":9.96, "avg_r":1.21, "tp":0, "sl":0, "eod":0
}


def score(m: dict, baseline: dict) -> float:
    if m["n"] < 30: return -999
    s  = (m["wr"]     - baseline["wr"])     * 2.0
    s += (m["avg_r"]  - baseline["avg_r"])  * 30.0
    s += (m["sharpe"] - baseline["sharpe"]) * 10.0
    s += (m["pnl"]    - baseline["pnl"])    / 500
    s -= (m["max_dd"] - baseline["max_dd"]) * 0.5
    return round(s, 2)


BASE_PARAMS = {
    "vol_thresh": 2.0, "target_mult": 2.0, "entry_cutoff": 1300,
    "buf_pct": 0.001, "partial_exit": False, "rsi_filter": False,
    "vwap_filter": False, "vol_accel": False, "width_filter": False,
}

def p(**kw):
    d = dict(BASE_PARAMS)
    d.update(kw)
    return d


def main():
    print("=" * 70)
    print("  ORB Tuning v3 — Building on v2 Winner (Vol 2.0x, 56.9% WR)")
    print("  v2 baseline: n=394, WR=56.9%, AvgR=1.21, PnL=Rs13531, Sharpe=2.92, DD=9.96%")
    print("=" * 70)

    print("\nLoading cached 5-min data...", flush=True)
    all_days = {}
    for ticker in ALL_TICKERS:
        bars = fetch_raw(ticker)
        if bars:
            all_days[ticker] = split_days(bars)
    print(f"  Loaded {len(all_days)} tickers")

    configs = {
        "v2 baseline (vol=2.0, all tickers)": (BASE_PARAMS, None),

        # --- Single-variable changes from v2 ---
        "P: Top-4 tickers only":
            (p(), list(TOP4)),

        "Q: Partial exit (50%@1.5x, 50%@2.5x)":
            (p(partial_exit=True), None),

        "R: RSI(14) confirmation":
            (p(rsi_filter=True), None),

        "S: VWAP filter":
            (p(vwap_filter=True), None),

        "T: Stronger buffer 0.5% (close>ORH*1.005)":
            (p(buf_pct=0.005), None),

        "U: Entry 09:30-11:30 only":
            (p(entry_cutoff=1130), None),

        "V: ORB width 0.3-0.7% quality band":
            (p(width_filter=(0.003, 0.007)), None),

        "W: Vol acceleration (also > prev bar)":
            (p(vol_accel=True), None),

        # --- Combinations ---
        "X: P+Q (top4 + partial exit)":
            (p(partial_exit=True), list(TOP4)),

        "Y: P+R (top4 + RSI)":
            (p(rsi_filter=True), list(TOP4)),

        "Z: P+Q+R (top4 + partial + RSI)":
            (p(partial_exit=True, rsi_filter=True), list(TOP4)),

        "AA: P+Q+U (top4 + partial + 11:30 cutoff)":
            (p(partial_exit=True, entry_cutoff=1130), list(TOP4)),

        "AB: Q+R (partial + RSI, all tickers)":
            (p(partial_exit=True, rsi_filter=True), None),

        "AC: Q+T (partial + strong buffer)":
            (p(partial_exit=True, buf_pct=0.005), None),

        "AD: Q+V (partial + width filter)":
            (p(partial_exit=True, width_filter=(0.003, 0.007)), None),

        "AE: P+Q+S (top4 + partial + VWAP)":
            (p(partial_exit=True, vwap_filter=True), list(TOP4)),

        "AF: Q+R+V (partial + RSI + width)":
            (p(partial_exit=True, rsi_filter=True, width_filter=(0.003, 0.007)), None),
    }

    results = {}
    for label, (params, tickers) in configs.items():
        trades = run_config(all_days, params, tickers)
        results[label] = metrics(trades)

    baseline_m = results["v2 baseline (vol=2.0, all tickers)"]

    print(f"\n{'Config':<46} {'N':>5} {'WR%':>6} {'AvgR':>6} {'PnL':>8} {'Shrp':>6} {'DD%':>6}  {'TP':>4}{'SL':>4}{'EOD':>5}  {'Score':>7}")
    print("-" * 115)

    scored = []
    for label, m in results.items():
        is_base = label.startswith("v2 baseline")
        s = score(m, V2_BASELINE)
        flag = " <--BASE" if is_base else (f"  +{s:.1f}" if s > 0 else f"   {s:.1f}")
        eod_pct = (m["eod"]/m["n"]*100) if m["n"] > 0 else 0
        print(f"  {label:<44} {m['n']:>5} {m['wr']:>5.1f}%  {m['avg_r']:>5.2f}  "
              f"Rs{m['pnl']:>7.0f}  {m['sharpe']:>5.2f}  {m['max_dd']:>5.2f}%"
              f"  {m['tp']:>4}{m['sl']:>4}{m['eod']:>5}  {flag}")
        if not is_base:
            scored.append((label, m, s, configs[label]))

    scored.sort(key=lambda x: -x[2])

    print(f"\n{'='*70}")
    print(f"  TOP 5 CONFIGS BY COMPOSITE SCORE")
    print(f"{'='*70}")
    for rank, (label, m, s, cfg_data) in enumerate(scored[:5], 1):
        params, tickers = cfg_data
        ticker_note = f"tickers={list(tickers)}" if tickers else "all 14 tickers"
        wr_delta = m["wr"] - V2_BASELINE["wr"]
        pnl_delta = m["pnl"] - V2_BASELINE["pnl"]
        sharpe_delta = m["sharpe"] - V2_BASELINE["sharpe"]
        print(f"\n  #{rank} {label}  [score={s:+.1f}]")
        print(f"     n={m['n']}  WR={m['wr']}% ({wr_delta:+.1f}pp)  AvgR={m['avg_r']}  "
              f"PnL=Rs{m['pnl']} ({pnl_delta:+.0f})  Sharpe={m['sharpe']} ({sharpe_delta:+.2f})  DD={m['max_dd']}%")
        print(f"     TP={m['tp']}  SL={m['sl']}  EOD={m['eod']}  ({ticker_note})")

    best_label, best_m, best_score, best_cfg = scored[0]
    best_params, best_tickers = best_cfg

    print(f"\n{'='*70}")
    print(f"  WINNER vs V2 BASELINE")
    print(f"{'='*70}")
    print(f"\n  {'Metric':<22} {'v2 Baseline':>12} {'v3 Best':>12} {'Delta':>10}")
    print(f"  {'-'*60}")
    for metric, fmt in [("n","{}"),("wr","{:.1f}%"),("avg_r","{:.2f}"),
                         ("pnl","Rs{:.0f}"),("sharpe","{:.2f}"),("max_dd","{:.2f}%")]:
        bv = V2_BASELINE[metric]
        wv = best_m[metric]
        if metric == "n":
            delta_str = f"{wv-bv:+d}"
        else:
            delta_str = f"{wv-bv:+.2f}"
        print(f"  {metric:<22} {str(bv):>12} {str(wv):>12} {delta_str:>10}")

    print(f"\n  Composite score vs v2: {best_score:+.1f}")

    print(f"\n  v3 proposed config:")
    for k, v in best_params.items():
        if k != "gap_align":
            print(f"    {k:<18}: {v}")
    if best_tickers:
        print(f"    {'ticker_filter':<18}: {sorted(best_tickers)}")

    # Assess statistical confidence
    n = best_m["n"]
    wr = best_m["wr"] / 100
    se = math.sqrt(wr * (1-wr) / n)
    ci95 = 1.96 * se * 100
    print(f"\n  Statistical check:")
    print(f"    n={n}  WR={best_m['wr']}% ± {ci95:.1f}pp (95% CI)")
    print(f"    Lower bound: {best_m['wr']-ci95:.1f}%  Upper bound: {best_m['wr']+ci95:.1f}%")
    if best_m["wr"] - ci95 > 50:
        print(f"    => Lower CI bound > 50%: STATISTICALLY SIGNIFICANT positive edge")
    else:
        print(f"    => Lower CI bound <= 50%: edge not statistically confirmed at 95% CI")

    print()


main()
