#!/usr/bin/env python3
"""
ORB Strategy Tuning Study — real NSE 5-min data.
Baseline: 52.0% WR, AvgR 1.10, PnL +Rs7,166, Sharpe 1.10, DD 15.75%
                   TP=71  SL=89  EOD=386  (71% of exits are EOD — target too far)

Tested enhancements:
  A  Target 1.5x (vs 2x)           — reduce EOD exits, more TP hits
  B  Entry window 09:30-11:00       — morning momentum only
  C  Gap-direction alignment         — trade only in gap direction
  D  ORB width quality filter        — skip too-narrow or too-wide ranges
  E  Vol surge 2x (vs 1.5x)         — stronger confirmation
  F  Trend filter: close > 5-bar EMA — intraday trend aligned
  G  Combined best (A+B+C+D)
  H  Combined tightest (A+B+C+D+E)
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

TICKERS = [
    "RELIANCE","HDFCBANK","ICICIBANK","INFY","TCS",
    "SBIN","AXISBANK","BHARTIARTL","WIPRO","TATASTEEL",
    "ONGC","NTPC","COALINDIA","BAJFINANCE",
]

YF_BASE = "https://query2.finance.yahoo.com/v8/finance/chart"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


# ── Data helpers ──────────────────────────────────────────────────────────────

def fetch_raw(ticker: str) -> list[dict]:
    cache = CACHE_DIR / f"{ticker}_5min_v8.json"
    if cache.exists() and (time.time() - cache.stat().st_mtime) / 3600 < 12:
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


def ema(values: list[float], period: int) -> float:
    if not values: return 0.0
    k = 2.0 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


# ── ORB runner (parameterised) ────────────────────────────────────────────────

def run_orb_day(day_bars: list[dict], prev_close: float, params: dict) -> dict | None:
    target_mult   = params.get("target_mult",   2.0)
    vol_thresh    = params.get("vol_thresh",    1.5)
    entry_cutoff  = params.get("entry_cutoff",  1300)
    gap_align     = params.get("gap_align",     False)
    width_filter  = params.get("width_filter",  False)  # (min_pct, max_pct)
    trend_filter  = params.get("trend_filter",  False)

    if len(day_bars) < 10:
        return None

    orh = max(b["high"] for b in day_bars[:3])
    orl = min(b["low"]  for b in day_bars[:3])
    orb_width = orh - orl
    if orb_width <= 0:
        return None

    open_px = day_bars[0]["open"]

    # ── Filter A: ORB width quality
    if width_filter:
        wf = params["width_filter"]
        width_pct = orb_width / open_px
        if width_pct < wf[0] or width_pct > wf[1]:
            return None

    # ── Filter C: Gap-direction alignment
    gap_up = prev_close > 0 and open_px > prev_close

    long_ok  = True
    short_ok = True
    if gap_align and prev_close > 0:
        long_ok  = open_px >= prev_close   # only long if gap-up or flat
        short_ok = open_px <= prev_close   # only short if gap-down or flat

    long_entry_px  = orh * 1.001
    short_entry_px = orl * 0.999

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

        closes_so_far.append(bar["close"])

        # ── Filter F: Intraday trend (close > 5-bar EMA = uptrend)
        if trend_filter:
            ema5 = ema(closes_so_far[-5:], 5) if len(closes_so_far) >= 5 else closes_so_far[-1]

        # Long
        if long_ok and bar["close"] > long_entry_px and vol_ok:
            if trend_filter and bar["close"] < ema5:
                continue
            entry = long_entry_px * (1 + SLIPPAGE_PCT)
            stop  = orl
            tgt   = entry + target_mult * orb_width
            qty   = max(1, int(MAX_POS_SIZE / entry))
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
                if fb["high"] >= tgt:
                    pnl = (tgt - entry) * qty - cost
                    return {"dir":"L","pnl":round(pnl,2),"exit":"TP"}
            return None

        # Short
        if short_ok and bar["close"] < short_entry_px and vol_ok:
            if trend_filter and bar["close"] > ema5:
                continue
            entry = short_entry_px * (1 - SLIPPAGE_PCT)
            stop  = orh
            tgt   = entry - target_mult * orb_width
            qty   = max(1, int(MAX_POS_SIZE / entry))
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
                if fb["low"] <= tgt:
                    pnl = (entry - tgt) * qty - cost
                    return {"dir":"S","pnl":round(pnl,2),"exit":"TP"}
            return None

    return None


# ── Run full backtest for one config ──────────────────────────────────────────

def run_config(all_days_by_ticker: dict, params: dict) -> list[dict]:
    trades = []
    for ticker, days in all_days_by_ticker.items():
        for i, day_bars in enumerate(days):
            prev_close = days[i-1][-1]["close"] if i > 0 else 0.0
            r = run_orb_day(day_bars, prev_close, params)
            if r:
                trades.append({**r, "ticker": ticker})
    return trades


# ── Metrics ───────────────────────────────────────────────────────────────────

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


def score(m: dict, baseline: dict) -> float:
    """Composite improvement score vs baseline. Higher = better."""
    if m["n"] < 20: return -999
    s  = (m["wr"]     - baseline["wr"])     * 2.0   # WR improvement counts 2x
    s += (m["avg_r"]  - baseline["avg_r"])  * 30.0  # AvgR improvement
    s += (m["sharpe"] - baseline["sharpe"]) * 10.0  # Sharpe
    s += (m["pnl"]    - baseline["pnl"])    / 500   # absolute PnL
    s -= (m["max_dd"] - baseline["max_dd"]) * 0.5   # penalise higher DD
    return round(s, 2)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 68)
    print("  ORB Strategy Tuning Study — Real NSE 5-min Data")
    print("  Baseline: 52.0% WR | AvgR 1.10 | PnL +Rs7,166 | Sharpe 1.10")
    print("  Problem : 71% of exits are EOD (target=2x too far)")
    print("=" * 68)

    print("\nLoading cached 5-min data...", flush=True)
    all_days_by_ticker = {}
    for ticker in TICKERS:
        bars = fetch_raw(ticker)
        if bars:
            all_days_by_ticker[ticker] = split_days(bars)
    print(f"  Loaded {len(all_days_by_ticker)} tickers")

    # ── Define iterations ─────────────────────────────────────────────────────
    configs = {
        "Baseline (2x, 1.5xvol, 09:30-13:00)": {
            "target_mult": 2.0, "vol_thresh": 1.5, "entry_cutoff": 1300,
            "gap_align": False, "width_filter": False, "trend_filter": False,
        },
        "A: Target 1.5x": {
            "target_mult": 1.5, "vol_thresh": 1.5, "entry_cutoff": 1300,
            "gap_align": False, "width_filter": False, "trend_filter": False,
        },
        "B: Entry 09:30-11:00 only": {
            "target_mult": 2.0, "vol_thresh": 1.5, "entry_cutoff": 1100,
            "gap_align": False, "width_filter": False, "trend_filter": False,
        },
        "C: Gap-direction align": {
            "target_mult": 2.0, "vol_thresh": 1.5, "entry_cutoff": 1300,
            "gap_align": True, "width_filter": False, "trend_filter": False,
        },
        "D: ORB width 0.2-0.8% of price": {
            "target_mult": 2.0, "vol_thresh": 1.5, "entry_cutoff": 1300,
            "gap_align": False, "width_filter": (0.002, 0.008), "trend_filter": False,
        },
        "E: Vol 2.0x surge": {
            "target_mult": 2.0, "vol_thresh": 2.0, "entry_cutoff": 1300,
            "gap_align": False, "width_filter": False, "trend_filter": False,
        },
        "F: Intraday trend (EMA5)": {
            "target_mult": 2.0, "vol_thresh": 1.5, "entry_cutoff": 1300,
            "gap_align": False, "width_filter": False, "trend_filter": True,
        },
        "G: A+B (1.5x tgt + 11:00 cutoff)": {
            "target_mult": 1.5, "vol_thresh": 1.5, "entry_cutoff": 1100,
            "gap_align": False, "width_filter": False, "trend_filter": False,
        },
        "H: A+B+C (1.5x+11:00+gap align)": {
            "target_mult": 1.5, "vol_thresh": 1.5, "entry_cutoff": 1100,
            "gap_align": True, "width_filter": False, "trend_filter": False,
        },
        "I: A+B+D (1.5x+11:00+width filt)": {
            "target_mult": 1.5, "vol_thresh": 1.5, "entry_cutoff": 1100,
            "gap_align": False, "width_filter": (0.002, 0.008), "trend_filter": False,
        },
        "J: A+B+C+D full combo": {
            "target_mult": 1.5, "vol_thresh": 1.5, "entry_cutoff": 1100,
            "gap_align": True, "width_filter": (0.002, 0.008), "trend_filter": False,
        },
        "K: A+B+C+D+E (tightest)": {
            "target_mult": 1.5, "vol_thresh": 2.0, "entry_cutoff": 1100,
            "gap_align": True, "width_filter": (0.002, 0.008), "trend_filter": False,
        },
        "L: J+trend filter": {
            "target_mult": 1.5, "vol_thresh": 1.5, "entry_cutoff": 1100,
            "gap_align": True, "width_filter": (0.002, 0.008), "trend_filter": True,
        },
        "M: 1.5x tgt + gap + EMA5": {
            "target_mult": 1.5, "vol_thresh": 1.5, "entry_cutoff": 1300,
            "gap_align": True, "width_filter": False, "trend_filter": True,
        },
    }

    results = {}
    for label, params in configs.items():
        trades = run_config(all_days_by_ticker, params)
        results[label] = metrics(trades)

    baseline = results["Baseline (2x, 1.5xvol, 09:30-13:00)"]

    # ── Print results table ───────────────────────────────────────────────────
    print(f"\n{'Config':<42} {'N':>5} {'WR%':>6} {'AvgR':>6} {'PnL':>8} {'Shrp':>6} {'DD%':>6}  {'TP':>4}{'SL':>4}{'EOD':>5}  {'Score':>6}")
    print("-" * 105)

    scored = []
    for label, m in results.items():
        s = score(m, baseline)
        is_base = label.startswith("Baseline")
        flag = " ◀BASE" if is_base else (f"  +{s:.1f}" if s > 0 else f"  {s:.1f}")
        print(f"  {label:<40} {m['n']:>5} {m['wr']:>5.1f}%  {m['avg_r']:>5.2f}  "
              f"Rs{m['pnl']:>6.0f}  {m['sharpe']:>5.2f}  {m['max_dd']:>5.2f}%"
              f"  {m['tp']:>4}{m['sl']:>4}{m['eod']:>5}  {flag}")
        if not is_base:
            scored.append((label, m, s))

    # ── Best config ───────────────────────────────────────────────────────────
    scored.sort(key=lambda x: -x[2])
    best_label, best_m, best_score = scored[0]

    print(f"\n{'='*68}")
    print(f"  WINNER: {best_label}")
    print(f"{'='*68}")
    print(f"\n  {'Metric':<22} {'Baseline':>12} {'Best':>12} {'Delta':>10}")
    print(f"  {'-'*58}")
    for metric, fmt in [("n","{}"),("wr","{:.1f}%"),("avg_r","{:.2f}"),
                         ("pnl","Rs{:.0f}"),("sharpe","{:.2f}"),("max_dd","{:.2f}%")]:
        bv = baseline[metric]
        wv = best_m[metric]
        delta = wv - bv
        delta_str = f"{'+'if delta>0 else ''}{delta:.2f}"
        print(f"  {metric:<22} {str(bv):>12} {str(wv):>12} {delta_str:>10}")

    print(f"\n  Exit breakdown  — Baseline: TP={baseline['tp']} SL={baseline['sl']} EOD={baseline['eod']}")
    print(f"                  — Best:     TP={best_m['tp']} SL={best_m['sl']} EOD={best_m['eod']}")

    eod_pct_base = baseline['eod'] / baseline['n'] * 100
    eod_pct_best = best_m['eod'] / best_m['n'] * 100
    print(f"  EOD rate: {eod_pct_base:.0f}% → {eod_pct_best:.0f}%  (target: reduce below 50%)")

    # ── Improvement verdict ───────────────────────────────────────────────────
    print(f"\n{'='*68}")
    print(f"  IMPROVEMENT SUMMARY")
    print(f"{'='*68}")
    improved = []
    if best_m["wr"]     > baseline["wr"]:     improved.append(f"WR {baseline['wr']}% → {best_m['wr']}%")
    if best_m["avg_r"]  > baseline["avg_r"]:  improved.append(f"AvgR {baseline['avg_r']} → {best_m['avg_r']}")
    if best_m["pnl"]    > baseline["pnl"]:    improved.append(f"PnL Rs{baseline['pnl']} → Rs{best_m['pnl']}")
    if best_m["sharpe"] > baseline["sharpe"]: improved.append(f"Sharpe {baseline['sharpe']} → {best_m['sharpe']}")
    if best_m["max_dd"] < baseline["max_dd"]: improved.append(f"MaxDD {baseline['max_dd']}% → {best_m['max_dd']}%")
    for item in improved:
        print(f"  ✅ {item}")
    regressed = []
    if best_m["wr"]     < baseline["wr"]:     regressed.append(f"WR {baseline['wr']}% → {best_m['wr']}%")
    if best_m["avg_r"]  < baseline["avg_r"]:  regressed.append(f"AvgR {baseline['avg_r']} → {best_m['avg_r']}")
    if best_m["pnl"]    < baseline["pnl"]:    regressed.append(f"PnL Rs{baseline['pnl']} → Rs{best_m['pnl']}")
    if best_m["max_dd"] > baseline["max_dd"]: regressed.append(f"MaxDD {baseline['max_dd']}% → {best_m['max_dd']}%")
    for item in regressed:
        print(f"  ⚠️  {item}")

    print(f"\n  Composite score vs baseline: +{best_score:.1f}")
    print(f"\n  Proposed config for TRADING-STRATEGY.md update:")
    best_p = configs[best_label]
    print(f"    target_mult  : {best_p['target_mult']}x")
    print(f"    vol_thresh   : {best_p['vol_thresh']}x")
    print(f"    entry_cutoff : {best_p['entry_cutoff']} IST")
    print(f"    gap_align    : {best_p['gap_align']}")
    print(f"    width_filter : {best_p['width_filter']}")
    print(f"    trend_filter : {best_p['trend_filter']}")
    print()


main()
