#!/usr/bin/env python3
"""Test Dhan charts/intraday endpoint for 5-min OHLCV."""
import sys, io, os, json
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import requests

# Load .env
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

BASE   = os.environ.get("DHAN_BASE_URL", "https://api.dhan.co")
TOKEN  = os.environ.get("DHAN_ACCESS_TOKEN", "")
CLIENT = os.environ.get("DHAN_CLIENT_ID", "")

if not TOKEN or not CLIENT:
    print("ERROR: DHAN_ACCESS_TOKEN or DHAN_CLIENT_ID not set")
    sys.exit(1)

headers = {
    "access-token": TOKEN,
    "client-id": CLIENT,
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Test with RELIANCE (securityId 2885), 5-min, April 1 – May 2
payload = {
    "securityId": "2885",
    "exchangeSegment": "NSE_EQ",
    "instrument": "EQUITY",
    "interval": "5",
    "fromDate": "2026-04-01",
    "toDate": "2026-05-02",
}

print(f"Testing Dhan /v2/charts/intraday — RELIANCE 5min Apr 1–May 2")
try:
    r = requests.post(f"{BASE}/v2/charts/intraday", headers=headers,
                      json=payload, timeout=30)
    print(f"HTTP {r.status_code}")
    try:
        d = r.json()
    except Exception:
        print("Non-JSON response:", r.text[:400])
        sys.exit(1)

    if isinstance(d, dict):
        print("Keys:", list(d.keys()))
        if "open" in d:
            n = len(d["open"])
            print(f"Candle count: {n}")
            if n > 0:
                print(f"First timestamp: {d.get('timestamp', [None])[0]}")
                print(f"Last  timestamp: {d.get('timestamp', [None])[-1]}")
                print(f"Sample open: {d['open'][:3]}")
                print(f"Sample close: {d['close'][:3]}")
                print(f"Sample volume: {d.get('volume', [])[:3]}")
        elif "errorCode" in d or "message" in d:
            print("API error:", json.dumps(d, indent=2)[:400])
        else:
            print(json.dumps(d, indent=2)[:600])
    else:
        print(type(d), str(d)[:400])
except Exception as e:
    print(f"Request failed: {e}")
