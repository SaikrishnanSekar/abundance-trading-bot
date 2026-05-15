"""
Scheduled ORB propose task — runs at 09:30 IST Mon-Fri via Task Scheduler.
Scans for ORB entry signals, runs gate checks, proposes trade to Telegram.
Writes memory/india/PENDING-TRADE.json — poll script acts on Y reply.
"""
import sys, os, io, json, subprocess, urllib.request
from pathlib import Path
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

IST = timezone(timedelta(hours=5, minutes=30))
PENDING_FILE = ROOT / "memory" / "india" / "PENDING-TRADE.json"


def send_telegram(text):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        (ROOT / "notify_fallback.log").open("a", encoding="utf-8").write(
            f"\n[PROPOSE {datetime.now(IST)}]\n{text}\n"
        )
        print("No Telegram creds — fallback log written.")
        return None
    data = json.dumps({
        "chat_id": chat_id, "text": text,
        "parse_mode": "Markdown", "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
            msg_id = resp.get("result", {}).get("message_id")
            print(f"Telegram sent msg_id={msg_id}")
            return msg_id
    except Exception as e:
        print(f"Telegram error: {e}")
        return None


def run_shell(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           cwd=str(ROOT), timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def get_security_id(sym):
    path = ROOT / "data" / "nse_securities.json"
    if path.exists():
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            return d.get("NSE_EQ", {}).get(sym, {}).get("securityId", "")
        except Exception:
            pass
    return ""


# ── Kill switch ──────────────────────────────────────────────────────────────
if (ROOT / "memory" / "KILL_SWITCH.md").exists():
    print("KILL_SWITCH present — proposal skipped.")
    sys.exit(0)

# ── Market hours check ───────────────────────────────────────────────────────
now  = datetime.now(IST)
hhmm = now.hour * 100 + now.minute
dow  = now.weekday()  # 0=Mon, 6=Sun
today_str = now.date().isoformat()

if dow >= 5 or hhmm < 915 or hhmm > 1515:
    print(f"Market closed (dow={dow}, hhmm={hhmm}) — skipping.")
    sys.exit(0)

holidays_file = ROOT / "data" / "nse_holidays.txt"
if holidays_file.exists():
    for line in holidays_file.read_text().splitlines():
        if line.strip().startswith(today_str):
            print(f"NSE holiday {today_str} — skipping.")
            sys.exit(0)

# ── Run ORB scan ─────────────────────────────────────────────────────────────
import scan_orb_live
buf = io.StringIO()
with redirect_stdout(buf):
    scan_orb_live.scan()
output = buf.getvalue()
print(output)

lines       = output.strip().split("\n")
entry_rows  = [l for l in lines if ">>> ENTRY" in l and "|" in l]
summary     = next((l for l in lines if "Active entries:" in l), "")
skip_count  = next((l.split("Width-skip:")[1].split("|")[0].strip()
                    for l in lines if "Width-skip:" in l), "?")

if not entry_rows:
    near_rows = [l for l in lines if "NEAR" in l and "|" in l]
    near_str  = ""
    if near_rows:
        near_str = "\nNear: " + ", ".join(
            l.split("|")[0].strip() for l in near_rows[:3]
        )
    send_telegram(
        f"ORB SCAN | {now.strftime('%H:%M')} | {today_str}\n"
        f"No entry signals.{near_str}\n"
        f"Width-skip: {skip_count} tickers"
    )
    sys.exit(0)

# ── Parse top entry signal ───────────────────────────────────────────────────
top_row = entry_rows[0]
cols     = [c.strip() for c in top_row.split("|")]
if len(cols) < 8:
    print("Could not parse entry row — aborting.")
    sys.exit(1)

ticker    = cols[0].strip()
close_px  = float(cols[2].strip())
orh       = float(cols[3].strip())
orl       = float(cols[4].strip())
width_pct = float(cols[5].strip().rstrip("%"))
status    = cols[7].strip()
side      = "LONG" if "LONG" in status else "SHORT"

tgt1 = tgt2 = sl = None
if "[T1:" in top_row:
    try:
        bracket = top_row.split("[T1:")[1].rstrip("]")
        parts   = bracket.split()
        tgt1    = float(parts[0])
        tgt2    = float(parts[1].lstrip("T2:"))
        sl      = float(parts[2].lstrip("SL:"))
    except Exception:
        pass

# ── Security ID check ────────────────────────────────────────────────────────
sec_id = get_security_id(ticker)
if not sec_id:
    send_telegram(
        f"ORB SIGNAL: {ticker} {side} @ Rs{close_px:.2f}\n"
        f"BLOCKED — securityId missing in nse_securities.json.\n"
        f"Add it then re-run, or trade manually."
    )
    sys.exit(0)

# ── VIX gate ─────────────────────────────────────────────────────────────────
vix = 99.0
for ln in run_shell("bash scripts/vix.sh").splitlines():
    if "INDIA_VIX=" in ln:
        try:
            vix = float(ln.split("=")[1].strip())
        except Exception:
            pass
if vix >= 20:
    send_telegram(f"ORB SIGNAL BLOCKED: VIX {vix:.2f} >= 20")
    sys.exit(0)

# ── Open positions gate ──────────────────────────────────────────────────────
open_count = 0
pos_raw    = run_shell("bash scripts/dhan.sh positions")
try:
    pos_data   = json.loads(pos_raw)
    positions  = pos_data.get("data", pos_data) if isinstance(pos_data, dict) else pos_data
    if isinstance(positions, list):
        open_count = sum(
            1 for p in positions
            if isinstance(p, dict)
            and p.get("productType") == "INTRADAY"
            and abs(float(p.get("netQty", 0))) > 0
        )
except Exception:
    pass
if open_count >= 3:
    send_telegram(f"ORB SIGNAL BLOCKED: {open_count}/3 positions open")
    sys.exit(0)

# ── ATR + margin ─────────────────────────────────────────────────────────────
atr = 0.0
try:
    atr = float(run_shell(f"bash scripts/dhan.sh atr {ticker}").strip())
except Exception:
    pass

margin = 20000.0
try:
    funds_data = json.loads(run_shell("bash scripts/dhan.sh funds"))
    d          = funds_data.get("data", funds_data)
    margin     = float(d.get("availabelBalance") or d.get("availableBalance") or 20000)
except Exception:
    pass

# ── Sizing ───────────────────────────────────────────────────────────────────
qty = stop_price = target1 = target2 = r_actual = heat_pct = cost_pct = None
if atr > 0:
    sz_raw = run_shell(
        f"python scripts/size_calc.py --market india --entry {close_px} --atr {atr} "
        f"--capital 20000 --margin {margin} --tier 2 --size-multiplier 1.0"
    )
    try:
        sz        = json.loads(sz_raw)
        qty       = sz.get("qty")
        stop_price= sz.get("stop_price")
        target1   = sz.get("target1")
        target2   = sz.get("target2")
        r_actual  = sz.get("R_actual")
        heat_pct  = sz.get("heat_pct_of_capital")
        cost_pct  = sz.get("cost_pct_of_margin")
    except Exception:
        pass

# Fallback sizing from scan targets
if not qty:
    stop_price = sl or (orl if side == "LONG" else orh)
    stop_dist  = abs(close_px - stop_price)
    qty        = max(1, int(200 / stop_dist)) if stop_dist > 0 else 1
    target1    = tgt1 or (close_px + stop_dist * 1.5)
    target2    = tgt2 or (close_px + stop_dist * 2.5)
    r_actual   = round(stop_dist * qty, 2)
    heat_pct   = round(r_actual / 20000 * 100, 2)
    cost_pct   = round(close_px * qty / margin * 100, 2) if margin > 0 else 0

# ── Write PENDING-TRADE.json ─────────────────────────────────────────────────
expires_ist = now.replace(hour=15, minute=10, second=0, microsecond=0)
pending = {
    "sym":          ticker,
    "side":         side,
    "sec_id":       sec_id,
    "entry":        round(close_px, 2),
    "stop":         round(stop_price, 2),
    "target1":      round(target1, 2),
    "target2":      round(target2, 2),
    "qty":          qty,
    "atr":          round(atr, 2),
    "vix":          vix,
    "orb_width_pct":width_pct,
    "proposed_at":  now.isoformat(),
    "expires_at":   expires_ist.isoformat(),
}
PENDING_FILE.write_text(json.dumps(pending, indent=2), encoding="utf-8")
print(f"PENDING-TRADE written: {pending}")

# ── Send Telegram proposal ───────────────────────────────────────────────────
stop_pct = abs(close_px - stop_price) / close_px * 100
msg = (
    f"India ORB SIGNAL | {now.strftime('%H:%M')} | {today_str}\n\n"
    f"*{ticker} {side}*\n"
    f"Entry: Rs{close_px:.2f}   SL: Rs{stop_price:.2f} ({stop_pct:.1f}%)\n"
    f"T1: Rs{target1:.2f}   T2: Rs{target2:.2f}\n"
    f"Qty: {qty}   R: Rs{r_actual}   Heat: {heat_pct}%\n"
    f"ORB width: {width_pct:.1f}%   VIX: {vix:.1f}\n\n"
    f"Reply *Y* to place order   *N* to skip\n"
    f"(expires 15:10 IST)"
)
msg_id = send_telegram(msg)
if msg_id:
    pending["proposal_msg_id"] = msg_id
    PENDING_FILE.write_text(json.dumps(pending, indent=2), encoding="utf-8")

# Send remaining signals as info
if len(entry_rows) > 1:
    others = ", ".join(
        r.split("|")[0].strip() for r in entry_rows[1:4]
    )
    send_telegram(f"Other ORB signals (not proposed): {others}")
