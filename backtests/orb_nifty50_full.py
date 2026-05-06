#!/usr/bin/env python3
"""
ORB Full Nifty 50 Study — all 50 Nifty constituents, real NSE 5-min data.

Phase 1: Fetch & cache 5-min data for all 50 tickers
Phase 2: Per-ticker ORB backtest (v3 baseline params: vol=2.0x)
Phase 3: Rank tickers by WR → update preferred universe
Phase 4: Re-run v3 best config on actual top tickers

Run: python3 backtests/orb_nifty50_full.py
"""
import sys, io, json, math, statistics, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

CAPITAL        = 20_000
MARGIN         = CAPITAL * 5
MAX_POS_SIZE   = MARGIN * 0.20
COMMISSION_PCT = 0.0003
SLIPPAGE_PCT   = 0.0005

CACHE_DIR = Path(__file__).parent.parent / "data" / "history_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
IST = timezone(timedelta(hours=5, minutes=30))

YF_BASE = "https://query2.finance.yahoo.com/v8/finance/chart"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}

# Full Nifty 50 constituents (as of 2026-Q1)
NIFTY50 = [
    "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJAJFINSV", "BAJFINANCE", "BHARTIARTL",
    "BEL", "BPCL", "BRITANNIA", "CIPLA",
    "COALINDIA", "DIVISLAB", "DRREDDY", "EICHERMOT",
    "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK",
    "INDUSINDBK", "INFY", "ITC", "JSWSTEEL",
    "KOTAKBANK", "LT", "M&M", "MARUTI",
    "NESTLEIND", "NTPC", "ONGC", "POWERGRID",
    "RELIANCE", "SBIN", "SHRIRAMFIN", "SUNPHARMA",
    "TATAMOTORS", "TATACONSUM", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO",
    "WIPRO", "ZOMATO",
]

# Yahoo Finance symbol map (overrides for non-standard tickers)
YF_MAP = {
    "M&M":      "M&M",
    "BAJAJ-AUTO": "BAJAJ-AUTO",
}


# ── Data layer ────────────────────────────────────────────────────────────────

def yf_symbol(ticker: str) -> str:
    return YF_MAP.get(ticker, ticker) + ".NS"


def fetch_raw(ticker: str) -> list[dict]:
    cache = CACHE_DIR / f"{ticker}_5min_v8.json"
    if cache.exists() and (time.time() - cache.stat().st_mtime) / 3600 < 48:
        data = json.loads(cache.read_text())
        if data:
            return data

    sym = yf_symbol(ticker)
    url = f"{YF_BASE}/{sym}?interval=5m&range=58d"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = json.loads(r.read())
            break
        except Exception as e:
            if attempt == 2:
                return []
            time.sleep(4 * (attempt + 1))

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
    except Exception as e:
        return []


def split_days(bars: list[dict]) -> list[list[dict]]:
    from collections import defaultdict
    buckets = defaultdict(list)
    for b in bars:
        buckets[datetime.fromisoformat(b["dt"]).date().isoformat()].append(b)
    return [sorted(v, key=lambda x: x["ts"]) for k,v in sorted(buckets.items()) if len(v) >= 15]


def hhmm(bar: dict) -> int:
    dt = datetime.fromisoformat(bar["dt"])
    return dt.hour*100 + dt.minute


def rolling_vol_avg(bars, idx, window=20):
    start = max(0, idx - window + 1)
    vols  = [bars[j]["volume"] for j in range(start, idx+1)]
    return sum(vols)/len(vols) if vols else 1.0


def calc_vwap(bars):
    tv = tp = 0.0
    for b in bars:
        tp_price = (b["high"]+b["low"]+b["close"])/3
        tv += tp_price * b["volume"]
        tp += b["volume"]
    return tv/tp if tp > 0 else 0.0


# ── ORB v3 strategy ───────────────────────────────────────────────────────────

def run_orb_v3_day(day_bars: list[dict], params: dict) -> dict | None:
    """
    v3 params used:
      vol_thresh  : volume confirmation multiplier (default 2.0)
      partial_exit: bool — 50% at 1.5x ORB, SL to BE, rest at 2.5x
      vwap_filter : bool — only long above VWAP, short below
      target_mult : full exit target (used when partial_exit=False)
    """
    vol_thresh   = params.get("vol_thresh",   2.0)
    partial_exit = params.get("partial_exit", False)
    vwap_filter  = params.get("vwap_filter",  False)
    target_mult  = params.get("target_mult",  2.0)
    entry_cutoff = params.get("entry_cutoff", 1300)
    buf          = params.get("buf_pct",      0.001)

    if len(day_bars) < 10:
        return None
    orh = max(b["high"] for b in day_bars[:3])
    orl = min(b["low"]  for b in day_bars[:3])
    orb_width = orh - orl
    if orb_width <= 0:
        return None

    long_entry_px  = orh * (1 + buf)
    short_entry_px = orl * (1 - buf)

    for i in range(3, len(day_bars)):
        bar = day_bars[i]
        t   = hhmm(bar)
        if t < 930: continue
        if t > entry_cutoff: break

        vol_avg = rolling_vol_avg(day_bars, i)
        vol_ok  = bar["volume"] > vol_thresh * vol_avg
        if not vol_ok: continue

        if vwap_filter:
            vwap = calc_vwap(day_bars[:i+1])
        else:
            vwap = 0.0

        # Long
        if bar["close"] > long_entry_px:
            if vwap_filter and bar["close"] <= vwap: continue
            entry = long_entry_px * (1 + SLIPPAGE_PCT)
            stop  = orl
            qty   = max(1, int(MAX_POS_SIZE / entry))
            cost_rate = (COMMISSION_PCT + SLIPPAGE_PCT) * 2

            if partial_exit:
                half, rest = max(1, qty//2), qty - max(1, qty//2)
                p1_done = False; p1_pnl = 0.0; stop_adj = stop
                tgt1 = entry + 1.5 * orb_width
                tgt2 = entry + 2.5 * orb_width
                for j in range(i+1, len(day_bars)):
                    fb = day_bars[j]; ft = hhmm(fb)
                    if ft >= 1510:
                        epx = fb["open"] * (1-SLIPPAGE_PCT)
                        pnl = (p1_pnl + (epx-entry)*rest - entry*rest*cost_rate) if p1_done else ((epx-entry)*qty - entry*qty*cost_rate)
                        return {"dir":"L","pnl":round(pnl,2),"exit":"EOD"}
                    if fb["low"] <= stop_adj:
                        epx = stop_adj
                        pnl = (p1_pnl + (epx-entry)*rest - entry*rest*cost_rate) if p1_done else ((epx-entry)*qty - entry*qty*cost_rate)
                        return {"dir":"L","pnl":round(pnl,2),"exit":"SL"}
                    if not p1_done and fb["high"] >= tgt1:
                        p1_pnl = (tgt1-entry)*half - entry*half*cost_rate
                        p1_done = True; stop_adj = entry
                    if p1_done and fb["high"] >= tgt2:
                        pnl = p1_pnl + (tgt2-entry)*rest - entry*rest*cost_rate
                        return {"dir":"L","pnl":round(pnl,2),"exit":"TP"}
                return None
            else:
                tgt = entry + target_mult * orb_width
                for j in range(i+1, len(day_bars)):
                    fb = day_bars[j]; ft = hhmm(fb)
                    cost = entry*qty*cost_rate
                    if ft >= 1510:
                        return {"dir":"L","pnl":round((fb["open"]*(1-SLIPPAGE_PCT)-entry)*qty-cost,2),"exit":"EOD"}
                    if fb["low"] <= stop:
                        return {"dir":"L","pnl":round((stop-entry)*qty-cost,2),"exit":"SL"}
                    if fb["high"] >= tgt:
                        return {"dir":"L","pnl":round((tgt-entry)*qty-cost,2),"exit":"TP"}
                return None

        # Short
        if bar["close"] < short_entry_px:
            if vwap_filter and bar["close"] >= vwap: continue
            entry = short_entry_px * (1-SLIPPAGE_PCT)
            stop  = orh
            qty   = max(1, int(MAX_POS_SIZE / entry))
            cost_rate = (COMMISSION_PCT + SLIPPAGE_PCT) * 2

            if partial_exit:
                half, rest = max(1, qty//2), qty - max(1, qty//2)
                p1_done = False; p1_pnl = 0.0; stop_adj = stop
                tgt1 = entry - 1.5 * orb_width
                tgt2 = entry - 2.5 * orb_width
                for j in range(i+1, len(day_bars)):
                    fb = day_bars[j]; ft = hhmm(fb)
                    if ft >= 1510:
                        epx = fb["open"] * (1+SLIPPAGE_PCT)
                        pnl = (p1_pnl + (entry-epx)*rest - entry*rest*cost_rate) if p1_done else ((entry-epx)*qty - entry*qty*cost_rate)
                        return {"dir":"S","pnl":round(pnl,2),"exit":"EOD"}
                    if fb["high"] >= stop_adj:
                        epx = stop_adj
                        pnl = (p1_pnl + (entry-epx)*rest - entry*rest*cost_rate) if p1_done else ((entry-epx)*qty - entry*qty*cost_rate)
                        return {"dir":"S","pnl":round(pnl,2),"exit":"SL"}
                    if not p1_done and fb["low"] <= tgt1:
                        p1_pnl = (entry-tgt1)*half - entry*half*cost_rate
                        p1_done = True; stop_adj = entry
                    if p1_done and fb["low"] <= tgt2:
                        pnl = p1_pnl + (entry-tgt2)*rest - entry*rest*cost_rate
                        return {"dir":"S","pnl":round(pnl,2),"exit":"TP"}
                return None
            else:
                tgt = entry - target_mult * orb_width
                for j in range(i+1, len(day_bars)):
                    fb = day_bars[j]; ft = hhmm(fb)
                    cost = entry*qty*cost_rate
                    if ft >= 1510:
                        return {"dir":"S","pnl":round((entry-fb["open"]*(1+SLIPPAGE_PCT))*qty-cost,2),"exit":"EOD"}
                    if fb["high"] >= stop:
                        return {"dir":"S","pnl":round((entry-stop)*qty-cost,2),"exit":"SL"}
                    if fb["low"] <= tgt:
                        return {"dir":"S","pnl":round((entry-tgt)*qty-cost,2),"exit":"TP"}
                return None

    return None


def metrics(trades):
    if not trades:
        return {"n":0,"wr":0.0,"pnl":0,"sharpe":0,"max_dd":0,"avg_r":0,"avg_win":0,"avg_loss":0,"tp":0,"sl":0,"eod":0}
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
    return {"n":len(trades),"wr":round(wr,1),"pnl":round(sum(pnls),0),
            "sharpe":round(sharpe,2),"max_dd":round(dd/CAPITAL*100,2),
            "avg_r":round(avg_r,2),"avg_win":round(avg_w,0),"avg_loss":round(avg_l,0),
            "tp":sum(1 for t in trades if t.get("exit")=="TP"),
            "sl":sum(1 for t in trades if t.get("exit")=="SL"),
            "eod":sum(1 for t in trades if t.get("exit")=="EOD")}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 72)
    print("  ORB Full Nifty 50 Study — Real NSE 5-min data (Yahoo Finance v8)")
    print(f"  Universe: {len(NIFTY50)} tickers | ~56 trading days | vol=2.0x baseline")
    print("=" * 72)

    # ── Phase 1: Fetch all tickers ─────────────────────────────────────────
    print(f"\n[Phase 1] Fetching 5-min data for all {len(NIFTY50)} Nifty 50 tickers...")
    print("  (cached data reused if < 48h old, skipping API for those)\n")

    all_days = {}
    failed   = []

    for i, ticker in enumerate(NIFTY50):
        cached = CACHE_DIR / f"{ticker}_5min_v8.json"
        from_cache = cached.exists() and (time.time()-cached.stat().st_mtime)/3600 < 48
        status = "CACHE" if from_cache else "FETCH"

        if not from_cache and i > 0:
            time.sleep(2)   # polite delay between live fetches

        bars = fetch_raw(ticker)
        if bars:
            days = split_days(bars)
            all_days[ticker] = days
            print(f"  [{i+1:2d}/50] {ticker:<14} {status}  {len(bars):5d} bars  {len(days)} days")
        else:
            failed.append(ticker)
            print(f"  [{i+1:2d}/50] {ticker:<14} FAILED")

    print(f"\n  Loaded {len(all_days)}/50 tickers. Failed: {failed if failed else 'none'}")

    # ── Phase 2: Per-ticker ORB (v3 base params: vol=2.0, no partial, no VWAP)
    print(f"\n{'='*72}")
    print(f"  [Phase 2] Per-ticker ORB — baseline v3 params (vol=2.0x)")
    print(f"{'='*72}")
    print(f"\n  {'Ticker':<14} {'N':>4} {'WR%':>6} {'AvgR':>6} {'PnL':>8} {'Shrp':>6} {'DD%':>6}  Grade")
    print(f"  {'-'*65}")

    base_params = {"vol_thresh":2.0,"partial_exit":False,"vwap_filter":False,"target_mult":2.0}
    ticker_results = {}

    for ticker, days in all_days.items():
        trades = []
        for i, day_bars in enumerate(days):
            r = run_orb_v3_day(day_bars, base_params)
            if r:
                trades.append({**r, "ticker": ticker})
        if trades:
            m = metrics(trades)
            ticker_results[ticker] = m
            n = m["n"]
            grade = ("A" if m["wr"] >= 60 and m["pnl"] > 0 else
                     "B" if m["wr"] >= 55 and m["pnl"] > 0 else
                     "C" if m["wr"] >= 50 and m["pnl"] > 0 else
                     "D" if m["pnl"] > 0 else "F")
            print(f"  {ticker:<14} {n:>4} {m['wr']:>5.1f}%  {m['avg_r']:>5.2f}  "
                  f"Rs{m['pnl']:>6.0f}  {m['sharpe']:>5.2f}  {m['max_dd']:>5.2f}%  {grade}")
        else:
            print(f"  {ticker:<14}    0   —      —       —      —      —   —")

    # ── Phase 3: Rank and identify best tickers ────────────────────────────
    print(f"\n{'='*72}")
    print(f"  [Phase 3] Ranking — sorted by WR (min 10 trades)")
    print(f"{'='*72}\n")

    ranked = sorted(
        [(t, m) for t, m in ticker_results.items() if m["n"] >= 10],
        key=lambda x: (-x[1]["wr"], -x[1]["pnl"])
    )

    print(f"  {'Rank':<5} {'Ticker':<14} {'N':>4} {'WR%':>6} {'AvgR':>6} {'PnL':>8} {'Shrp':>6}  Tag")
    print(f"  {'-'*65}")
    for rank, (t, m) in enumerate(ranked, 1):
        tag = ("STRONG" if m["wr"]>=60 and m["pnl"]>0 else
               "GOOD"   if m["wr"]>=55 and m["pnl"]>0 else
               "MARGINAL" if m["wr"]>=50 and m["pnl"]>0 else
               "SKIP")
        print(f"  {rank:<5} {t:<14} {m['n']:>4} {m['wr']:>5.1f}%  {m['avg_r']:>5.2f}  "
              f"Rs{m['pnl']:>6.0f}  {m['sharpe']:>5.2f}  {tag}")

    top_tickers = [t for t, m in ranked if m["wr"] >= 58 and m["n"] >= 10 and m["pnl"] > 0]
    good_tickers = [t for t, m in ranked if m["wr"] >= 52 and m["n"] >= 10 and m["pnl"] > 0]

    print(f"\n  Strong (WR>=58%, n>=10, PnL>0): {top_tickers}")
    print(f"  Good   (WR>=52%, n>=10, PnL>0): {good_tickers}")

    # ── Phase 4: Run v3 full config on actual top tickers ─────────────────
    print(f"\n{'='*72}")
    print(f"  [Phase 4] v3 config on full-universe top tickers")
    print(f"{'='*72}\n")

    v3_params = {"vol_thresh":2.0,"partial_exit":True,"vwap_filter":True,"target_mult":2.0}

    configs_to_test = {
        "v2 baseline (vol=2.0, all 50)":   (base_params, list(all_days.keys())),
        "v3 AE (top-4 from 14-ticker study)": (v3_params, ["BHARTIARTL","HDFCBANK","RELIANCE","AXISBANK"]),
    }
    if top_tickers:
        configs_to_test[f"v3 AE (top {len(top_tickers)} from full Nifty 50)"] = (v3_params, top_tickers)
    if good_tickers and good_tickers != top_tickers:
        configs_to_test[f"v3 AE (good {len(good_tickers)} from full Nifty 50)"] = (v3_params, good_tickers)

    print(f"  {'Config':<48} {'N':>5} {'WR%':>6} {'AvgR':>6} {'PnL':>8} {'Shrp':>6} {'DD%':>6}")
    print(f"  {'-'*85}")

    phase4_results = {}
    for label, (params, tickers) in configs_to_test.items():
        trades = []
        for ticker in tickers:
            if ticker not in all_days: continue
            days = all_days[ticker]
            for i, day_bars in enumerate(days):
                r = run_orb_v3_day(day_bars, params)
                if r:
                    trades.append({**r, "ticker": ticker})
        m = metrics(trades)
        phase4_results[label] = m
        n_tickers = len([t for t in tickers if t in all_days])
        print(f"  {label:<48} {m['n']:>5} {m['wr']:>5.1f}%  {m['avg_r']:>5.2f}  "
              f"Rs{m['pnl']:>7.0f}  {m['sharpe']:>5.2f}  {m['max_dd']:>5.2f}%")

    # ── Summary ───────────────────────────────────────────────────────────
    print(f"\n{'='*72}")
    print(f"  SUMMARY & STRATEGY RECOMMENDATIONS")
    print(f"{'='*72}\n")

    print(f"  Previous preferred tickers (from 14-ticker study):")
    old_top4 = ["BHARTIARTL","HDFCBANK","RELIANCE","AXISBANK"]
    for t in old_top4:
        m = ticker_results.get(t)
        if m:
            print(f"    {t:<14} WR={m['wr']}%  n={m['n']}  PnL=Rs{m['pnl']}")
        else:
            print(f"    {t:<14} no data")

    print(f"\n  NEW preferred tickers (from full Nifty 50):")
    for rank, (t, m) in enumerate(ranked[:10], 1):
        old_flag = " (was in top-4)" if t in old_top4 else ""
        new_flag = " *** NEW ***" if t not in old_top4 and m["wr"] >= 58 else ""
        print(f"  #{rank:2d} {t:<14} WR={m['wr']:4.1f}%  AvgR={m['avg_r']:.2f}  "
              f"PnL=Rs{m['pnl']:6.0f}  Sharpe={m['sharpe']:.2f}{old_flag}{new_flag}")

    print(f"\n  Recommendation:")
    if top_tickers:
        dropped = [t for t in old_top4 if t not in top_tickers]
        added   = [t for t in top_tickers if t not in old_top4]
        print(f"    Replace preferred universe with full-Nifty-50 top tickers (WR>=58%)")
        if dropped: print(f"    Drop from v3 list: {dropped}")
        if added:   print(f"    Add to v3 list   : {added}")
    else:
        print(f"    Full-Nifty scan did not find new tickers beating WR>=58% threshold")
        print(f"    Keep existing top-4 — they remain the best validated set")

    print()


main()
