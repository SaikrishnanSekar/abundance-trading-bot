import sys, json, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

_SCRIPTS = Path(__file__).parent / "scripts"

IST = timezone(timedelta(hours=5, minutes=30))

# Full Nifty 50 universe
NIFTY_50 = [
    "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO",
    "BAJAJFINSV", "BAJFINANCE", "BHARTIARTL", "BEL", "BPCL",
    "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

# Nifty Next 50 — stocks ranked 51-100 by free-float market cap (NSE index)
# Rebalanced quarterly; verify against NSE factsheet after each rebalancing.
NIFTY_NEXT_50 = [
    "ADANIENT",   "ADANIGREEN",  "AMBUJACEM",  "BAJAJHLDNG", "BANKBARODA",
    "BERGEPAINT", "BOSCHLTD",    "CANBK",      "CHOLAFIN",   "COLPAL",
    "CONCOR",     "DABUR",       "DLF",        "DMART",      "GAIL",
    "GODREJCP",   "HAVELLS",     "INDHOTEL",   "INDUSTOWER", "IOC",
    "IRCTC",      "IRFC",        "LICI",       "LODHA",      "LUPIN",
    "MARICO",     "MUTHOOTFIN",  "NAUKRI",     "NYKAA",      "OFSS",
    "PERSISTENT", "PIDILITIND",  "PNB",        "RECLTD",     "SAIL",
    "SRF",        "TATAPOWER",   "TIINDIA",    "TORNTPHARM", "TORNTPOWER",
    "TVSMOTOR",   "UNIONBANK",   "UPL",        "VEDL",       "VOLTAS",
    "ETERNAL",    "JSWENERGY",   "ZYDUSLIFE",  "PPLPHARMA",  "PAYTM",
]

# Nifty Midcap 50 — liquid midcap universe (NSE Midcap 50 index)
# Verify against NSE factsheet quarterly; remove any that move to Nifty 100.
MIDCAP_50_LIQUID = [
    "ABCAPITAL",  "APLAPOLLO",   "ASTRAL",     "AUROPHARMA", "BALKRISIND",
    "BANKINDIA",  "BATAINDIA",   "BHARATFORG", "BIOCON",     "COFORGE",
    "CROMPTON",   "DELHIVERY",   "FEDERALBNK", "GMRAIRPORT", "GODREJPROP",
    "IDFCFIRSTB", "INDIAMART",   "JKCEMENT",   "JUBLFOOD",   "KALYANKJIL",
    "KPITTECH",   "LTTS",        "MANAPPURAM", "MAXHEALTH",  "MPHASIS",
    "NHPC",       "OBEROIRLTY",  "PAGEIND",    "PIIND",      "POLICYBZR",
    "POLYCAB",    "RBLBANK",     "SJVN",       "SUNDRMFAST", "SUPREMEIND",
    "TATACHEM",   "TATACOMM",    "VGUARD",     "ABFRL",      "CESC",
    "DIXON",      "HUDCO",       "INDIANB",    "IREDA",      "JBCHEPHARM",
    "KAYNES",     "MOTILALOFS",  "NUVAMA",     "PRESTIGE",   "SOLARINDS",
]

# NSE sector map — used for sector snapshot in scan output
SECTOR_MAP = {
    # Nifty 50
    "BANKING":  ["HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK", "INDUSINDBK", "SBIN"],
    "NBFC":     ["BAJAJFINSV", "BAJFINANCE", "SHRIRAMFIN"],
    "IT":       ["INFY", "TCS", "WIPRO", "HCLTECH", "TECHM"],
    "PHARMA":   ["SUNPHARMA", "DRREDDY", "DIVISLAB", "CIPLA", "APOLLOHOSP"],
    "AUTO":     ["BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT", "M&M", "MARUTI"],
    "FMCG":     ["HINDUNILVR", "BRITANNIA", "NESTLEIND", "TATACONSUM", "ITC"],
    "ENERGY":   ["ONGC", "BPCL", "RELIANCE", "COALINDIA"],
    "INFRA":    ["ADANIPORTS", "LT", "BEL", "NTPC", "POWERGRID"],
    "METALS":   ["TATASTEEL", "JSWSTEEL", "HINDALCO"],
    "CEMENT":   ["ULTRACEMCO", "GRASIM"],
    "TELECOM":  ["BHARTIARTL"],
    "CONSUMER": ["TITAN", "TRENT", "ASIANPAINT"],
    "INSURE":   ["SBILIFE", "HDFCLIFE"],
    # Nifty Next 50 additions
    "PSU-BNK":  ["BANKBARODA", "CANBK", "PNB", "UNIONBANK", "SAIL", "IOC",
                 "CONCOR", "RECLTD", "GAIL", "IRFC", "LICI", "BANKINDIA", "INDIANB"],
    "ADANI":    ["ADANIENT", "ADANIGREEN"],
    "REALTY":   ["DLF", "LODHA", "GODREJPROP", "OBEROIRLTY", "PRESTIGE"],
    "CEMENT2":  ["AMBUJACEM", "JKCEMENT"],
    "AUTO2":    ["TVSMOTOR", "TIINDIA", "BALKRISIND", "BHARATFORG", "SUNDRMFAST"],
    "PHARMA2":  ["LUPIN", "TORNTPHARM", "AUROPHARMA", "BIOCON", "ZYDUSLIFE", "JBCHEPHARM", "PIIND"],
    "FMCG2":    ["COLPAL", "DABUR", "MARICO", "GODREJCP", "BATAINDIA", "PAGEIND", "ABFRL"],
    "IT2":      ["OFSS", "PERSISTENT", "MPHASIS", "COFORGE", "KPITTECH", "LTTS", "INDIAMART"],
    "POWER":    ["TATAPOWER", "TORNTPOWER", "JSWENERGY", "NHPC", "SJVN", "IREDA", "CESC"],
    "NBFC2":    ["CHOLAFIN", "MUTHOOTFIN", "BAJAJHLDNG", "MANAPPURAM", "ABCAPITAL", "MOTILALOFS", "NUVAMA"],
    "TELECOM2": ["INDUSTOWER"],
    "ELEC":     ["HAVELLS", "VOLTAS", "CROMPTON", "POLYCAB", "VGUARD", "DIXON", "KAYNES", "APLAPOLLO"],
    "HOTEL":    ["INDHOTEL"],
    "CHEM":     ["SRF", "UPL", "PIDILITIND", "TATACHEM", "SOLARINDS", "SUPREMEIND", "ASTRAL"],
    "METALS2":  ["VEDL", "ADANIENT"],
    "FINTECH":  ["PAYTM", "POLICYBZR", "NAUKRI", "NYKAA"],
    "INFRA2":   ["GMRINFRA", "HUDCO", "TATACOMM", "DELHIVERY"],
    "FOOD":     ["DMART", "JUBLFOOD"],
    "BANK2":    ["FEDERALBNK", "IDFCFIRSTB", "RBLBANK"],
    "RETAIL":   ["KALYANKJIL"],
    "BOSCH":    ["BOSCHLTD"],
    "BERGEP":   ["BERGEPAINT"],
    "OTHER":    ["TATAMOTORS", "ABFRL"],
}
_SECTOR_LOOKUP = {t: s for s, tickers in SECTOR_MAP.items() for t in tickers}


def _ticker_sector(ticker):
    return _SECTOR_LOOKUP.get(ticker, "OTHER")


YF_BASE = "https://query2.finance.yahoo.com/v8/finance/chart"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

FEED_FILE    = Path(__file__).parent / "data" / "live_feed.json"
FEED_MAX_AGE = 60   # seconds


# ── Single-pass cache preload ─────────────────────────────────────────────────

def preload_daily_context(today_str, universe=None):
    """One pass through history cache for all tickers. Returns avg_vols, breadth, ctx.

    universe — list of tickers to compute avg_vols/ctx for (defaults to NIFTY_50).
    Breadth (% above 20/50d SMA) is always computed on NIFTY_50 regardless of universe
    so the market-health signal stays consistent.
    """
    cache_dir = Path(__file__).parent / "data" / "history_cache"
    if universe is None:
        universe = NIFTY_50
    avg_vols = {}
    ctx      = {}
    above_20 = above_50 = breadth_n = 0

    # Full scan set = universe for avg_vols/ctx, always include NIFTY_50 for breadth
    breadth_set = set(NIFTY_50)
    scan_set    = set(universe) | breadth_set

    for ticker in scan_set:
        f = cache_dir / f"{ticker}_5min_v8.json"
        if not f.exists():
            continue
        try:
            raw_bars = json.loads(f.read_text(encoding="utf-8"))
            vol_by_day  = {}
            ohlc_by_day = {}
            for b in raw_bars:
                d = b["dt"][:10]
                if d >= today_str:
                    continue
                vol_by_day[d] = vol_by_day.get(d, 0) + b.get("volume", 0)
                if d not in ohlc_by_day:
                    ohlc_by_day[d] = {"h": b["high"], "l": b["low"], "c": b["close"]}
                else:
                    e = ohlc_by_day[d]
                    if b["high"] > e["h"]: e["h"] = b["high"]
                    if b["low"]  < e["l"]: e["l"] = b["low"]
                    e["c"] = b["close"]   # last bar of day wins

            # 20-day average daily volume (only for universe stocks, not breadth-only extras)
            if ticker in set(universe):
                recent_vol = sorted(vol_by_day.items())[-20:]
                if recent_vol:
                    avg_vols[ticker] = sum(v for _, v in recent_vol) / len(recent_vol)

            # Daily OHLC bars sorted
            skeys  = sorted(ohlc_by_day.keys())
            bars_d = [ohlc_by_day[k] for k in skeys]
            closes = [b["c"] for b in bars_d]
            if not closes:
                continue

            # Market breadth: only Nifty 50 stocks count (market-health signal)
            if ticker in breadth_set and len(closes) >= 20:
                ma20 = sum(closes[-20:]) / 20
                breadth_n += 1
                if closes[-1] > ma20:
                    above_20 += 1
                if len(closes) >= 50:
                    ma50_b = sum(closes[-50:]) / 50
                    if closes[-1] > ma50_b:
                        above_50 += 1

            # ATR-14 (Wilder's) and 50d MA extension
            if len(bars_d) >= 15:
                trs = [bars_d[0]["h"] - bars_d[0]["l"]]
                for i in range(1, len(bars_d)):
                    tr = max(
                        bars_d[i]["h"] - bars_d[i]["l"],
                        abs(bars_d[i]["h"] - bars_d[i-1]["c"]),
                        abs(bars_d[i]["l"] - bars_d[i-1]["c"])
                    )
                    trs.append(tr)
                if len(trs) >= 14:
                    atr14 = sum(trs[:14]) / 14
                    for tr in trs[14:]:
                        atr14 = (atr14 * 13 + tr) / 14
                    ma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sum(closes) / len(closes)
                    last_close = closes[-1]
                    ext     = (last_close - ma50) / atr14 if atr14 > 0 else 0
                    adr_pct = (atr14 / last_close * 100)  if last_close > 0 else 0
                    ctx[ticker] = {"atr14": atr14, "ma50": ma50, "ext": ext, "adr_pct": adr_pct}
        except Exception:
            pass

    breadth = {
        "p20": above_20 / breadth_n * 100 if breadth_n > 0 else 0,
        "p50": above_50 / breadth_n * 100 if breadth_n > 0 else 0,
        "n":   breadth_n,
    }
    return avg_vols, breadth, ctx


# ── Live WebSocket feed ───────────────────────────────────────────────────────

def load_live_feed():
    """Read data/live_feed.json written by kotak_feed.py.
    Returns (tickers_dict, is_fresh)."""
    try:
        if not FEED_FILE.exists():
            return {}, False
        raw = json.loads(FEED_FILE.read_text(encoding="utf-8"))
        updated_at = raw.get("updated_at", "")
        try:
            from datetime import datetime as _dt
            feed_time = _dt.fromisoformat(updated_at)
            age_secs  = (datetime.now(IST) - feed_time).total_seconds()
            fresh     = age_secs < FEED_MAX_AGE
        except Exception:
            fresh = False
        return raw.get("tickers", {}), fresh
    except Exception:
        return {}, False


# ── RSI ───────────────────────────────────────────────────────────────────────

def calc_rsi(bars, period=14):
    """Wilder's RSI on close prices. Returns float or None if insufficient data."""
    closes = [b["close"] for b in bars]
    if len(closes) < period + 1:
        return None
    deltas   = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains    = [max(d, 0) for d in deltas]
    losses   = [abs(min(d, 0)) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 1)


# ── Yahoo 5-min fetch ─────────────────────────────────────────────────────────

def fetch_data(ticker):
    url = f"{YF_BASE}/{ticker}.NS?interval=5m&range=5d"
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=5) as r:
                raw = json.loads(r.read())
            res = raw["chart"]["result"][0]
            ts  = res["timestamp"]
            q   = res["indicators"]["quote"][0]
            bars = []
            for i, t in enumerate(ts):
                o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
                if None in (o, h, l, c): continue
                dt_ist = datetime.fromtimestamp(t, tz=IST)
                hhmm   = dt_ist.hour * 100 + dt_ist.minute
                if hhmm < 915 or hhmm > 1515: continue
                bars.append({
                    "ts": t, "dt": dt_ist,
                    "open": o, "high": h, "low": l, "close": c, "volume": v or 0
                })
            return bars
        except Exception:
            time.sleep(1)
    return []


# ── Main scan ─────────────────────────────────────────────────────────────────

def scan():
    print("--- NIFTY 50 LIVE ORB SCAN ---")
    now_ist   = datetime.now(IST)
    today_str = now_ist.date().isoformat()
    print(f"Time: {now_ist.strftime('%Y-%m-%d %H:%M:%S')} IST")
    print("-" * 80)

    # Single-pass cache preload: avg volumes + market breadth + daily ATR/MA context
    avg_day_vols, breadth, daily_ctx = preload_daily_context(today_str)

    # Market breadth header (Jeff Sun regime check — NSE equivalent)
    if breadth["n"] > 0:
        p20, p50 = breadth["p20"], breadth["p50"]
        if p20 >= 60:
            bias_label = "BULLISH"
        elif p20 >= 40:
            bias_label = "NEUTRAL"
        else:
            bias_label = "BEARISH"
        print(f"  Breadth : {p20:.0f}% above 20d SMA | {p50:.0f}% above 50d SMA "
              f"| Regime: {bias_label}  ({breadth['n']} tickers)")

    # Live WebSocket feed
    live_feed, feed_fresh = load_live_feed()
    feed_src = f"LIVE ({len(live_feed)} tickers)" if feed_fresh else "STALE/ABSENT — Yahoo only"
    print(f"  Feed    : {feed_src}")

    # Session fraction for day-volume pace
    session_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    elapsed_min  = max((now_ist - session_open).total_seconds() / 60, 1)
    day_fraction = min(elapsed_min / 375, 1.0)

    results = []

    for ticker in NIFTY_50:
        bars = fetch_data(ticker)
        if not bars:
            continue

        today_bars = [b for b in bars if b["dt"].date().isoformat() == today_str]
        if len(today_bars) < 3:
            continue

        orh       = max(b["high"] for b in today_bars[:3])
        orl       = min(b["low"]  for b in today_bars[:3])
        orb_width = orh - orl
        mid       = (orh + orl) / 2
        if orb_width <= 0 or mid <= 0:
            continue

        width_pct = orb_width / mid * 100
        # Width gate: portfolio backtest (orb_weekly_portfolio.py, IS Feb-May +
        # OOS May-Jul 2026) shows the old >=1.5% hard skip removes ~2/3 of
        # profitable signals (avg OR width is ~1.0-1.2%). Only degenerate
        # ranges (<0.10% — data glitch / no movement) are skipped now.
        if width_pct < 0.10:
            results.append({
                "ticker": ticker,
                "status": f"SKIP-WIDTH ({width_pct:.2f}%<0.10% degenerate)",
                "close": today_bars[-1]["close"], "orh": orh, "orl": orl,
                "vol_ratio": 0, "width_pct": width_pct,
                "time": today_bars[-1]["dt"].strftime('%H:%M'),
                "sector": _ticker_sector(ticker), "adr_pct": None,
            })
            continue

        long_entry  = orh * 1.001
        short_entry = orl * 0.999

        # ── Opening gap vs previous close (informational flag — NOT a hard skip)
        # NSE backtest confirms gap-direction filter hurts WR; large gaps are flagged only.
        yesterday_bars = [b for b in bars if b["dt"].date().isoformat() < today_str]
        gap_pct = None
        if yesterday_bars and today_bars:
            prev_close = yesterday_bars[-1]["close"]
            gap_pct    = (today_bars[0]["open"] - prev_close) / prev_close * 100

        # ── Daily ATR/MA context from preloaded cache
        dctx    = daily_ctx.get(ticker, {})
        atr_ext = dctx.get("ext")      # (last_close - 50d_MA) / ATR14
        adr_pct = dctx.get("adr_pct")  # ATR14 / price * 100

        # ── Live feed vs Yahoo fallback
        fd         = live_feed.get(ticker, {}) if feed_fresh else {}
        latest_bar = today_bars[-1]
        close_px   = float(fd["ltp"]) if fd.get("ltp") else latest_bar["close"]

        if fd.get("vwap"):
            vwap = float(fd["vwap"])
        else:
            cum_tp_vol = sum((b["high"]+b["low"]+b["close"])/3 * max(b["volume"], 1)
                            for b in today_bars)
            cum_vol    = sum(max(b["volume"], 1) for b in today_bars)
            vwap       = cum_tp_vol / cum_vol if cum_vol > 0 else close_px

        # ── Volume
        ref_idx = len(bars) - 1
        if bars[ref_idx]["volume"] == 0 and ref_idx > 0:
            ref_idx -= 1
        prev_start  = max(0, ref_idx - 20)
        prev_vols   = [bars[j]["volume"] for j in range(prev_start, ref_idx)]
        avg_bar_vol = sum(prev_vols) / len(prev_vols) if prev_vols else 1.0
        vol_ratio   = bars[ref_idx]["volume"] / avg_bar_vol if avg_bar_vol > 0 else 0

        day_vol      = int(fd["volume"]) if fd.get("volume") else 0
        avg_day      = avg_day_vols.get(ticker, 0)
        expected_vol = avg_day * day_fraction
        day_vol_pace = day_vol / expected_vol if expected_vol > 0 else 0

        if vol_ratio > 0:
            eff_vol, vol_src = vol_ratio, "b"
        elif day_vol_pace > 0:
            eff_vol, vol_src = day_vol_pace, "d"
        else:
            eff_vol, vol_src = 0.0, "-"
        vol_ok = eff_vol >= 2.0

        rsi = calc_rsi(bars[:ref_idx + 1])

        tgt1_long  = close_px + orb_width * 1.5 if close_px > long_entry else None
        tgt2_long  = close_px + orb_width * 2.5 if close_px > long_entry else None
        tgt1_short = close_px - orb_width * 1.5 if close_px < short_entry else None
        tgt2_short = close_px - orb_width * 2.5 if close_px < short_entry else None

        vwap_ok_long  = close_px > vwap
        vwap_ok_short = close_px < vwap

        rsi_ok_long  = rsi is None or rsi >= 50
        rsi_ok_short = rsi is None or rsi <= 50
        rsi_str = f"{rsi:.0f}" if rsi is not None else "?"

        pos_pct = (close_px - orl) / orb_width * 100

        dist_long  = (long_entry  - close_px) / close_px * 100
        dist_short = (close_px - short_entry) / close_px * 100

        spike_orh = (today_bars[0]["high"] == orh and
                     (orh - today_bars[0]["close"]) / orh > 0.003)
        spike_orl = (today_bars[0]["low"]  == orl and
                     (today_bars[0]["close"] - orl) / orl > 0.003)

        failed_long  = any(b["high"] >= orh * 0.998 and b["close"] < long_entry
                           for b in today_bars[3:])
        failed_short = any(b["low"]  <= orl * 1.002 and b["close"] > short_entry
                           for b in today_bars[3:])

        vol_str = f"{eff_vol:.1f}{vol_src}"

        # ── ATR extension suffix (from 50d MA — Jeff Sun overextension check)
        ext_tag = ""
        if atr_ext is not None:
            if atr_ext > 8:
                ext_tag = " [OVEREXT]"    # >8× ATR above 50d MA — high reversal risk
            elif atr_ext > 6:
                ext_tag = " [ext]"        # 6-8× — approaching extension zone

        # ── Large gap annotation (>5% — warning only, not a hard skip per NSE backtest)
        gap_tag = (f" [gap{gap_pct:+.1f}%]" if gap_pct is not None and abs(gap_pct) > 5
                   else "")

        # ── Entry-window tag: validated window is 09:30-11:30 IST
        # (orb_weekly_portfolio.py V5 — chosen in-sample, held up best OOS).
        # Signals after 11:30 are flagged, not hidden: human decides.
        late_tag = " [LATE >11:30]" if (now_ist.hour * 100 + now_ist.minute) > 1130 else ""

        # ── Status assignment
        if close_px > long_entry:
            if vol_ok and vwap_ok_long and rsi_ok_long:
                status = f">>> ENTRY LONG (vol{vol_str}+VWAP+RSI OK){ext_tag}{gap_tag}{late_tag}"
            elif not rsi_ok_long:
                status = f"BREAKOUT LONG (RSI FAIL {rsi_str} — skip){ext_tag}"
            elif not vwap_ok_long:
                status = f"BREAKOUT LONG (VWAP FAIL — skip){ext_tag}"
            else:
                status = f"BREAKOUT LONG (LOW VOL {vol_str} — wait){ext_tag}"
        elif close_px < short_entry:
            if vol_ok and vwap_ok_short and rsi_ok_short:
                status = f">>> ENTRY SHORT (vol{vol_str}+VWAP+RSI OK){ext_tag}{gap_tag}{late_tag}"
            elif not rsi_ok_short:
                status = f"BREAKOUT SHORT (RSI FAIL {rsi_str} — skip){ext_tag}"
            elif not vwap_ok_short:
                status = f"BREAKOUT SHORT (VWAP FAIL — skip){ext_tag}"
            else:
                status = f"BREAKOUT SHORT (LOW VOL {vol_str} — wait){ext_tag}"
        elif failed_long and not failed_short:
            spike_tag = " [spike-ORH]" if spike_orh else ""
            status = f"FAILED-ORH{spike_tag} (tested {orh:.0f}, reversed — skip)"
        elif failed_short and not failed_long:
            spike_tag = " [spike-ORL]" if spike_orl else ""
            status = f"FAILED-ORL{spike_tag} (tested {orl:.0f}, reversed — skip)"
        elif dist_long <= 0.15:
            if not rsi_ok_long:
                status = f"NEAR LONG (RSI weak {rsi_str} — low priority)"
            else:
                status = f"NEAR LONG ({dist_long:.2f}% away, VWAP {'ok' if vwap_ok_long else 'fail'})"
        elif dist_short <= 0.15:
            if not rsi_ok_short:
                status = f"NEAR SHORT (RSI weak {rsi_str} — low priority)"
            else:
                status = f"NEAR SHORT ({dist_short:.2f}% away, VWAP {'ok' if vwap_ok_short else 'fail'})"
        elif pos_pct < 35 and (rsi is None or rsi < 50):
            status = f"WEAK (pos={pos_pct:.0f}%, RSI={rsi_str} — bearish bias)"
        elif pos_pct > 65 and (rsi is None or rsi > 50):
            status = f"WATCH-LONG (pos={pos_pct:.0f}%, RSI={rsi_str})"
        else:
            status = f"WATCHING (pos={pos_pct:.0f}%)"

        results.append({
            "ticker":    ticker,
            "sector":    _ticker_sector(ticker),
            "status":    status,
            "close":     close_px,
            "orh":       orh,
            "orl":       orl,
            "width_pct": width_pct,
            "vwap":      vwap,
            "vol_ratio": eff_vol,
            "vol_src":   vol_src,
            "rsi":       rsi,
            "adr_pct":   adr_pct,
            "time":      latest_bar["dt"].strftime('%H:%M'),
            "tgt1":      tgt1_long or tgt1_short,
            "tgt2":      tgt2_long or tgt2_short,
            "stop":      orl if close_px > long_entry else (orh if close_px < short_entry else None),
        })

    # ── Sort
    def sort_key(r):
        s = r["status"]
        if ">>> ENTRY"  in s: return 0
        if "WATCH-LONG" in s: return 1
        if "NEAR"       in s: return 2
        if "BREAKOUT"   in s: return 3
        if "WATCHING"   in s: return 4
        if "WEAK"       in s: return 5
        if "FAILED"     in s: return 8
        if "SKIP"       in s: return 9
        return 6

    results.sort(key=sort_key)

    # ── Print table
    print(f"\n{'Ticker':<12} | {'Time':<5} | {'Price':>8} | {'ORH':>8} | {'ORL':>8} | "
          f"{'Wid%':>5} | {'Vol':>6} | {'ADR%':>5} | {'RSI':>5} | Status")
    print("-" * 120)
    for r in results:
        tgt_str = ""
        if r.get("tgt1") and r.get("stop"):
            tgt_str = f"  [T1:{r['tgt1']:.1f} T2:{r.get('tgt2',0):.1f} SL:{r['stop']:.1f}]"
        rsi_val = f"{r['rsi']:.0f}" if r.get("rsi") is not None else "?"
        vol_val = f"{r['vol_ratio']:.1f}{r.get('vol_src','')}" if r.get("vol_ratio", 0) > 0 else "  -"
        adr_val = f"{r['adr_pct']:.1f}" if r.get("adr_pct") is not None else "  -"
        print(f"{r['ticker']:<12} | {r['time']:<5} | {r['close']:>8.2f} | {r['orh']:>8.2f} | "
              f"{r['orl']:>8.2f} | {r.get('width_pct',0):>5.1f}% | {vol_val:>6} | "
              f"{adr_val:>5} | {rsi_val:>5} | {r['status']}{tgt_str}")

    # ── Signal summary
    entries = [r for r in results if ">>> ENTRY"  in r["status"]]
    watches = [r for r in results if "WATCH-LONG" in r["status"] or "NEAR" in r["status"]]
    failed  = [r for r in results if "FAILED"     in r["status"]]
    skipped = [r for r in results if "SKIP"       in r["status"]]
    weak    = [r for r in results if "WEAK"       in r["status"]]
    print(f"\nEntries: {len(entries)} | Watch/Near: {len(watches)} | "
          f"Failed-ORB: {len(failed)} | Weak: {len(weak)} | Width-skip: {len(skipped)}")
    if entries:
        print(f"ACTION: {[r['ticker'] for r in entries]}")
    if watches:
        print(f"WATCH:  {[r['ticker'] for r in watches]}")

    # ── Sector snapshot (Jeff Sun thesis-board equivalent for NSE)
    from collections import defaultdict
    sec_stats = defaultdict(lambda: {"E": 0, "W": 0, "F": 0, "X": 0, "tickers": []})
    for r in results:
        s = r["sector"]
        st = r["status"]
        if ">>> ENTRY"  in st: sec_stats[s]["E"] += 1; sec_stats[s]["tickers"].append(r["ticker"] + "(E)")
        elif "WATCH-LONG" in st or "NEAR" in st: sec_stats[s]["W"] += 1; sec_stats[s]["tickers"].append(r["ticker"] + "(W)")
        elif "FAILED" in st or "WEAK" in st:     sec_stats[s]["F"] += 1; sec_stats[s]["tickers"].append(r["ticker"] + "(f)")
        elif "SKIP" not in st:                   sec_stats[s]["X"] += 1

    active = {s: v for s, v in sec_stats.items() if v["E"] or v["W"] or v["F"]}
    if active:
        print(f"\n{'-'*80}")
        print(f"{'SECTOR':<10} | {'E':>3} | {'W':>3} | {'F':>3} | Score | Leading tickers")
        print(f"{'-'*80}")
        for sec in sorted(active, key=lambda s: -(active[s]["E"]*3 + active[s]["W"] - active[s]["F"])):
            v     = active[sec]
            score = v["E"] * 3 + v["W"] - v["F"]
            arrow = "^" if score > 0 else ("v" if score < 0 else "-")
            leads = " ".join(v["tickers"][:5])
            print(f"{arrow} {sec:<9} | {v['E']:>3} | {v['W']:>3} | {v['F']:>3} | {score:>5} | {leads}")
        print(f"  E=Entry  W=Watch/Near  F=Failed/Weak")


if __name__ == "__main__":
    scan()
