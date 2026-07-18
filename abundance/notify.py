"""Optional Telegram notifier. Reads TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from
the process environment or a repo-root .env (read-only — this module NEVER
writes a .env). Missing creds or network failure → message appended to
abundance/reports/notify_fallback.log; the scan never crashes over Telegram."""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone

from .config import ENV_FILE, REPORT_DIR, TELEGRAM_MAX_LEN


def _env(key: str) -> str | None:
    if os.environ.get(key):
        return os.environ[key]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith(f"{key}=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def send(msg: str) -> bool:
    msg = msg[:TELEGRAM_MAX_LEN]
    token, chat = _env("TELEGRAM_BOT_TOKEN"), _env("TELEGRAM_CHAT_ID")
    if token and chat:
        body = json.dumps({"chat_id": chat, "text": msg,
                           "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=body,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15):
                return True
        except Exception:
            pass  # fall through to local log
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with (REPORT_DIR / "notify_fallback.log").open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n---\n")
    return False
