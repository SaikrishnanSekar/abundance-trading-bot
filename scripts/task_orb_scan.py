"""
Scheduled ORB scan task — called by Windows Task Scheduler at 09:30 IST Mon-Fri.
Runs the live ORB scan, formats results, sends to Telegram.
"""
import sys, os, io, json, urllib.request
from pathlib import Path
from contextlib import redirect_stdout
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Load .env
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

IST = timezone(timedelta(hours=5, minutes=30))

# Check kill switch
if (ROOT / "memory" / "KILL_SWITCH.md").exists():
    print("KILL_SWITCH present — ORB scan aborted.")
    sys.exit(0)

# Run scan and capture output
import scan_orb_live
buf = io.StringIO()
with redirect_stdout(buf):
    scan_orb_live.scan()
output = buf.getvalue()
print(output)  # also write to log file

# Parse results
lines = output.strip().split("\n")
entry_lines = [l for l in lines if ">>> ENTRY" in l]
near_lines  = [l for l in lines if "NEAR" in l and ">>>" not in l and "|" in l]
summary     = next((l for l in lines if "Active entries:" in l), "")

now_ist  = datetime.now(IST)
time_str = now_ist.strftime("%H:%M")
date_str = now_ist.strftime("%Y-%m-%d")

msg_parts = [f"ORB SCAN | {time_str} | {date_str}"]

if entry_lines:
    msg_parts.append("")
    msg_parts.append("*ENTRY SIGNALS:*")
    for l in entry_lines:
        cols = [c.strip() for c in l.split("|")]
        if len(cols) >= 8:
            ticker = cols[0]
            price  = cols[2]
            status = cols[7].split("[")[0].strip()[:50]
            tgt_sl = ""
            if "[" in cols[7]:
                tgt_sl = " " + cols[7].split("[")[1].rstrip("]")
            msg_parts.append(f"  {ticker} @ {price} — {status}{tgt_sl}")
else:
    msg_parts.append("ENTRIES: 0")

if near_lines:
    msg_parts.append("")
    msg_parts.append("*NEAR BREAKOUT:*")
    for l in near_lines[:4]:
        cols = [c.strip() for c in l.split("|")]
        if len(cols) >= 8:
            ticker = cols[0]
            price  = cols[2]
            status = cols[7].strip()[:50]
            msg_parts.append(f"  {ticker} @ {price} — {status}")

if summary:
    msg_parts.append("")
    msg_parts.append(summary.strip())

msg = "\n".join(msg_parts)

# Send to Telegram
def send_telegram(text):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        fallback = ROOT / "notify_fallback.log"
        with open(fallback, "a", encoding="utf-8") as f:
            f.write(f"\n[ORB TASK {datetime.now(IST)}]\n{text}\n")
        print("No Telegram creds — written to notify_fallback.log")
        return
    data = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"Telegram sent: {r.status}")
    except Exception as e:
        print(f"Telegram error: {e}")

send_telegram(msg)
