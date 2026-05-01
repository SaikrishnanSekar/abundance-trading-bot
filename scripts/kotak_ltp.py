import argparse
import getpass
import json
import os
import re
from typing import Any

import pyotp
from dotenv import load_dotenv
from neo_api_client import NeoAPI


TOKEN_KEYS = ("pSymbol", "pSymbolToken", "instrument_token", "token", "tk")
NAME_KEYS = ("pSymbolName", "pTrdSymbol", "tradingSymbol", "symbol")
LTP_KEYS = ("ltp", "lastPrice", "last_price", "lastTradedPrice", "ltpValue")


def env(name: str, fallback: str = "") -> str:
    return os.getenv(name, fallback).strip()


def current_totp() -> str:
    if env("KOTAK_TOTP"):
        return env("KOTAK_TOTP")
    if env("KOTAK_TOTP_SECRET"):
        return pyotp.TOTP(env("KOTAK_TOTP_SECRET")).now()
    return getpass.getpass("Enter current Kotak Neo TOTP: ").strip()


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


def require_success(label: str, response: Any) -> None:
    print(f"{label}: {json.dumps(scrub(response), ensure_ascii=False)}", flush=True)
    if isinstance(response, dict) and ("error" in response or "Error" in response):
        raise RuntimeError(f"{label} failed")


def login() -> NeoAPI:
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
    require_success("totp_login", client.totp_login(mobile_number=mobile, ucc=ucc, totp=current_totp()))
    require_success("totp_validate", client.totp_validate(mpin=mpin))
    return client


def first_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def resolve_symbol(client: NeoAPI, symbol: str, exchange_segment: str) -> dict[str, str]:
    result = client.search_scrip(exchange_segment=exchange_segment, symbol=symbol)
    if isinstance(result, dict):
        raise RuntimeError(f"search_scrip failed for {symbol}: {json.dumps(scrub(result), ensure_ascii=False)}")
    if not isinstance(result, list) or not result:
        raise RuntimeError(f"No Kotak scrip found for {symbol} on {exchange_segment}")

    exact = []
    wanted = re.sub(r"[^a-z0-9]", "", symbol.lower())
    for row in result:
        names = [
            str(row.get("pTrdSymbol", "")),
            str(row.get("pSymbolName", "")),
            str(row.get("pDesc", "")),
            str(row.get("pSymbol", "")),
        ]
        normalized = [re.sub(r"[^a-z0-9]", "", name.lower()) for name in names]
        eq_symbol = f"{wanted}eq"
        if wanted in normalized or eq_symbol in normalized:
            exact.append(row)

    row = exact[0] if exact else result[0]
    token = first_value(row, TOKEN_KEYS)
    if not token:
        raise RuntimeError(f"Kotak search result for {symbol} did not include an instrument token: {row}")

    name = first_value(row, NAME_KEYS) or symbol
    return {
        "symbol": str(name),
        "instrument_token": str(token),
        "exchange_segment": exchange_segment,
    }


def quote_key(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None
    exchange = row.get("exchange") or row.get("exchange_segment")
    token = row.get("exchange_token") or row.get("instrument_token") or row.get("token")
    if exchange and token:
        return f"{exchange}|{token}"
    return None


def extract_ltp(row: Any) -> Any:
    if isinstance(row, dict):
        for key in LTP_KEYS:
            if key in row:
                return row[key]
        for item in row.values():
            ltp = extract_ltp(item)
            if ltp is not None:
                return ltp
    if isinstance(row, list):
        for item in row:
            ltp = extract_ltp(item)
            if ltp is not None:
                return ltp
    return None


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Get LTP for symbols using Kotak Neo APIs only.")
    parser.add_argument("symbols", nargs="*", default=["RELIANCE", "TCS", "INFY"])
    parser.add_argument("--exchange-segment", default=env("KOTAK_EXCHANGE_SEGMENT", "nse_cm"))
    parser.add_argument("--tokens-json", default=env("KOTAK_INSTRUMENTS", ""))
    args = parser.parse_args()

    client = login()

    if args.tokens_json:
        instruments = json.loads(args.tokens_json)
        resolved = [
            {
                "symbol": item.get("symbol") or item.get("instrument_token"),
                "instrument_token": item["instrument_token"],
                "exchange_segment": item["exchange_segment"],
            }
            for item in instruments
        ]
    else:
        resolved = [resolve_symbol(client, symbol, args.exchange_segment) for symbol in args.symbols]

    quote_tokens = [
        {"instrument_token": item["instrument_token"], "exchange_segment": item["exchange_segment"]}
        for item in resolved
    ]
    print("\nResolved")
    for item in resolved:
        print(f"{item['symbol']} -> {item['exchange_segment']}|{item['instrument_token']}")

    quotes = client.quotes(instrument_tokens=quote_tokens, quote_type="ltp")
    print(f"quotes_raw: {json.dumps(scrub(quotes), ensure_ascii=False)}", flush=True)

    quote_rows = quotes.get("data", quotes) if isinstance(quotes, dict) else quotes
    if isinstance(quote_rows, dict):
        quote_rows = quote_rows.get("list", quote_rows.get("quotes", quote_rows.get("data", quote_rows)))
    if not isinstance(quote_rows, list):
        quote_rows = [quote_rows]

    by_key = {quote_key(row): row for row in quote_rows if quote_key(row)}

    print("\nLTP")
    for item in resolved:
        key = f"{item['exchange_segment']}|{item['instrument_token']}"
        quote = by_key.get(key)
        print(f"{item['symbol']} ({key}): {extract_ltp(quote) if quote else 'NO_QUOTE_RETURNED'}")

    client.logout()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
