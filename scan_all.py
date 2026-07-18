"""
Multi-strategy live scanner — all 4 strategies in one pass.
  1. ORB v3            (Active)
  2. Gap Fill Down-Long (Proposed — pending approval)
  3. BB Squeeze         (Proposed)
  4. PDH Continuation   (Proposed)

Run: python scan_all.py
"""
import sys, os, json, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT     = Path(__file__).parent
LOG_FILE = ROOT / "logs" / "scan_all.log"

env_file = ROOT / ".env"
if env_file.exists():
    for _line in env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# Tee all print() output to both stdout and log file
class _Tee:
    def __init__(self, *streams): self._s = streams
    def write(self, d):
        for s in self._s:
            try: s.write(d)
            except Exception: pass
    def flush(self):
        for s in self._s:
            try: s.flush()
            except Exception: pass

_log_fh = open(LOG_FILE, "a", encoding="utf-8", errors="replace")
sys.stdout = _Tee(sys.__stdout__, _log_fh)
sys.stderr = _Tee(sys.__stderr__, _log_fh)


def _send_telegram(text):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    data = json.dumps({
        "chat_id": chat_id, "text": text,
        "parse_mode": "Markdown", "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            print(f"  [Telegram sent OK — {len(text)} chars]")
    except Exception as e:
        print(f"  [Telegram ERROR: {e}]")

# Pull shared helpers from scan_orb_live
sys.path.insert(0, str(Path(__file__).parent))
from scan_orb_live import (
    fetch_data, load_live_feed, calc_rsi,
    preload_daily_context, NIFTY_50, NIFTY_NEXT_50, MIDCAP_50_LIQUID,
    _ticker_sector,
)

IST = timezone(timedelta(hours=5, minutes=30))

# ── Universe config — edit here to pick which groups to scan ──────────────────
# Set True/False per group. Changes take effect on next scan run.
SCAN_GROUPS = {
    "N50":   True,   # Nifty 50        (50 stocks)  — always liquid, core universe
    "NXT50": True,   # Nifty Next 50   (50 stocks)  — liquid large-caps outside N50
    "MID50": False,  # Nifty Midcap 50 (50 stocks)  — higher beta; set True to enable
}

# Min avg daily volume (shares) for BUY NOW to fire for each group.
# Stocks below this threshold are demoted to WATCHING even if all gates pass.
MIN_VOL_FOR_ENTRY = {
    "N50":   0,          # no filter — all N50 stocks are liquid
    "NXT50": 300_000,    # ~3L shares/day minimum
    "MID50": 500_000,    # ~5L shares/day minimum
}

# Build universe and group lookup from config above
_TICKER_GROUP: dict[str, str] = {}
for _grp, _enabled in SCAN_GROUPS.items():
    if not _enabled:
        continue
    _list = {"N50": NIFTY_50, "NXT50": NIFTY_NEXT_50, "MID50": MIDCAP_50_LIQUID}[_grp]
    for _t in _list:
        _TICKER_GROUP.setdefault(_t, _grp)   # N50 wins if a ticker appears in multiple lists

UNIVERSE = list(_TICKER_GROUP.keys())


# ── Utility ───────────────────────────────────────────────────────────────────

def _now_hhmm():
    n = datetime.now(IST)
    return n.hour * 100 + n.minute

def _in_entry_window():
    h = _now_hhmm()
    return 930 <= h <= 1300

def _atr14(bars):
    if len(bars) < 2:
        return bars[-1]["close"] * 0.005 if bars else 1
    trs = []
    for i in range(max(1, len(bars) - 15), len(bars)):
        tr = max(
            bars[i]["high"] - bars[i]["low"],
            abs(bars[i]["high"] - bars[i-1]["close"]),
            abs(bars[i]["low"]  - bars[i-1]["close"])
        )
        trs.append(tr)
    return sum(trs) / len(trs) if trs else bars[-1]["close"] * 0.005


# ── Strategy 1: ORB v3 ────────────────────────────────────────────────────────

def check_orb(today_bars, bars, fd, avg_day_vol, day_fraction):
    if len(today_bars) < 3:
        return None

    orh = max(b["high"] for b in today_bars[:3])
    orl = min(b["low"]  for b in today_bars[:3])
    orb_w = orh - orl
    mid   = (orh + orl) / 2
    if orb_w <= 0 or mid <= 0 or orb_w / mid * 100 < 1.5:
        return None

    long_entry  = orh * 1.001
    short_entry = orl * 0.999

    close_px = float(fd["ltp"]) if fd.get("ltp") else today_bars[-1]["close"]

    if fd.get("vwap"):
        vwap = float(fd["vwap"])
    else:
        tpvol = sum((b["high"]+b["low"]+b["close"])/3 * max(b["volume"],1) for b in today_bars)
        cvol  = sum(max(b["volume"],1) for b in today_bars)
        vwap  = tpvol / cvol if cvol > 0 else close_px

    # Bar vol ratio
    ref = len(bars) - 1
    if bars[ref]["volume"] == 0 and ref > 0:
        ref -= 1
    pvols = [bars[j]["volume"] for j in range(max(0, ref-20), ref)]
    avg_bar = sum(pvols) / len(pvols) if pvols else 1
    vol_r   = bars[ref]["volume"] / avg_bar if avg_bar > 0 else 0

    if vol_r == 0 and avg_day_vol > 0:
        dv    = int(fd["volume"]) if fd.get("volume") else 0
        vol_r = dv / (avg_day_vol * day_fraction) if day_fraction > 0 else 0

    rsi = calc_rsi(bars[:ref+1])
    vol_ok  = vol_r >= 2.0
    vwap_lk = close_px > vwap
    vwap_sk = close_px < vwap
    rsi_lk  = rsi is None or rsi >= 50
    rsi_sk  = rsi is None or rsi <= 50

    failed_long  = any(b["high"] >= orh * 0.998 and b["close"] < long_entry  for b in today_bars[3:])
    failed_short = any(b["low"]  <= orl * 1.002 and b["close"] > short_entry for b in today_bars[3:])

    if close_px > long_entry and not failed_long:
        direction = "LONG"
        gates_ok  = vol_ok and vwap_lk and rsi_lk
        fails     = [] + (["vol"] if not vol_ok else []) + \
                    (["VWAP"] if not vwap_lk else []) + \
                    (["RSI"] if not rsi_lk else [])
    elif close_px < short_entry and not failed_short:
        direction = "SHORT"
        gates_ok  = vol_ok and vwap_sk and rsi_sk
        fails     = [] + (["vol"] if not vol_ok else []) + \
                    (["VWAP"] if not vwap_sk else []) + \
                    (["RSI"] if not rsi_sk else [])
    else:
        return None

    sl = orl if direction == "LONG" else orh
    t1 = close_px + orb_w * 1.5 * (1 if direction == "LONG" else -1)
    t2 = close_px + orb_w * 2.5 * (1 if direction == "LONG" else -1)

    status = "ENTRY" if gates_ok else ("BREAKOUT-" + "+".join(fails) + "-FAIL")
    return {
        "strategy": "ORB",
        "status":   status,
        "direction": direction,
        "price": close_px,
        "entry": close_px,
        "stop":  sl,
        "t1":    t1,
        "t2":    t2,
        "vol_r": vol_r,
        "rsi":   rsi,
        "notes": f"ORB {orb_w/mid*100:.1f}% wid | vol{vol_r:.1f}x | RSI {rsi:.0f}" if rsi else "",
    }


# ── Strategy 2: Gap Fill Down-Long ───────────────────────────────────────────

def check_gap_fill(today_bars, bars, today_str):
    yesterday = [b for b in bars if b["dt"].date().isoformat() < today_str]
    if not yesterday or not today_bars:
        return None

    prev_close = yesterday[-1]["close"]
    today_open = today_bars[0]["open"]
    gap_pct    = (today_open - prev_close) / prev_close * 100

    if not (-1.0 <= gap_pct <= -0.4):
        return None

    # Volume gate: first-bar volume vs 20-bar avg
    pvols  = [b["volume"] for b in yesterday[-20:] if b["volume"] > 0]
    avg_v  = sum(pvols) / len(pvols) if pvols else 0
    fb_vol = today_bars[0]["volume"]
    vol_ok = avg_v == 0 or (fb_vol >= 2.0 * avg_v)

    stop      = today_open * 0.994
    cur_price = today_bars[-1]["close"]
    gap_size  = abs(prev_close - today_open)

    if cur_price < stop:
        return {"strategy": "GAP-FILL", "status": "STOPPED-OUT",
                "prev_close": prev_close, "gap_pct": gap_pct,
                "entry": today_open, "stop": stop, "target": prev_close,
                "price": cur_price, "vol_ok": vol_ok,
                "rsi_ok": True, "vwap_ok": True}

    # Check if price continued falling in first 5 bars (gap continuation = fail)
    if len(today_bars) >= 5:
        if any(b["close"] < stop for b in today_bars[:5]):
            return {"strategy": "GAP-FILL", "status": "FAILED-CONTINUATION",
                    "prev_close": prev_close, "gap_pct": gap_pct, "price": cur_price,
                    "rsi_ok": True, "vwap_ok": True}

    fill_pct = (cur_price - today_open) / gap_size * 100 if gap_size > 0 else 0

    # RSI gate: must show upward momentum (≥50) to confirm buyers are in control
    rsi    = calc_rsi(bars)
    rsi_ok = rsi is None or rsi >= 50

    # VWAP gate: price must be at or above VWAP — institutional demand confirmation
    tpvol  = sum((b["high"]+b["low"]+b["close"])/3 * max(b["volume"],1) for b in today_bars)
    cvol   = sum(max(b["volume"],1) for b in today_bars)
    vwap   = tpvol / cvol if cvol > 0 else cur_price
    vwap_ok = cur_price >= vwap

    if cur_price >= prev_close:
        status = "FILLED"
    elif fill_pct >= 50:
        status = "FILLING (50%+)"
    elif fill_pct >= 30:
        status = "FILLING"
    else:
        status = "OPEN"

    rsi_str = f"{rsi:.0f}" if rsi is not None else "?"
    notes = (f"gap {gap_pct:.2f}% | fill {fill_pct:.0f}%"
             f" | vol {'ok' if vol_ok else 'LOW'}"
             f" | RSI {rsi_str}{'[ok]' if rsi_ok else '[SKIP]'}"
             f" | VWAP {vwap:.1f}{'[ok]' if vwap_ok else '[SKIP]'}")

    return {
        "strategy": "GAP-FILL",
        "status":   status,
        "direction": "LONG",
        "prev_close": prev_close,
        "gap_pct":   gap_pct,
        "entry":     today_open,
        "stop":      stop,
        "t1":        prev_close,
        "t2":        None,
        "price":     cur_price,
        "fill_pct":  fill_pct,
        "vol_ok":    vol_ok,
        "rsi":       rsi,
        "rsi_ok":    rsi_ok,
        "vwap":      vwap,
        "vwap_ok":   vwap_ok,
        "notes":     notes,
    }


# ── Strategy 3: BB Squeeze ───────────────────────────────────────────────────

def _calc_bb(bars, period=20, mult=2.0):
    closes = [b["close"] for b in bars]
    out = []
    for i in range(len(closes)):
        if i < period - 1:
            out.append(None)
        else:
            w  = closes[i - period + 1 : i + 1]
            ma = sum(w) / period
            sd = (sum((x - ma)**2 for x in w) / period) ** 0.5
            out.append((ma + mult * sd, ma, ma - mult * sd, mult * 2 * sd))  # upper,mid,lower,width
    return out


def check_bb_squeeze(bars, min_sq=5):
    if len(bars) < 25:
        return None

    bb = _calc_bb(bars)
    valid = [(i, b) for i, b in enumerate(bb) if b is not None]
    if len(valid) < min_sq + 2:
        return None

    # Count consecutive bars where width is narrowing at the tail
    widths = [b[3] for _, b in valid]
    n_sq = 0
    for i in range(len(widths) - 1, 0, -1):
        if widths[i] <= widths[i - 1]:
            n_sq += 1
        else:
            break

    if n_sq < min_sq:
        return None

    cur_bar = bars[-1]
    cur_bb  = valid[-1][1]  # (upper, mid, lower, width)
    atr     = _atr14(bars)

    # Volume
    vols   = [b["volume"] for b in bars[-21:-1] if b["volume"] > 0]
    avg_v  = sum(vols) / len(vols) if vols else 1
    vol_r  = cur_bar["volume"] / avg_v if avg_v > 0 else 0

    body      = abs(cur_bar["close"] - cur_bar["open"])
    strong    = body >= 0.5 * atr
    is_long   = cur_bar["close"] > cur_bb[0]
    is_short  = cur_bar["close"] < cur_bb[2]

    if not (is_long or is_short):
        # No breakout yet — report WATCHING
        return {
            "strategy":  "BB-SQUEEZE",
            "status":    "WATCHING",
            "direction": "TBD",
            "n_sq":      n_sq,
            "price":     cur_bar["close"],
            "upper_bb":  cur_bb[0],
            "lower_bb":  cur_bb[2],
            "bb_width":  cur_bb[3],
            "entry":     None,
            "stop":      None,
            "t1":        None,
            "t2":        None,
            "notes":     f"{n_sq}-bar squeeze | width {cur_bb[3]:.2f} | watch {cur_bb[0]:.1f}/{cur_bb[2]:.1f}",
        }

    direction = "LONG" if is_long else "SHORT"
    sign      = 1 if is_long else -1
    entry     = cur_bar["close"]
    stop      = entry - sign * atr
    t1        = entry + sign * atr
    t2        = entry + sign * 2 * atr

    if vol_r < 1.8 or not strong:
        status = "BREAKOUT-LOW-QUALITY"
        notes  = f"{n_sq}-sq | vol{vol_r:.1f}x {'LOW' if vol_r < 1.8 else 'ok'} | body {'ok' if strong else 'WEAK'}"
    else:
        status = "ENTRY"
        notes  = f"{n_sq}-bar squeeze | vol{vol_r:.1f}x | body ok"

    return {
        "strategy":  "BB-SQUEEZE",
        "status":    status,
        "direction": direction,
        "n_sq":      n_sq,
        "price":     entry,
        "entry":     entry,
        "stop":      stop,
        "t1":        t1,
        "t2":        t2,
        "vol_r":     vol_r,
        "notes":     notes,
    }


# ── Strategy 4: PDH Gap Continuation ─────────────────────────────────────────

def check_pdh(today_bars, bars, today_str):
    yesterday = [b for b in bars if b["dt"].date().isoformat() < today_str]
    if not yesterday or len(today_bars) < 5:
        return None

    pdh        = max(b["high"] for b in yesterday)
    prev_close = yesterday[-1]["close"]
    today_open = today_bars[0]["open"]

    gap_pct = (today_open - prev_close) / prev_close * 100
    if not (0.3 <= gap_pct <= 1.5):
        return None
    if today_open <= pdh:
        return None
    if today_bars[0]["close"] <= today_bars[0]["open"]:  # first bar must be bullish
        return None
    if not all(b["close"] > pdh for b in today_bars[:5]):
        return None

    gap_size = today_open - prev_close
    stop     = pdh * 0.998
    t1       = today_open
    t2       = pdh + 2 * gap_size

    cur_price = today_bars[-1]["close"]

    # Look for pullback-to-PDH entry trigger
    entry_bar = None
    for b in today_bars[4:]:
        if b["low"] <= pdh * 1.003 and b["close"] > pdh:
            entry_bar = b
            break

    if entry_bar is None:
        # No pullback yet
        near_pdh = cur_price <= pdh * 1.006
        return {
            "strategy":  "PDH",
            "status":    "WATCHING-NEAR-PDH" if near_pdh else "RUNNING-AWAY",
            "direction": "LONG",
            "pdh":       pdh,
            "gap_pct":   gap_pct,
            "price":     cur_price,
            "entry":     None,
            "stop":      stop,
            "t1":        t1,
            "t2":        t2,
            "notes":     f"PDH {pdh:.1f} | gap +{gap_pct:.1f}% | {'near PDH' if near_pdh else 'price ran'}",
        }

    entry_price = entry_bar["close"]

    if cur_price < stop:
        status = "STOPPED-OUT"
    elif cur_price >= t2:
        status = "T2-HIT"
    elif cur_price >= t1:
        status = "T1-HIT-TRAILING"
    else:
        status = "IN-TRADE"

    pnl = cur_price - entry_price
    return {
        "strategy":  "PDH",
        "status":    status,
        "direction": "LONG",
        "pdh":       pdh,
        "gap_pct":   gap_pct,
        "price":     cur_price,
        "entry":     entry_price,
        "stop":      stop,
        "t1":        t1,
        "t2":        t2,
        "pnl":       pnl,
        "notes":     f"PDH {pdh:.1f} | entry {entry_price:.1f} | P&L {pnl:+.1f}",
    }


# ── Main scan ─────────────────────────────────────────────────────────────────

def scan():
    now_ist   = datetime.now(IST)
    today_str = now_ist.date().isoformat()
    hhmm      = now_ist.hour * 100 + now_ist.minute
    in_window = _in_entry_window()

    enabled_grps = "+".join(g for g, on in SCAN_GROUPS.items() if on)
    print("=" * 80)
    print(f"  MULTI-STRATEGY SCAN  ·  {len(UNIVERSE)} tickers [{enabled_grps}]"
          f"  ·  {now_ist.strftime('%Y-%m-%d %H:%M')} IST")
    print("=" * 80)

    avg_day_vols, breadth, daily_ctx = preload_daily_context(today_str, universe=UNIVERSE)
    live_feed, feed_fresh = load_live_feed()

    p20 = breadth["p20"]
    regime = "BULLISH" if p20 >= 60 else ("NEUTRAL" if p20 >= 40 else "BEARISH")
    feed_tag = f"LIVE ({len(live_feed)} tickers)" if feed_fresh else "STALE"
    entry_tag = "OPEN" if in_window else f"CLOSED at 13:00 (now {now_ist.strftime('%H:%M')})"
    grp_tag = "+".join(g for g, on in SCAN_GROUPS.items() if on)

    print(f"  Regime: {regime} ({p20:.0f}% > 20d SMA)  |  Feed: {feed_tag}  |  Entry window: {entry_tag}")
    print()

    session_open = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    elapsed_min  = max((now_ist - session_open).total_seconds() / 60, 1)
    day_fraction = min(elapsed_min / 375, 1.0)

    # Buckets
    buy_now    = []   # entry-quality signals, all gates passed
    watching   = []   # setup forming / near-entry
    historical = []   # triggered earlier today
    no_signal  = []   # nothing interesting

    print(f"  Scanning {len(UNIVERSE)} tickers  [{grp_tag}]", end="", flush=True)

    confluence          = []  # tickers with both BB squeeze + ORB entry
    gap_fill_candidates = []  # collected for market-wide gap filter (routed after loop)

    for ticker in UNIVERSE:
        print(".", end="", flush=True)
        bars = fetch_data(ticker)
        if not bars:
            continue

        today_bars = [b for b in bars if b["dt"].date().isoformat() == today_str]
        fd         = live_feed.get(ticker, {}) if feed_fresh else {}
        avg_d      = avg_day_vols.get(ticker, 0)
        sector     = _ticker_sector(ticker)
        group      = _TICKER_GROUP.get(ticker, "N50")
        min_vol    = MIN_VOL_FOR_ENTRY.get(group, 0)
        vol_liquid = avg_d >= min_vol  # False → demote to WATCHING regardless of gates

        base = {"ticker": ticker, "sector": sector, "group": group}

        # ── ORB ──
        orb = check_orb(today_bars, bars, fd, avg_d, day_fraction)
        orb_entry = orb and orb["status"] == "ENTRY"
        if orb:
            row = {**base, **orb}
            if orb_entry:
                if in_window and vol_liquid:
                    buy_now.append(row)
                elif in_window and not vol_liquid:
                    row = dict(row)
                    row["notes"] = row.get("notes","") + f" | SKIP: thin({avg_d/1e5:.1f}L<{min_vol/1e5:.0f}L)"
                    watching.append(row)
                else:
                    historical.append({**row, "note_time": "post-window"})
            elif "FAIL" in orb["status"]:
                watching.append(row)

        # ── Gap Fill — collect only; route after loop with market-wide filter ──
        gf = check_gap_fill(today_bars, bars, today_str)
        if gf:
            gap_fill_candidates.append({**base, **gf})

        # ── BB Squeeze ──
        bb = check_bb_squeeze(bars)
        bb_compressed = bb and bb["status"] in ("WATCHING", "ENTRY", "BREAKOUT-LOW-QUALITY")
        if bb:
            row = {**base, **bb}
            if bb["status"] == "ENTRY":
                if in_window:
                    buy_now.append(row)
                else:
                    watching.append({**row, "status": "BB-ENTRY-POST-WINDOW"})
            elif bb["status"] == "WATCHING":
                watching.append(row)
            elif "QUALITY" in bb["status"]:
                watching.append(row)

        # ── Confluence: BB squeeze compressed + ORB entry both fire ──
        if bb_compressed and orb_entry and in_window:
            n_sq = bb.get("n_sq", 0)
            confluence.append({
                **base,
                "strategy":  "CONFLUENCE",
                "status":    "ENTRY",
                "direction": orb["direction"],
                "price":     orb["price"],
                "entry":     orb["entry"],
                "stop":      orb["stop"],
                "t1":        orb["t1"],
                "t2":        orb["t2"],
                "vol_r":     orb.get("vol_r", 0),
                "n_sq":      n_sq,
                "notes":     f"BB {n_sq}-bar squeeze + ORB {orb['direction']} | vol{orb.get('vol_r',0):.1f}x | {orb.get('notes','')}",
            })

        # ── PDH ──
        pdh = check_pdh(today_bars, bars, today_str)
        if pdh:
            row = {**base, **pdh}
            if pdh["status"] == "WATCHING-NEAR-PDH":
                if in_window:
                    buy_now.append(row)
                else:
                    watching.append(row)
            elif pdh["status"] in ("IN-TRADE", "T1-HIT-TRAILING"):
                historical.append(row)
            elif pdh["status"] in ("T2-HIT", "STOPPED-OUT"):
                historical.append(row)

    print()

    # ── Route Gap Fill candidates with all false-positive gates ──────────────
    # Gate 1: market-wide gap down → gap fills structurally unreliable
    gap_down_count  = sum(1 for r in gap_fill_candidates if r.get("gap_pct", 0) <= -0.4)
    market_gap_down = gap_down_count >= 5

    if market_gap_down:
        print(f"\n  [MARKET-WIDE GAP-DOWN]: {gap_down_count}/50 stocks gapped down -- "
              f"Gap Fill LONG suspended (short-covering dominates, fills unreliable)")

    for row in gap_fill_candidates:
        status     = row.get("status", "")
        fill_pct   = row.get("fill_pct", 0)
        vol_ok     = row.get("vol_ok", True)
        rsi_ok     = row.get("rsi_ok", True)
        vwap_ok    = row.get("vwap_ok", True)
        grp        = row.get("group", "N50")
        avg_d_row  = avg_day_vols.get(row.get("ticker",""), 0)
        min_v      = MIN_VOL_FOR_ENTRY.get(grp, 0)
        vol_liquid = avg_d_row >= min_v

        if status in ("OPEN", "FILLING", "FILLING (50%+)"):
            skip = []
            if market_gap_down:      skip.append(f"mkt-gap({gap_down_count})")
            if fill_pct <= 0:        skip.append("fill<0")
            if not vol_ok:           skip.append("vol-LOW")
            if not rsi_ok:           skip.append("RSI<50")
            if not vwap_ok:          skip.append("below-VWAP")
            if not vol_liquid:       skip.append(f"thin({avg_d_row/1e5:.1f}L<{min_v/1e5:.0f}L)")

            if skip:
                row = dict(row)
                row["notes"] = row.get("notes", "") + f" | SKIP: {','.join(skip)}"
                watching.append(row)
            elif in_window:
                buy_now.append(row)
            else:
                watching.append(row)
        elif status == "FILLED":
            historical.append(row)
        elif "STOP" in status or "FAIL" in status:
            historical.append(row)

    # ── OUTPUT ───────────────────────────────────────────────────────────────

    def fmt_price(v):
        return f"{v:>8.2f}" if v is not None else "       -"

    def print_table(rows, show_entry=True):
        if not rows:
            print("  (none)")
            return
        hdr = f"  {'Ticker':<12} {'Grp':<6} {'Sector':<10} {'Strat':<12} {'Dir':<6} {'Price':>8}"
        if show_entry:
            hdr += f" {'Entry':>8} {'T1':>8} {'T2':>9} {'SL':>8}"
        hdr += f"  Notes"
        print(hdr)
        print("  " + "-" * 118)
        for r in rows:
            grp_col = r.get("group", "N50")
            line = (f"  {r['ticker']:<12} {grp_col:<6} {r['sector']:<10} {r['strategy']:<12}"
                    f" {r.get('direction','?'):<6} {fmt_price(r.get('price'))}")
            if show_entry:
                line += (f" {fmt_price(r.get('entry'))}"
                         f" {fmt_price(r.get('t1'))}"
                         f" {fmt_price(r.get('t2'))}"
                         f" {fmt_price(r.get('stop'))}")
            line += f"  {r.get('notes', r.get('status',''))}"
            print(line)

    # Section 0 — CONFLUENCE (highest priority)
    if confluence:
        print(f"\n{'*'*80}")
        print(f"  *** CONFLUENCE SIGNALS ({len(confluence)}) — BB Squeeze + ORB both confirmed ***")
        print(f"{'*'*80}")
        print_table(sorted(confluence, key=lambda r: -r.get("n_sq", 0)))

    # Section 1 — BUY NOW
    window_note = "" if in_window else "  [entry window closed - informational only]"
    print(f"\n### BUY NOW ###  ({len(buy_now)} signals){window_note}")
    print_table(sorted(buy_now, key=lambda r: (r['strategy'], r['ticker'])))

    # Section 2 — WATCHING
    print(f"\n--- WATCHING ---  ({len(watching)} setups forming)")
    print_table(sorted(watching, key=lambda r: (r['strategy'], r['ticker'])))

    # Section 3 — TODAY'S RESULTS
    print(f"\n... TODAY'S HISTORY ...  ({len(historical)} completed / in-trade)")
    print_table(sorted(historical, key=lambda r: (r['strategy'], r['ticker'])), show_entry=True)

    # Quick summary
    active_buys = [r for r in buy_now if "POST-WINDOW" not in r.get("status","")]
    print(f"\n{'='*80}")
    print(f"  SUMMARY  ·  {now_ist.strftime('%H:%M')} IST")
    print(f"  Market regime : {regime}  ({p20:.0f}% of Nifty 50 above 20d SMA)")
    print(f"  Entry window  : {'OPEN — new entries allowed' if in_window else 'CLOSED (all strategies cut off at 13:00)'}")
    print(f"  Confluence    : {len(confluence)}  |  Buy signals : {len(active_buys)}  |  Watching : {len(watching)}  |  Historical : {len(historical)}")
    if confluence:
        print(f"  CONFLUENCE    : {[r['ticker'] for r in confluence]}  <-- BB Squeeze + ORB both fired")
    if active_buys:
        print(f"  ACTION NEEDED : {[r['ticker'] for r in active_buys]}")
    if not confluence and not active_buys:
        print(f"  No entry-quality signals within open window.")
    print(f"{'='*80}")

    # ── Telegram notification ─────────────────────────────────────────────────
    _tg_lines = [
        f"*ABUNDANCE SCAN* | {now_ist.strftime('%H:%M')} IST | {now_ist.strftime('%Y-%m-%d')}",
        f"Regime: {regime} ({p20:.0f}% > 20d SMA) | Window: {'OPEN' if in_window else 'CLOSED'}",
    ]

    # Confluence first — highest conviction
    if confluence:
        _tg_lines.append("")
        _tg_lines.append(f"*CONFLUENCE — BB Squeeze + ORB ({len(confluence)} signal(s)):*")
        for r in sorted(confluence, key=lambda x: -x.get("n_sq", 0)):
            e  = r.get("entry") or 0
            t1 = r.get("t1")    or 0
            t2 = r.get("t2")
            sl = r.get("stop")  or 0
            t2s = f" | T2 {t2:.2f}" if t2 else ""
            _tg_lines.append(
                f"  *{r['ticker']}* {r.get('direction','')} @ {r.get('price',0):.2f}\n"
                f"    Entry {e:.2f} | T1 {t1:.2f}{t2s} | SL {sl:.2f}\n"
                f"    {r.get('notes','')}"
            )

    if active_buys:
        _tg_lines.append("")
        _tg_lines.append(f"*BUY NOW ({len(active_buys)} signal(s)):*")
        for r in sorted(active_buys, key=lambda x: x["strategy"]):
            e  = r.get("entry") or 0
            t1 = r.get("t1")    or 0
            t2 = r.get("t2")
            sl = r.get("stop")  or 0
            t2s = f" | T2 {t2:.2f}" if t2 else ""
            _tg_lines.append(
                f"  *{r['ticker']}* ({r['strategy']} {r.get('direction','')}) @ {r.get('price',0):.2f}\n"
                f"    Entry {e:.2f} | T1 {t1:.2f}{t2s} | SL {sl:.2f}\n"
                f"    {r.get('notes','')}"
            )

    if not confluence and not active_buys:
        _tg_lines.append("No entry signals — monitoring.")

    # Always show top squeeze watches
    squeeze_watch = sorted(
        [r for r in watching if r["strategy"] == "BB-SQUEEZE"],
        key=lambda x: -x.get("n_sq", 0)
    )[:5]
    n_sq_total = len([r for r in watching if r["strategy"] == "BB-SQUEEZE"])
    if squeeze_watch:
        _tg_lines.append("")
        _tg_lines.append(f"*BB SQUEEZE ({n_sq_total} stocks compressing):*")
        for r in squeeze_watch:
            _tg_lines.append(f"  {r['ticker']} ({r.get('n_sq',0)}-bar) {r.get('notes','')}")

    # Only send Telegram Mon-Fri, 09:00-13:15 IST
    # 09:00-09:15: pre-open prep | 09:15-09:30: open | 09:30-13:00: entry window | 13:00-13:15: close
    # Prevents spurious messages when the script is run manually in the evening
    tg_ok = (now_ist.weekday() < 5) and (900 <= hhmm <= 1315)
    if tg_ok:
        _tg_lines.append(f"\n_Next scan in ~10 min_")
        _send_telegram("\n".join(_tg_lines))
    else:
        dow = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][now_ist.weekday()]
        print(f"\n  [Telegram suppressed — outside market hours: {dow} {now_ist.strftime('%H:%M')} IST]")


if __name__ == "__main__":
    scan()
