"""
Scheduled pre-market task — called by Windows Task Scheduler at 08:45 IST Mon-Fri.
Runs premarket_watchlist.py and sends Telegram summary.
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
    print("KILL_SWITCH present — pre-market skipped.")
    sys.exit(0)

# Run premarket watchlist and capture output
import scripts.premarket_watchlist as pm
buf = io.StringIO()
try:
    with redirect_stdout(buf):
        pm.main()
    exit_code = 0
except SystemExit as e:
    exit_code = e.code or 0
output = buf.getvalue()
print(output)

if exit_code != 0:
    # Blocked by VIX or kill switch — already printed reason
    sys.exit(exit_code)

# Parse summary lines for Telegram
lines = output.strip().split("\n")
vix_line     = next((l for l in lines if "VIX:" in l and "CLEAR" in l), "VIX: unknown")
top3_line    = next((l for l in lines if "Top 3 priority:" in l), "")
likely_line  = next((l for l in lines if "Likely to pass" in l), "")
approved_line= next((l for l in lines if "tickers approved" in l), "")

now_ist  = datetime.now(IST)
date_str = now_ist.strftime("%Y-%m-%d")
time_str = now_ist.strftime("%H:%M")

msg = f"India PRE-MARKET | {date_str} | {time_str} IST\n\n"
msg += f"{vix_line.strip()}\n"
if approved_line:
    msg += f"{approved_line.strip()}\n"
if likely_line:
    msg += f"{likely_line.strip()}\n"
if top3_line:
    msg += f"{top3_line.strip()}\n"
msg += "\nStrategy: ORB v3 | width gate >=1.5%\nORB scan fires at 09:30 IST"

# Send to Telegram
def send_telegram(text):
    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        fallback = ROOT / "notify_fallback.log"
        with open(fallback, "a", encoding="utf-8") as f:
            f.write(f"\n[PREMARKET TASK {datetime.now(IST)}]\n{text}\n")
        print("No Telegram creds — written to notify_fallback.log")
        return
    data = json.dumps({
        "chat_id": chat_id,
        "text": text,
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
