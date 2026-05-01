import argparse
import getpass
import json
import os
import signal
import sys
import time
from datetime import datetime

import pyotp
from dotenv import load_dotenv
from neo_api_client import NeoAPI


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_instruments(raw_value: str) -> list[dict[str, str]]:
    try:
        instruments = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"KOTAK_INSTRUMENTS must be valid JSON: {exc}") from exc

    if not isinstance(instruments, list) or not instruments:
        raise ValueError("KOTAK_INSTRUMENTS must be a non-empty JSON list")

    for item in instruments:
        if not isinstance(item, dict):
            raise ValueError("Each instrument must be a JSON object")
        if not item.get("instrument_token") or not item.get("exchange_segment"):
            raise ValueError("Each instrument needs instrument_token and exchange_segment")

    return instruments


def current_totp() -> str:
    manual_totp = os.getenv("KOTAK_TOTP", "").strip()
    if manual_totp:
        return manual_totp

    totp_secret = os.getenv("KOTAK_TOTP_SECRET", "").strip()
    if totp_secret:
        return pyotp.TOTP(totp_secret).now()

    return getpass.getpass("Enter current Kotak Neo TOTP: ").strip()


def print_tick(message) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(message, (dict, list)):
        payload = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
    else:
        payload = str(message)
    print(f"{timestamp} {payload}", flush=True)


def scrub_secrets(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key.lower() in {"token", "sid", "rid", "authtoken", "accesstoken", "sessiontoken"}:
                redacted[key] = "***"
            else:
                redacted[key] = scrub_secrets(item)
        return redacted
    if isinstance(value, list):
        return [scrub_secrets(item) for item in value]
    return value


def print_response(label: str, response) -> None:
    print(f"{label}: {json.dumps(scrub_secrets(response), ensure_ascii=False)}", flush=True)


def build_client() -> NeoAPI:
    consumer_key = os.getenv("KOTAK_CONSUMER_KEY", "").strip()
    mobile_number = os.getenv("KOTAK_MOBILE_NUMBER", "").strip()
    ucc = os.getenv("KOTAK_UCC", "").strip()
    mpin = os.getenv("KOTAK_MPIN", "").strip()
    environment = os.getenv("KOTAK_ENV", "prod").strip() or "prod"

    missing = [
        name
        for name, value in {
            "KOTAK_CONSUMER_KEY": consumer_key,
            "KOTAK_MOBILE_NUMBER": mobile_number,
            "KOTAK_UCC": ucc,
            "KOTAK_MPIN": mpin,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    client = NeoAPI(
        environment=environment,
        access_token=None,
        neo_fin_key=None,
        consumer_key=consumer_key,
    )

    client.on_message = print_tick
    client.on_error = lambda error: print(f"WebSocket error: {error}", file=sys.stderr, flush=True)
    client.on_close = lambda message: print(f"WebSocket closed: {message}", flush=True)
    client.on_open = lambda message: print(f"WebSocket opened: {message}", flush=True)

    login_response = client.totp_login(mobile_number=mobile_number, ucc=ucc, totp=current_totp())
    print_response("totp_login", login_response)
    validate_response = client.totp_validate(mpin=mpin)
    print_response("totp_validate", validate_response)

    if not getattr(client.configuration, "edit_token", None):
        raise RuntimeError("Login did not complete. Check the sanitized responses above.")

    return client


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Stream realtime Kotak Neo market data.")
    parser.add_argument("--seconds", type=int, default=0, help="Stop after N seconds. Default: run forever.")
    parser.add_argument("--depth", action="store_true", help="Subscribe to market depth.")
    parser.add_argument("--index", action="store_true", help="Subscribe to index feed.")
    args = parser.parse_args()

    instruments = load_instruments(os.getenv("KOTAK_INSTRUMENTS", "[]"))
    is_depth = args.depth or env_bool("KOTAK_IS_DEPTH")
    is_index = args.index or env_bool("KOTAK_IS_INDEX")

    client = build_client()
    stop = False

    def request_stop(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    subscribed = False
    print(f"Subscribing to {instruments}", flush=True)
    client.subscribe(instrument_tokens=instruments, isIndex=is_index, isDepth=is_depth)
    subscribed = True

    started = time.monotonic()
    try:
        while not stop:
            if args.seconds and time.monotonic() - started >= args.seconds:
                break
            time.sleep(1)
    finally:
        if subscribed:
            print("Unsubscribing...", flush=True)
            client.un_subscribe(instrument_tokens=instruments, isIndex=is_index, isDepth=is_depth)
        client.logout()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
