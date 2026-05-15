"""
Telegram reply poller — runs every 2 min via Task Scheduler (09:30-15:15 IST).
Checks for Y/N reply to the ORB proposal. Y → places Dhan order + SL order.
"""
import sys, os, json, subprocess, urllib.request
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).parent.parent
os.chdir(ROOT)

env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

IST         = timezone(timedelta(hours=5, minutes=30))
TOKEN       = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID     = os.environ.get("TELEGRAM_CHAT_ID", "")
OFFSET_FILE = ROOT / "memory" / "india" / "telegram_poll_offset.txt"
PENDING_FILE= ROOT / "memory" / "india" / "PENDING-TRADE.json"


def send_telegram(text):
    if not TOKEN or not CHAT_ID:
        return
    data = json.dumps({
        "chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data=data, headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        print(f"Telegram error: {e}")


def get_updates(offset=0):
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates?offset={offset}&timeout=3&limit=20"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read()).get("result", [])
    except Exception as e:
        print(f"getUpdates error: {e}")
        return []


def run_shell(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           cwd=str(ROOT), timeout=20)
        return r.stdout.strip()
    except Exception:
        return ""


def place_order(pending):
    sym    = pending["sym"]
    side   = pending["side"]
    sec_id = pending["sec_id"]
    entry  = pending["entry"]
    stop   = pending["stop"]
    t1     = pending["target1"]
    t2     = pending["target2"]
    qty    = pending["qty"]

    trans   = "BUY" if side == "LONG" else "SELL"
    sl_trans= "SELL" if side == "LONG" else "BUY"

    order = {
        "transactionType":  trans,
        "exchangeSegment":  "NSE_EQ",
        "productType":      "INTRADAY",
        "orderType":        "LIMIT",
        "validity":         "DAY",
        "tradingSymbol":    sym,
        "securityId":       sec_id,
        "quantity":         qty,
        "price":            entry,
    }
    result_raw = run_shell(f"bash scripts/dhan.sh order '{json.dumps(order)}'")
    print(f"Entry order result: {result_raw}")

    try:
        res      = json.loads(result_raw)
        order_id = res.get("orderId") or (res.get("data") or {}).get("orderId", "?")
    except Exception:
        order_id = "parse-error"

    send_telegram(
        f"ORDER PLACED | {sym} {side}\n"
        f"Entry: Rs{entry}   Qty: {qty}   OrderID: {order_id}\n"
        f"SL: Rs{stop}   T1: Rs{t1}   T2: Rs{t2}\n"
        f"Placing SL order now..."
    )

    # SL order
    sl_price   = round(stop * (0.998 if sl_trans == "SELL" else 1.002), 2)
    sl_order   = {
        "transactionType":  sl_trans,
        "exchangeSegment":  "NSE_EQ",
        "productType":      "INTRADAY",
        "orderType":        "STOP_LOSS",
        "validity":         "DAY",
        "tradingSymbol":    sym,
        "securityId":       sec_id,
        "quantity":         qty,
        "price":            sl_price,
        "triggerPrice":     stop,
    }
    sl_raw = run_shell(f"bash scripts/dhan.sh order '{json.dumps(sl_order)}'")
    print(f"SL order result: {sl_raw}")

    try:
        sl_res  = json.loads(sl_raw)
        sl_id   = sl_res.get("orderId") or (sl_res.get("data") or {}).get("orderId", "?")
        send_telegram(f"SL ORDER PLACED | {sym} SL Rs{stop}   OrderID: {sl_id}")
    except Exception:
        send_telegram(f"SL order raw response: {sl_raw[:200]}")

    # Append to TRADE-LOG
    trade_log = ROOT / "memory" / "india" / "TRADE-LOG.md"
    now_ist   = datetime.now(IST)
    log_entry = (
        f"\n| {now_ist.strftime('%Y-%m-%d %H:%M')} | {sym} | {side} | "
        f"Rs{entry} | Rs{stop} | Rs{t1} | Rs{t2} | {qty} | OPEN | ORB v3 |"
    )
    with trade_log.open("a", encoding="utf-8") as f:
        f.write(log_entry)
    print(f"TRADE-LOG updated: {log_entry.strip()}")


# ── Guards ────────────────────────────────────────────────────────────────────
if not TOKEN or not CHAT_ID:
    print("No Telegram creds — poll skipped.")
    sys.exit(0)

# ── Load offset ───────────────────────────────────────────────────────────────
offset = 0
if OFFSET_FILE.exists():
    try:
        offset = int(OFFSET_FILE.read_text().strip())
    except Exception:
        pass

# ── Fetch updates ─────────────────────────────────────────────────────────────
updates = get_updates(offset)
if not updates:
    print("No new Telegram updates.")
    sys.exit(0)

new_offset = max(u["update_id"] for u in updates) + 1
OFFSET_FILE.write_text(str(new_offset))

# ── Load + expiry-check pending trade ─────────────────────────────────────────
pending = None
if PENDING_FILE.exists():
    try:
        pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
        expires = datetime.fromisoformat(pending["expires_at"])
        if datetime.now(IST) > expires:
            print(f"Pending trade for {pending.get('sym')} expired — clearing.")
            PENDING_FILE.unlink(missing_ok=True)
            pending = None
    except Exception:
        pass

# ── Process messages ───────────────────────────────────────────────────────────
for update in updates:
    msg  = update.get("message") or update.get("channel_post") or {}
    if not msg:
        continue
    chat = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "").strip().upper()

    if chat != str(CHAT_ID):
        continue

    print(f"Telegram message from {chat}: '{text}'")

    if text in ("Y", "YES") and pending:
        sym = pending["sym"]
        print(f"Y received — placing {pending['side']} order for {sym}")
        place_order(pending)
        PENDING_FILE.unlink(missing_ok=True)
        print("PENDING-TRADE.json cleared.")

    elif text in ("N", "NO", "SKIP") and pending:
        sym = pending.get("sym", "?")
        print(f"N received — skipping {sym}")
        send_telegram(f"Trade SKIPPED: {sym}")
        PENDING_FILE.unlink(missing_ok=True)
        print("PENDING-TRADE.json cleared.")

    elif text in ("Y", "YES") and not pending:
        print("Y received but no pending trade.")
        send_telegram("No pending trade to confirm.")
