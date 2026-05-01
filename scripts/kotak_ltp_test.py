#!/usr/bin/env python3
"""Quick smoke-test for Kotak Neo SDK auth + LTP quotes."""

import os, sys
from pathlib import Path
import pyotp
from neo_api_client import NeoAPI

# Load .env
env_file = Path(__file__).resolve().parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            if k.strip() not in os.environ:
                os.environ[k.strip()] = v.strip()

consumer_key = os.environ.get("KOTAK_CONSUMER_KEY", "")
mobile       = os.environ.get("KOTAK_MOBILE", "")
ucc          = os.environ.get("KOTAK_UCC", "")
mpin         = os.environ.get("KOTAK_MPIN", "")
totp_secret  = os.environ.get("KOTAK_TOTP_SECRET", "")

missing = [k for k, v in [("KOTAK_CONSUMER_KEY", consumer_key), ("KOTAK_MOBILE", mobile),
           ("KOTAK_UCC", ucc), ("KOTAK_MPIN", mpin), ("KOTAK_TOTP_SECRET", totp_secret)] if not v]
if missing:
    print(f"ERROR: missing env vars: {missing}", file=sys.stderr)
    sys.exit(1)

print("[1/3] Initialising NeoAPI client...")
client = NeoAPI(
    environment="prod",
    access_token=None,
    neo_fin_key=None,
    consumer_key=consumer_key,
)

totp = pyotp.TOTP(totp_secret).now()
print(f"[2/3] totp_login (TOTP={totp})...")
login_resp = client.totp_login(
    mobile_number=mobile,
    ucc=ucc,
    totp=totp,
)
print("login_resp:", login_resp)

print("[3/3] totp_validate (mpin)...")
validate_resp = client.totp_validate(mpin=mpin)
print("validate_resp:", validate_resp)

print("\n--- LTP quotes ---")
quotes = client.quotes(
    instrument_tokens=[
        {"instrument_token": "2885",  "exchange_segment": "nse_cm"},  # RELIANCE
        {"instrument_token": "11536", "exchange_segment": "nse_cm"},  # TCS
        {"instrument_token": "1594",  "exchange_segment": "nse_cm"},  # INFY
    ],
    quote_type="ltp",
)
print(quotes)

client.logout()
print("\nDone.")
