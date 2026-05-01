import argparse
import getpass
import json
import os
import signal
import sys
import time
from datetime import datetime
from threading import Lock
from typing import Any

import pyotp
from dotenv import load_dotenv
from neo_api_client import NeoAPI


DEFAULT_INSTRUMENTS = [
    {"symbol": "RELIANCE", "instrument_token": "2885", "exchange_segment": "nse_cm"},
    {"symbol": "TCS", "instrument_token": "11536", "exchange_segment": "nse_cm"},
    {"symbol": "INFY", "instrument_token": "1594", "exchange_segment": "nse_cm"},
]

LTP_KEYS = (
    "ltp",
    "last_traded_price",
    "lastPrice",
    "last_price",
    "lastTradedPrice",
    "ltpValue",
    "ltpVal",
)
TOKEN_KEYS = ("tk", "token", "instrument_token", "exchange_token", "eToken")
EXCHANGE_KEYS = ("e", "exchange", "exchange_segment", "exch", "exchangeSegment")


def env(name: str, fallback: str = "") -> str:
    return os.getenv(name, fallback).strip()


def current_totp() -> str:
    if env("KOTAK_TOTP"):
        return env("KOTAK_TOTP")
    if env("KOTAK_TOTP_SECRET"):
        return pyotp.TOTP(env("KOTAK_TOTP_SECRET")).now()
    return getpass.getpass("Enter current Kotak Neo TOTP: ").strip()


def load_instruments() -> list[dict[str, str]]:
    raw = env("KOTAK_INSTRUMENTS")
    if not raw:
        return DEFAULT_INSTRUMENTS

    data = json.loads(raw)
    if not isinstance(data, list) or not data:
        raise ValueError("KOTAK_INSTRUMENTS must be a non-empty JSON list")

    instruments = []
    for item in data:
        instruments.append(
            {
                "symbol": str(item.get("symbol") or item["instrument_token"]),
                "instrument_token": str(item["instrument_token"]),
                "exchange_segment": str(item["exchange_segment"]),
            }
        )
    return instruments


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key.lower() in {"token", "sid", "rid", "auth", "authorization"}:
                out[key] = "***"
            else:
                out[key] = scrub(item)
        return out
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def print_response(label: str, response: Any, verbose: bool) -> None:
    if verbose:
        print(f"{label}: {json.dumps(scrub(response), ensure_ascii=False)}", flush=True)
    if isinstance(response, dict) and ("error" in response or "Error" in response):
        raise RuntimeError(f"{label} failed: {json.dumps(scrub(response), ensure_ascii=False)}")


def login(verbose: bool) -> NeoAPI:
    consumer_key = env("KOTAK_CONSUMER_KEY")
    mobile = env("KOTAK_MOBILE_NUMBER") or env("KOTAK_MOBILE")
    ucc = env("KOTAK_UCC")
    mpin = env("KOTAK_MPIN")

    missing = [
        name
        for name, value in {
            "KOTAK_CONSUMER_KEY": consumer_key,
            "KOTAK_MOBILE_NUMBER/KOTAK_MOBILE": mobile,
            "KOTAK_UCC": ucc,
            "KOTAK_MPIN": mpin,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required variables: {', '.join(missing)}")

    client = NeoAPI(
        environment=env("KOTAK_ENV", "prod"),
        access_token=None,
        neo_fin_key=env("KOTAK_NEO_FIN_KEY") or None,
        consumer_key=consumer_key,
    )
    print_response("totp_login", client.totp_login(mobile_number=mobile, ucc=ucc, totp=current_totp()), verbose)
    print_response("totp_validate", client.totp_validate(mpin=mpin), verbose)
    return client


def first_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def find_ltp(value: Any) -> Any:
    if isinstance(value, dict):
        for key in LTP_KEYS:
            if value.get(key) not in (None, ""):
                return value[key]
        for item in value.values():
            ltp = find_ltp(item)
            if ltp not in (None, ""):
                return ltp
    elif isinstance(value, list):
        for item in value:
            ltp = find_ltp(item)
            if ltp not in (None, ""):
                return ltp
    return None


def flatten_ticks(message: Any) -> list[dict[str, Any]]:
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            return [{"raw": message}]

    if isinstance(message, list):
        rows = []
        for item in message:
            rows.extend(flatten_ticks(item))
        return rows

    if isinstance(message, dict):
        for key in ("data", "d", "feeds", "ticks", "result"):
            if isinstance(message.get(key), list):
                return flatten_ticks(message[key])
        return [message]

    return [{"raw": str(message)}]


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Stream realtime LTP from Kotak Neo WebSocket.")
    parser.add_argument("--seconds", type=int, default=0, help="Stop after N seconds. Default: run forever.")
    parser.add_argument(
        "--repeat-last",
        type=int,
        default=0,
        help="Print the latest cached LTP every N seconds, even if no new tick arrives.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print sanitized login responses and raw non-LTP ticks.")
    args = parser.parse_args()

    instruments = load_instruments()
    subscribe_tokens = [
        {"instrument_token": item["instrument_token"], "exchange_segment": item["exchange_segment"]}
        for item in instruments
    ]
    symbol_by_token = {
        str(item["instrument_token"]): item["symbol"]
        for item in instruments
    }
    latest_ltp = {}
    latest_lock = Lock()

    client = login(verbose=args.verbose)
    stop = False

    def request_stop(_signum, _frame):
        nonlocal stop
        stop = True

    def on_message(message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for tick in flatten_ticks(message):
            token = first_value(tick, TOKEN_KEYS) if isinstance(tick, dict) else None
            exchange = first_value(tick, EXCHANGE_KEYS) if isinstance(tick, dict) else None
            ltp = find_ltp(tick)
            symbol = symbol_by_token.get(str(token), str(token or "UNKNOWN"))

            if ltp not in (None, ""):
                with latest_lock:
                    latest_ltp[str(token)] = {
                        "symbol": symbol,
                        "exchange": exchange,
                        "ltp": ltp,
                        "time": timestamp,
                    }
                exchange_part = f"{exchange}|" if exchange else ""
                print(f"{timestamp} {symbol} ({exchange_part}{token}): {ltp}", flush=True)
            elif args.verbose:
                print(f"{timestamp} RAW {json.dumps(tick, ensure_ascii=False)}", flush=True)

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    client.on_message = on_message
    client.on_error = lambda *args: print(f"WebSocket error: {args}", file=sys.stderr, flush=True)
    client.on_close = lambda *args: print(f"WebSocket closed: {args}", flush=True)
    client.on_open = lambda *args: print(f"WebSocket opened: {args}", flush=True)

    print("Subscribing:", flush=True)
    for item in instruments:
        print(f"  {item['symbol']} -> {item['exchange_segment']}|{item['instrument_token']}", flush=True)

    subscribed = False
    try:
        client.subscribe(instrument_tokens=subscribe_tokens, isIndex=False, isDepth=False)
        subscribed = True
        started = time.monotonic()
        last_repeat = started
        while not stop:
            now = time.monotonic()
            if args.repeat_last and now - last_repeat >= args.repeat_last:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with latest_lock:
                    rows = list(latest_ltp.values())
                if rows:
                    for row in rows:
                        exchange_part = f"{row['exchange']}|" if row["exchange"] else ""
                        print(
                            f"{timestamp} LAST {row['symbol']} ({exchange_part}): {row['ltp']}",
                            flush=True,
                        )
                else:
                    print(f"{timestamp} Waiting for first tick...", flush=True)
                last_repeat = now
            if args.seconds and time.monotonic() - started >= args.seconds:
                break
            time.sleep(1)
    finally:
        if subscribed:
            try:
                client.un_subscribe(instrument_tokens=subscribe_tokens, isIndex=False, isDepth=False)
            except Exception as exc:
                print(f"Unsubscribe failed: {exc}", file=sys.stderr, flush=True)
        if getattr(client, "NeoWebSocket", None) and getattr(client.NeoWebSocket, "hsWebsocket", None):
            try:
                client.NeoWebSocket.hsWebsocket.close()
            except Exception as exc:
                print(f"WebSocket close failed: {exc}", file=sys.stderr, flush=True)
        client.logout()

    if args.seconds:
        os._exit(0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
