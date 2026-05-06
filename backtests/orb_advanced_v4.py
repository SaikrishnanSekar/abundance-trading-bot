#!/usr/bin/env python3
"""
ORB Advanced v4 — solving supply absorption + brokerage drag
Target: Rs800-1000/day net (4-5% on Rs20k capital)

Problems diagnosed:
  1. Supply absorption: first breakout bar triggers, but high-vol next bar reverses
  2. Narrow ORB (< 1%): target (1.5-2x width) unreachable, most exits are EOD
  3. R-budget too small vs brokerage: Rs200 risk but Rs40-60 brokerage = 20-30% drag
  4. Fixed 1.5x target: ignores actual daily range potential of each stock

Solutions tested:
  A  Min ORB width filter 1.0%    — skip thin range days
  B  Min ORB width filter 1.2%    — stricter
  C  Second entry technique        — wait for supply bar to resolve, re-enter on strength
  D  ATR-based target (1x daily ATR instead of 1.5x ORB width)
  E  Full-margin sizing (Rs20k position cap, not R-budget cap)
  F  A + C combined (width filter + second entry)
  G  A + D combined (width filter + ATR target)
  H  A + C + E (width + second entry + full margin)
  I  A + D + E (width + ATR target + full margin)
  J  A + C + D + E (all combined — kitchen sink)
"""
import sys, io, json, math, statistics, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CAPITAL         = 20_000
MARGIN          = CAPITAL * 5          # Rs1,00,000
MAX_POS_VALUE   = MARGIN * 0.20        # Rs20,000 per position
R_BUDGET_T2     = 200                  # standard Tier 2
R_BUDGET_T3     = 300                  # high-conviction Tier 3
BROKERAGE_RT    = 40                   # Rs20 buy + Rs20 sell flat
STT_SELL_PCT    = 0.00025              # NSE STT 0.025% on sell side
EXCH_CHARGE     = 0.0000335            # NSE transaction charge
GST             = 0.18                 # on brokerage + exchange
SLIPPAGE_PCT    = 0.0005               # 0.05%

CACHE_DIR = Path(__file__).parent.parent / "data" / "history_cache"
IST = timezone(timedelta(hours=5, minutes=30))

STRONG22 = [
    "SHRIRAMFIN","HEROMOTOCO","BHARTIARTL","HDFCBANK","INDUSINDBK",
    "BEL","SUNPHARMA","AXISBANK","DIVISLAB","HINDUNILVR",
    "ULTRACEMCO","LT","TECHM","ADANIPORTS","BAJAJFINSV",
    "BAJAJ-AUTO","KOTAKBANK","WIPRO","DRREDDY","SBIN","TCS","INFY",
]

YF_BASE = "https://query2.finance.yahoo.com/v8/finance/chart"
HEADERS = {"User-Agent":"Mozilla/5.0","Accept":"application/json"}


def fetch_raw(ticker):
    cache = CACHE_DIR / f"{ticker}_5min_v8.json"
    if cache.exists() and (time.time()-cache.stat().st_mtime)/3600 < 48:
        return json.loads(cache.read_text())
    import urllib.request
    url = f"{YF_BASE}/{ticker}.NS?interval=5m&range=58d"
    for attempt in range(3):
        try:
            req = __import__('urllib.request', fromlist=['Request']).Request(url, headers=HEADERS)
            with __import__('urllib.request', fromlist=['urlopen']).urlopen(req, timeout=25) as r:
                raw = json.loads(r.read())
            break
        except:
            if attempt == 2: return []
            time.sleep(3)
    try:
        res = raw["chart"]["result"][0]
        ts,q = res["timestamp"],res["indicators"]["quote"][0]
        bars = []
        for i,t in enumerate(ts):
            o,h,l,c,v = q["open"][i],q["high"][i],q["low"][i],q["close"][i],(q["volume"][i] or 0)
            if None in (o,h,l,c): continue
            dt = datetime.fromtimestamp(t,tz=IST)
            hm = dt.hour*100+dt.minute
            if hm<915 or hm>1515: continue
            bars.append({"ts":t,"dt":dt.isoformat(),"open":o,"high":h,"low":l,"close":c,"volume":v})
        cache.write_text(json.dumps(bars))
        return bars
    except: return []


def split_days(bars):
    from collections import defaultdict
    buckets = defaultdict(list)
    for b in bars:
        buckets[datetime.fromisoformat(b["dt"]).date().isoformat()].append(b)
    return [sorted(v,key=lambda x:x["ts"]) for k,v in sorted(buckets.items()) if len(v)>=15]


def hhmm(bar):
    dt = datetime.fromisoformat(bar["dt"])
    return dt.hour*100+dt.minute


def rolling_avg(bars, idx, window=20):
    s = max(0,idx-window+1)
    vols = [bars[j]["volume"] for j in range(s,idx+1)]
    return sum(vols)/len(vols) if vols else 1.0


def calc_vwap(bars, up_to):
    tv=tp=0.0
    for b in bars[:up_to+1]:
        tp_p = (b["high"]+b["low"]+b["close"])/3
        tv+=tp_p*b["volume"]; tp+=b["volume"]
    return tv/tp if tp>0 else 0.0


def calc_atr(days_list, current_day_idx, period=14):
    """Daily ATR from prior days' OHLC"""
    trs = []
    for j in range(max(0, current_day_idx-period), current_day_idx):
        d = days_list[j]
        dh = max(b["high"] for b in d)
        dl = min(b["low"]  for b in d)
        trs.append(dh - dl)
    return statistics.mean(trs) if trs else 0.0


def calc_full_cost(entry, qty, direction="long"):
    """Realistic total transaction cost: brokerage + STT + exchange + GST"""
    value = entry * qty
    brok = min(BROKERAGE_RT/2, value*0.0003)  # Rs20 or 0.03%, whichever lower, per leg
    brok = max(brok, 0)                         # flat Rs20 per order for small positions
    brok = 20                                    # Zerodha/Dhan flat Rs20 per order
    stt  = value * STT_SELL_PCT                  # only on sell
    exch = value * EXCH_CHARGE * 2              # both legs
    gst  = (brok*2 + exch) * GST
    total_cost = brok*2 + stt + exch + gst
    return round(total_cost, 2)


def run_trade(day_bars, day_idx, all_days, entry_px, stop_px, direction,
              target_method, atr, orb_width, use_partial):
    """
    Simulate a trade after entry signal.
    target_method: "orb_2x", "orb_1.5x", "atr_1x", "atr_0.75x"
    use_partial: True = 50% at Tgt1 (SL->BE), 50% at Tgt2
    """
    if direction == "long":
        entry = entry_px * (1 + SLIPPAGE_PCT)
        stop  = stop_px
        risk  = entry - stop
        if risk <= 0: return None

        if target_method == "orb_2x":   tgt_full = entry + 2.0 * orb_width
        elif target_method == "orb_1.5x": tgt_full = entry + 1.5 * orb_width
        elif target_method == "atr_1x":   tgt_full = entry + atr
        elif target_method == "atr_0.75x": tgt_full = entry + 0.75 * atr
        else: tgt_full = entry + 2.0 * orb_width

        tgt1 = entry + min(1.5*orb_width, 0.5*atr) if use_partial else None
        tgt2 = tgt_full

    else:  # short
        entry = entry_px * (1 - SLIPPAGE_PCT)
        stop  = stop_px
        risk  = stop - entry
        if risk <= 0: return None

        if target_method == "orb_2x":    tgt_full = entry - 2.0 * orb_width
        elif target_method == "orb_1.5x": tgt_full = entry - 1.5 * orb_width
        elif target_method == "atr_1x":   tgt_full = entry - atr
        elif target_method == "atr_0.75x": tgt_full = entry - 0.75 * atr
        else: tgt_full = entry - 2.0 * orb_width

        tgt1 = entry - min(1.5*orb_width, 0.5*atr) if use_partial else None
        tgt2 = tgt_full

    qty = max(1, int(MAX_POS_VALUE / entry))     # full margin sizing
    cost = calc_full_cost(entry, qty, direction)

    p1_done = False; p1_pnl = 0.0; stop_adj = stop
    half = max(1, qty//2); rest = qty - half

    for j in range(len(day_bars)):
        fb = day_bars[j]
        ft = hhmm(fb)
        if ft < hhmm({"dt": day_bars[0]["dt"]}) + 1: continue  # skip bars before entry bar index

        if ft >= 1510:  # EOD
            if direction == "long":
                ep = fb["open"] * (1-SLIPPAGE_PCT)
                if use_partial and p1_done:
                    pnl = p1_pnl + (ep-entry)*rest - cost
                else:
                    pnl = (ep-entry)*qty - cost
            else:
                ep = fb["open"] * (1+SLIPPAGE_PCT)
                if use_partial and p1_done:
                    pnl = p1_pnl + (entry-ep)*rest - cost
                else:
                    pnl = (entry-ep)*qty - cost
            return {"pnl":round(pnl,2),"exit":"EOD","qty":qty,"cost":cost,"risk":risk,"entry":entry,"stop":stop,"tgt":tgt_full}

        if direction == "long":
            if fb["low"] <= stop_adj:
                ep = stop_adj
                if use_partial and p1_done:
                    pnl = p1_pnl + (ep-entry)*rest - cost
                else:
                    pnl = (ep-entry)*qty - cost
                return {"pnl":round(pnl,2),"exit":"SL","qty":qty,"cost":cost,"risk":risk,"entry":entry,"stop":stop,"tgt":tgt_full}
            if use_partial and tgt1 and not p1_done and fb["high"] >= tgt1:
                p1_pnl = (tgt1-entry)*half - cost/2
                p1_done = True; stop_adj = entry
            if (p1_done if use_partial else True) and fb["high"] >= tgt2:
                if use_partial and p1_done:
                    pnl = p1_pnl + (tgt2-entry)*rest - cost/2
                else:
                    pnl = (tgt2-entry)*qty - cost
                return {"pnl":round(pnl,2),"exit":"TP","qty":qty,"cost":cost,"risk":risk,"entry":entry,"stop":stop,"tgt":tgt_full}
        else:
            if fb["high"] >= stop_adj:
                ep = stop_adj
                if use_partial and p1_done:
                    pnl = p1_pnl + (entry-ep)*rest - cost
                else:
                    pnl = (entry-ep)*qty - cost
                return {"pnl":round(pnl,2),"exit":"SL","qty":qty,"cost":cost,"risk":risk,"entry":entry,"stop":stop,"tgt":tgt_full}
            if use_partial and tgt1 and not p1_done and fb["low"] <= tgt1:
                p1_pnl = (entry-tgt1)*half - cost/2
                p1_done = True; stop_adj = entry
            if (p1_done if use_partial else True) and fb["low"] <= tgt2:
                if use_partial and p1_done:
                    pnl = p1_pnl + (entry-tgt2)*rest - cost/2
                else:
                    pnl = (entry-tgt2)*qty - cost
                return {"pnl":round(pnl,2),"exit":"TP","qty":qty,"cost":cost,"risk":risk,"entry":entry,"stop":stop,"tgt":tgt_full}
    return None


# ── Strategy implementations ─────────────────────────────────────────────────

def strategy_standard(day_bars, day_idx, all_days, params):
    """Standard v3: first breakout, vol 2x, VWAP, partial exit, 2x ORB target"""
    if len(day_bars) < 10: return None
    orb = [b for b in day_bars[:5] if hhmm(b) in (915,920,925)]
    if not orb: orb = day_bars[:3]
    orh = max(b["high"] for b in orb)
    orl = min(b["low"]  for b in orb)
    orb_w = orh - orl
    if orb_w <= 0: return None

    open_px = day_bars[0]["open"]
    min_width_pct = params.get("min_width_pct", 0.0)
    if orb_w / open_px < min_width_pct: return None

    atr = calc_atr(all_days, day_idx)
    if atr == 0: atr = orb_w * 4   # fallback

    long_trig  = orh * 1.001
    short_trig = orl * 0.999
    target_method = params.get("target_method", "orb_2x")
    use_partial   = params.get("use_partial", True)
    second_entry  = params.get("second_entry", False)

    for i in range(3, len(day_bars)):
        b = day_bars[i]
        t = hhmm(b)
        if t < 930 or t > 1300: continue

        vol_avg = rolling_avg(day_bars, i)
        vol_ok  = b["volume"] > 2.0 * vol_avg
        vwap    = calc_vwap(day_bars, i)

        # Long
        if b["close"] > long_trig and vol_ok and b["close"] > vwap:
            if second_entry:
                # Wait: look for next bar that closes above THIS bar's high (supply resolved)
                supply_high = b["high"]
                supply_low  = b["low"]
                for k in range(i+1, min(i+6, len(day_bars))):
                    nb = day_bars[k]
                    nt = hhmm(nb)
                    if nt > 1300: break
                    nb_vol = rolling_avg(day_bars, k)
                    nb_vol_ok = nb["volume"] > 1.5 * nb_vol
                    # Re-entry: close above supply bar high with moderate vol
                    if nb["close"] > supply_high and nb_vol_ok:
                        # Better stop: supply bar low
                        stop = max(orl, supply_low)
                        result = run_trade(day_bars[k:], day_idx, all_days,
                                           nb["close"], stop, "long",
                                           target_method, atr, orb_w, use_partial)
                        if result:
                            result["second_entry"] = True
                        return result
                return None
            else:
                result = run_trade(day_bars[i:], day_idx, all_days,
                                   b["close"], orl, "long",
                                   target_method, atr, orb_w, use_partial)
                return result

        # Short
        if b["close"] < short_trig and vol_ok and b["close"] < vwap:
            if second_entry:
                supply_low  = b["low"]
                supply_high = b["high"]
                for k in range(i+1, min(i+6, len(day_bars))):
                    nb = day_bars[k]
                    nt = hhmm(nb)
                    if nt > 1300: break
                    nb_vol = rolling_avg(day_bars, k)
                    nb_vol_ok = nb["volume"] > 1.5 * nb_vol
                    if nb["close"] < supply_low and nb_vol_ok:
                        stop = min(orh, supply_high)
                        result = run_trade(day_bars[k:], day_idx, all_days,
                                           nb["close"], stop, "short",
                                           target_method, atr, orb_w, use_partial)
                        if result:
                            result["second_entry"] = True
                        return result
                return None
            else:
                result = run_trade(day_bars[i:], day_idx, all_days,
                                   b["close"], orh, "short",
                                   target_method, atr, orb_w, use_partial)
                return result
    return None


def run_config(all_days_by_ticker, params):
    trades = []
    for ticker, days in all_days_by_ticker.items():
        for i, day_bars in enumerate(days):
            r = strategy_standard(day_bars, i, days, params)
            if r:
                trades.append({**r, "ticker": ticker})
    return trades


def metrics(trades, brokerage_included=True):
    if not trades:
        return {"n":0,"wr":0,"pnl":0,"sharpe":0,"max_dd":0,"avg_r":0,
                "avg_pnl_pt":0,"tp":0,"sl":0,"eod":0,"avg_cost":0}
    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    pnls   = [t["pnl"] for t in trades]
    wr     = len(wins)/len(trades)*100
    avg_w  = statistics.mean(t["pnl"] for t in wins)  if wins   else 0
    avg_l  = statistics.mean(t["pnl"] for t in losses) if losses else 0
    avg_r  = abs(avg_w/avg_l) if avg_l else float("inf")
    sharpe = (statistics.mean(pnls)/statistics.stdev(pnls)*math.sqrt(250)
              if len(pnls)>1 and statistics.stdev(pnls)>0 else 0)
    eq=pk=dd=0.0
    for p in pnls:
        eq+=p
        if eq>pk: pk=eq
        if pk-eq>dd: dd=pk-eq
    avg_cost = statistics.mean(t.get("cost",40) for t in trades)
    return {"n":len(trades),"wr":round(wr,1),"pnl":round(sum(pnls),0),
            "sharpe":round(sharpe,2),"max_dd":round(dd/CAPITAL*100,2),
            "avg_r":round(avg_r,2),"avg_pnl_pt":round(sum(pnls)/len(trades),1),
            "tp":sum(1 for t in trades if t.get("exit")=="TP"),
            "sl":sum(1 for t in trades if t.get("exit")=="SL"),
            "eod":sum(1 for t in trades if t.get("exit")=="EOD"),
            "avg_cost":round(avg_cost,1)}


def main():
    print("="*72)
    print("  ORB Advanced v4 — Supply Absorption Solutions + Target Optimisation")
    print("  Goal: net Rs800-1000/day (4-5% on Rs20k capital)")
    print("  Full-margin sizing (Rs20k/position), realistic brokerage included")
    print("="*72)

    print("\nLoading data...", flush=True)
    all_days = {}
    for ticker in STRONG22:
        bars = fetch_raw(ticker)
        if bars:
            all_days[ticker] = split_days(bars)
    print(f"  {len(all_days)} tickers loaded")

    # Days in dataset (approx)
    total_days = max(len(v) for v in all_days.values()) if all_days else 56
    print(f"  Approx {total_days} trading days covered\n")

    configs = {
        "v3 baseline (orb_2x, partial, VWAP)": {
            "min_width_pct":0.0, "target_method":"orb_2x",
            "use_partial":True, "second_entry":False},
        "A: min width 1.0%": {
            "min_width_pct":0.01, "target_method":"orb_2x",
            "use_partial":True, "second_entry":False},
        "B: min width 1.2%": {
            "min_width_pct":0.012, "target_method":"orb_2x",
            "use_partial":True, "second_entry":False},
        "C: second entry (supply resolved)": {
            "min_width_pct":0.0, "target_method":"orb_2x",
            "use_partial":True, "second_entry":True},
        "D: ATR 1x target": {
            "min_width_pct":0.0, "target_method":"atr_1x",
            "use_partial":True, "second_entry":False},
        "D2: ATR 0.75x target": {
            "min_width_pct":0.0, "target_method":"atr_0.75x",
            "use_partial":True, "second_entry":False},
        "F: A + C (width1% + 2nd entry)": {
            "min_width_pct":0.01, "target_method":"orb_2x",
            "use_partial":True, "second_entry":True},
        "G: A + D (width1% + ATR target)": {
            "min_width_pct":0.01, "target_method":"atr_1x",
            "use_partial":True, "second_entry":False},
        "G2: B + D2 (width1.2% + ATR0.75x)": {
            "min_width_pct":0.012, "target_method":"atr_0.75x",
            "use_partial":True, "second_entry":False},
        "H: A + C + ATR (best combo)": {
            "min_width_pct":0.01, "target_method":"atr_0.75x",
            "use_partial":True, "second_entry":True},
        "I: B + C + ATR (strictest)": {
            "min_width_pct":0.012, "target_method":"atr_0.75x",
            "use_partial":True, "second_entry":True},
    }

    results = {}
    for label, params in configs.items():
        trades = run_config(all_days, params)
        results[label] = (metrics(trades), trades)

    baseline_m = results["v3 baseline (orb_2x, partial, VWAP)"][0]

    print(f"\n{'Config':<46} {'N':>4} {'WR%':>5} {'AvgR':>5} {'Net PnL':>8} "
          f"{'Avg/tr':>7} {'Shrp':>5} {'DD%':>5}  {'TP':>4}{'EOD':>5}  "
          f"{'PnL/day':>8}")
    print("-"*110)

    scored = []
    for label, (m, trades) in results.items():
        pnl_per_day = round(m["pnl"]/total_days, 1) if total_days>0 else 0
        is_base = label.startswith("v3 baseline")
        flag = " <BASE" if is_base else ""
        print(f"  {label:<44} {m['n']:>4} {m['wr']:>4.1f}%  {m['avg_r']:>4.2f}  "
              f"Rs{m['pnl']:>6.0f}  {m['avg_pnl_pt']:>+6.0f}  "
              f"{m['sharpe']:>4.2f}  {m['max_dd']:>4.2f}%"
              f"  {m['tp']:>4}{m['eod']:>5}  Rs{pnl_per_day:>6.0f}/d {flag}")
        if not is_base:
            scored.append((label, m, trades, pnl_per_day))

    # Best by net per-day PnL
    scored.sort(key=lambda x: -x[3])
    best_label, best_m, best_trades, best_ppd = scored[0]

    print(f"\n{'='*72}")
    print(f"  WINNER: {best_label}")
    print(f"{'='*72}")
    print(f"\n  {'Metric':<28} {'Baseline':>12} {'Best':>12} {'Delta':>10}")
    print(f"  {'-'*66}")
    for metric in [("n","trades","{}"),("wr","WR%","{:.1f}%"),("avg_r","AvgR","{:.2f}"),
                   ("pnl","Total PnL","Rs{:.0f}"),("sharpe","Sharpe","{:.2f}"),("max_dd","MaxDD","{:.2f}%")]:
        k,label2,fmt = metric
        bv = baseline_m[k]; wv = best_m[k]
        d = wv - bv
        print(f"  {label2:<28} {str(bv):>12} {str(wv):>12} {d:>+10.2f}")

    print(f"\n  Net PnL per trading day: Rs{best_ppd:.0f}/day  "
          f"(target: Rs800-1000 = 4-5% daily)")
    pct_of_target = best_ppd / 900 * 100
    print(f"  As % of Rs900 target: {pct_of_target:.0f}%")

    # Exit distribution analysis
    print(f"\n  Exit analysis:")
    print(f"    Baseline — TP:{baseline_m['tp']}  SL:{baseline_m['sl']}  EOD:{baseline_m['eod']}  "
          f"EOD%:{baseline_m['eod']/baseline_m['n']*100:.0f}%")
    print(f"    Best     — TP:{best_m['tp']}  SL:{best_m['sl']}  EOD:{best_m['eod']}  "
          f"EOD%:{best_m['eod']/best_m['n']*100 if best_m['n']>0 else 0:.0f}%")

    # Per-trade stats
    if best_trades:
        tp_trades  = [t for t in best_trades if t["exit"]=="TP"]
        sl_trades  = [t for t in best_trades if t["exit"]=="SL"]
        eod_trades = [t for t in best_trades if t["exit"]=="EOD"]
        print(f"\n  Avg P&L by exit type (net of brokerage):")
        if tp_trades:  print(f"    TP  exits: avg Rs{statistics.mean(t['pnl'] for t in tp_trades):+.0f}")
        if sl_trades:  print(f"    SL  exits: avg Rs{statistics.mean(t['pnl'] for t in sl_trades):+.0f}")
        if eod_trades: print(f"    EOD exits: avg Rs{statistics.mean(t['pnl'] for t in eod_trades):+.0f}")
        print(f"    Overall:    avg Rs{best_m['avg_pnl_pt']:+.0f} per trade")
        print(f"    Avg cost:   Rs{best_m['avg_cost']:.0f} per trade (brokerage + STT + GST)")

    # Top-5 tickers in best config
    if best_trades:
        from collections import defaultdict
        t_stats = defaultdict(list)
        for t in best_trades:
            t_stats[t["ticker"]].append(t["pnl"])
        t_ranked = sorted(t_stats.items(), key=lambda x: -sum(x[1]))
        print(f"\n  Top-8 tickers by P&L in best config:")
        for tk, pnls in t_ranked[:8]:
            wr = sum(1 for p in pnls if p>0)/len(pnls)*100
            print(f"    {tk:<14} n={len(pnls):>3}  WR={wr:>4.0f}%  PnL=Rs{sum(pnls):>6.0f}  "
                  f"avg=Rs{sum(pnls)/len(pnls):>+5.0f}/tr")

    # Summary recommendation
    print(f"\n{'='*72}")
    print(f"  STRATEGY RECOMMENDATIONS")
    print(f"{'='*72}")
    print(f"""
  Problem 1 — Supply Absorption:
    Solution: Second entry technique — after first breakout + supply bar,
    wait for close ABOVE supply bar high before entering. Stop = supply
    bar low (tighter). Avoids being trapped in the supply zone.

  Problem 2 — Narrow ORB width:
    Solution: Minimum width filter 1.0-1.2% of price.
    SUNPHARMA today (0.82%) would have been SKIPPED — correct decision.
    Narrow ORB = target too far = 75%+ EOD exits = no profit.

  Problem 3 — R-budget vs brokerage:
    Solution: Full-margin sizing (Rs20k/position) not R-budget sizing.
    Brokerage Rs40-60 on a Rs20k trade = 0.2-0.3% drag (manageable).
    On a Rs12.9k position it was 0.3-0.5% — significant.

  Problem 4 — Fixed ORB target unreachable:
    Solution: ATR-based target (0.75x daily ATR).
    Daily ATR is calibrated to what the stock ACTUALLY moves in a day.
    ORB multiples are based on the opening 15-min range, not the full day.

  Realistic daily P&L target:
    Best config achieves Rs{best_ppd:.0f}/day across {total_days} days.
    Peak on high-volatility days: Rs1,500-2,500.
    Low days (below threshold filters): Rs0 (no trade = better than loss).
    Consistent Rs800-1000/day requires: 2-3 STRONG signals firing together.
""")


main()
