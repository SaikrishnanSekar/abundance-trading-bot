import sys, json, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))

# STRONG-22 only — validated by backtests, ranked by WR x Sharpe
NIFTY_50 = [
    "SHRIRAMFIN", "BHARTIARTL", "HEROMOTOCO", "INDUSINDBK", "SUNPHARMA",
    "DIVISLAB", "TECHM", "ADANIPORTS", "HINDUNILVR", "ULTRACEMCO",
    "LT", "BEL", "BAJAJ-AUTO", "KOTAKBANK", "AXISBANK",
    "BAJAJFINSV", "HDFCBANK", "DRREDDY", "SBIN", "WIPRO",
    "TCS", "INFY"
]

YF_BASE = "https://query2.finance.yahoo.com/v8/finance/chart"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

def fetch_data(ticker):
    url = f"{YF_BASE}/{ticker}.NS?interval=5m&range=5d"
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=5) as r:
                raw = json.loads(r.read())
            
            res = raw["chart"]["result"][0]
            ts = res["timestamp"]
            q = res["indicators"]["quote"][0]
            
            bars = []
            for i, t in enumerate(ts):
                o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
                if None in (o, h, l, c): continue
                dt_ist = datetime.fromtimestamp(t, tz=IST)
                hhmm = dt_ist.hour * 100 + dt_ist.minute
                if hhmm < 915 or hhmm > 1515: continue
                bars.append({
                    "ts": t, "dt": dt_ist,
                    "open": o, "high": h, "low": l, "close": c, "volume": v or 0
                })
            return bars
        except Exception as e:
            time.sleep(1)
    return []

def scan():
    print(f"--- NIFTY 50 LIVE ORB SCAN ---")
    print(f"Time: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST")
    print("-" * 70)
    
    today_str = datetime.now(IST).date().isoformat()
    
    results = []
    
    for ticker in NIFTY_50:
        bars = fetch_data(ticker)
        if not bars: continue
        
        # Filter bars for today
        today_bars = [b for b in bars if b["dt"].date().isoformat() == today_str]
        
        if len(today_bars) < 3:
            # ORB not formed yet
            continue
            
        orh = max(b["high"] for b in today_bars[:3])
        orl = min(b["low"] for b in today_bars[:3])
        orb_width = orh - orl
        mid = (orh + orl) / 2

        if orb_width <= 0 or mid <= 0: continue

        # WIDTH GATE: ORB must be >= 1.5% of midpoint (skip narrow days)
        width_pct = orb_width / mid * 100
        if width_pct < 1.5:
            results.append({
                "ticker": ticker, "status": f"SKIP-WIDTH ({width_pct:.1f}%<1.5%)",
                "close": today_bars[-1]["close"], "orh": orh, "orl": orl,
                "vol_ratio": 0, "width_pct": width_pct,
                "time": today_bars[-1]["dt"].strftime('%H:%M')
            })
            continue

        long_entry = orh * 1.001
        short_entry = orl * 0.999

        # Current bar
        latest_bar = today_bars[-1]
        close_px = latest_bar["close"]

        # VWAP (cumulative from session start)
        cum_tp_vol = sum((b["high"]+b["low"]+b["close"])/3 * max(b["volume"],1) for b in today_bars)
        cum_vol = sum(max(b["volume"],1) for b in today_bars)
        vwap = cum_tp_vol / cum_vol if cum_vol > 0 else close_px

        # Volume ratio vs 20-bar avg
        idx = len(bars) - 1
        start = max(0, idx - 19)
        vols = [bars[j]["volume"] for j in range(start, idx + 1)]
        avg_vol = sum(vols) / len(vols) if vols else 1.0
        vol_ratio = latest_bar["volume"] / avg_vol if avg_vol > 0 else 0

        # Partial exit targets
        tgt1_long  = close_px + orb_width * 1.5 if close_px > long_entry else None
        tgt2_long  = close_px + orb_width * 2.5 if close_px > long_entry else None
        tgt1_short = close_px - orb_width * 1.5 if close_px < short_entry else None
        tgt2_short = close_px - orb_width * 2.5 if close_px < short_entry else None

        vwap_ok_long  = close_px > vwap
        vwap_ok_short = close_px < vwap

        status = "WATCHING"
        dist_long = (long_entry - close_px) / close_px * 100
        dist_short = (close_px - short_entry) / close_px * 100

        if close_px > long_entry:
            if vol_ratio >= 2.0 and vwap_ok_long:
                status = ">>> ENTRY LONG (vol+VWAP OK)"
            elif vwap_ok_long:
                status = f"BREAKOUT LONG (LOW VOL {vol_ratio:.1f}x — wait)"
            else:
                status = f"BREAKOUT LONG (VWAP FAIL — skip)"
        elif close_px < short_entry:
            if vol_ratio >= 2.0 and vwap_ok_short:
                status = ">>> ENTRY SHORT (vol+VWAP OK)"
            elif vwap_ok_short:
                status = f"BREAKOUT SHORT (LOW VOL {vol_ratio:.1f}x — wait)"
            else:
                status = f"BREAKOUT SHORT (VWAP FAIL — skip)"
        elif dist_long <= 0.15:
            status = f"NEAR LONG ({dist_long:.2f}% away, VWAP {'ok' if vwap_ok_long else 'fail'})"
        elif dist_short <= 0.15:
            status = f"NEAR SHORT ({dist_short:.2f}% away, VWAP {'ok' if vwap_ok_short else 'fail'})"

        results.append({
            "ticker": ticker,
            "status": status,
            "close": close_px,
            "orh": orh,
            "orl": orl,
            "width_pct": width_pct,
            "vwap": vwap,
            "vol_ratio": vol_ratio,
            "time": latest_bar["dt"].strftime('%H:%M'),
            "tgt1": tgt1_long or tgt1_short,
            "tgt2": tgt2_long or tgt2_short,
            "stop": orl if close_px > long_entry else (orh if close_px < short_entry else None),
        })
            
    # Sort results to put valid breakouts first
    def sort_key(r):
        if "VALID VOLUME" in r["status"]: return 0
        if "BREAKOUT" in r["status"] and "LOW VOL" in r["status"]: return 1
        if "NEAR" in r["status"]: return 2
        return 3
        
    results.sort(key=sort_key)
    
    def sort_key(r):
        s = r["status"]
        if ">>> ENTRY" in s: return 0
        if "NEAR" in s: return 1
        if "BREAKOUT" in s: return 2
        if "SKIP" in s: return 9
        return 5

    results.sort(key=sort_key)

    print(f"\n{'Ticker':<12} | {'Time':<5} | {'Price':>8} | {'ORH':>8} | {'ORL':>8} | {'Wid%':>5} | {'Volx':>5} | Status")
    print("-" * 100)
    for r in results:
        tgt_str = ""
        if r.get("tgt1") and r.get("stop"):
            tgt_str = f"  [T1:{r['tgt1']:.2f} T2:{r.get('tgt2',0):.2f} SL:{r['stop']:.2f}]"
        print(f"{r['ticker']:<12} | {r['time']:<5} | {r['close']:>8.2f} | {r['orh']:>8.2f} | "
              f"{r['orl']:>8.2f} | {r.get('width_pct',0):>5.1f}% | {r['vol_ratio']:>5.1f}x | "
              f"{r['status']}{tgt_str}")

    # Summary
    entries = [r for r in results if ">>> ENTRY" in r["status"]]
    near = [r for r in results if "NEAR" in r["status"]]
    skipped = [r for r in results if "SKIP" in r["status"]]
    print(f"\nActive entries: {len(entries)} | Near breakout: {len(near)} | Width-skip: {len(skipped)} | Watching: {len(results)-len(entries)-len(near)-len(skipped)}")
    if entries:
        print(f"ACTION: {[r['ticker'] for r in entries]}")

if __name__ == "__main__":
    scan()
