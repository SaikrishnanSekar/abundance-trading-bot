#!/usr/bin/env python3
"""
India Trading Dashboard — local Flask server.

Serves the dashboard at http://localhost:5050
Provides live JSON APIs:
  GET /api/data      — parsed POST-MORTEMS.md + DAILY-SCORE.md + open positions
  GET /api/quote?sym=RELIANCE  — live LTP via Kotak
  GET /api/vix       — live India VIX via Kotak
  GET /api/pulse     — LIVE-PULSE.md content

Run:
  python3 dashboard/server.py
  # or:
  bash scripts/dashboard.sh
"""

import json, os, re, subprocess, sys, time
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

ROOT = Path(__file__).resolve().parent.parent
MEMORY = ROOT / "memory" / "india"
SCRIPTS = ROOT / "scripts"

app = Flask(__name__, static_folder=str(Path(__file__).parent), static_url_path="")
CORS(app)


# ── Parsers ───────────────────────────────────────────────────────────────────

def parse_post_mortems() -> list:
    fpath = MEMORY / "POST-MORTEMS.md"
    if not fpath.exists():
        return []
    text = fpath.read_text(encoding="utf-8", errors="replace")
    trades = []
    # Split on horizontal rules; each block between --- is one trade
    blocks = re.split(r"\n---+\n", text)
    for block in blocks:
        t = {}
        for line in block.splitlines():
            m = re.match(r"^[-*]?\s*(\w[\w_]*)\s*:\s*(.+)", line.strip())
            if m:
                t[m.group(1).strip()] = m.group(2).strip()
        if t.get("outcome_code"):
            trades.append(t)
    # newest-first order → reverse so charts show chronological left-to-right
    trades.reverse()
    return trades


def parse_daily_score() -> list:
    fpath = MEMORY / "DAILY-SCORE.md"
    if not fpath.exists():
        return []
    rows = []
    for line in fpath.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|([^|]+)\|([^|]+)\|([^|]+)\|([^|]+)\|", line)
        if m:
            rows.append({
                "date":   m.group(1),
                "trades": m.group(2).strip(),
                "pnl":    m.group(3).strip(),
                "grade5": m.group(4).strip(),
                "grade20":m.group(5).strip(),
            })
    return rows


def parse_live_pulse() -> dict:
    fpath = MEMORY / "LIVE-PULSE.md"
    if not fpath.exists():
        return {}
    text = fpath.read_text(encoding="utf-8", errors="replace")
    data = {"raw": text, "positions": [], "last_updated": ""}
    # Extract timestamp
    ts = re.search(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2})", text)
    if ts:
        data["last_updated"] = ts.group(1)
    # Extract position blocks
    for block in re.findall(r"#{2,3}\s+(\w[\w\s]+)\n(.*?)(?=\n#{2,3}|\Z)", text, re.S):
        sym = block[0].strip()
        pos = {"symbol": sym}
        for line in block[1].splitlines():
            m = re.match(r"[-*]?\s*([\w_]+)\s*[=:]\s*(.+)", line.strip())
            if m:
                pos[m.group(1).strip()] = m.group(2).strip()
        if pos.get("ltp") or pos.get("entry"):
            data["positions"].append(pos)
    return data


def parse_trade_log() -> list:
    fpath = MEMORY / "TRADE-LOG.md"
    if not fpath.exists():
        return []
    text = fpath.read_text(encoding="utf-8", errors="replace")
    open_trades = []
    # Find rows in tables that look like open positions (no exit_time yet)
    for line in text.splitlines():
        if "|" in line and re.search(r"(OPEN|open|—|-{2,})", line):
            cols = [c.strip() for c in line.split("|") if c.strip()]
            if len(cols) >= 3:
                open_trades.append({"row": cols})
    return open_trades


def run_kotak(args: list, timeout: int = 20) -> str:
    """Call kotak.sh and return stdout."""
    env = os.environ.copy()
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env.setdefault(k.strip(), v.strip())
    try:
        result = subprocess.run(
            ["bash", str(SCRIPTS / "kotak.sh")] + args,
            capture_output=True, text=True, timeout=timeout, env=env,
            cwd=str(ROOT),
        )
        return result.stdout.strip()
    except Exception as e:
        return f"error: {e}"


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(str(Path(__file__).parent), "india.html")


@app.route("/api/data")
def api_data():
    trades = parse_post_mortems()
    score  = parse_daily_score()
    pulse  = parse_live_pulse()
    return jsonify({
        "trades":      trades,
        "daily_score": score,
        "pulse":       pulse,
        "trade_count": len(trades),
        "generated_at": datetime.now().isoformat(),
    })


@app.route("/api/quote")
def api_quote():
    sym = request.args.get("sym", "").upper().strip()
    if not sym:
        return jsonify({"error": "sym parameter required"}), 400
    ltp = run_kotak(["quote", sym])
    if ltp.startswith("error"):
        return jsonify({"symbol": sym, "ltp": None, "error": ltp}), 500
    return jsonify({"symbol": sym, "ltp": ltp, "ts": time.time()})


@app.route("/api/vix")
def api_vix():
    vix = run_kotak(["vix"])
    if vix.startswith("error"):
        return jsonify({"vix": None, "error": vix}), 500
    return jsonify({"vix": vix, "ts": time.time()})


@app.route("/api/pulse")
def api_pulse():
    return jsonify(parse_live_pulse())


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("DASHBOARD_PORT", 5050))
    print(f"\n  India Trading Dashboard")
    print(f"  http://localhost:{port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
