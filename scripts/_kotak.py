#!/usr/bin/env python3
"""
Kotak Neo realtime data client (DATA ONLY — orders stay on Dhan).

Uses the official neo-api-client v2 SDK (Kotak-Neo/Kotak-neo-api-v2 on GitHub).
Auth: consumer_key + mobile + UCC + TOTP + MPIN (no consumer_secret needed).
Session cached in data/.kotak_session.json (~6 h). Re-auth is transparent.
Instrument master (symbol→token) cached in data/kotak_master.json (refreshed daily).

Commands:
  python3 scripts/_kotak.py auth              full auth test, print session info
  python3 scripts/_kotak.py vix               India VIX as float
  python3 scripts/_kotak.py quote SYMBOL      live LTP as float (NSE equity)
  python3 scripts/_kotak.py flush             delete cached session + master

Reads from env / .env:
  KOTAK_CONSUMER_KEY, KOTAK_MOBILE, KOTAK_UCC, KOTAK_MPIN, KOTAK_TOTP_SECRET
"""

import csv, io, json, os, sys, time
from pathlib import Path

import pyotp
import requests as _req_lib
from neo_api_client import NeoAPI

_HERE         = Path(__file__).resolve().parent
SESSION_CACHE = _HERE.parent / "data" / ".kotak_session.json"
MASTER_CACHE  = _HERE.parent / "data" / "kotak_master.json"

# NSE VIX token candidates (nse_cm master CSV row with pTrdSymbol=INDIA VIX)
_VIX_TOKENS = [
    {"instrument_token": "26017", "exchange_segment": "nse_cm"},
    {"instrument_token": "13",    "exchange_segment": "nse_cm"},
    {"instrument_token": "26000", "exchange_segment": "nse_cm"},
]

_SCRIP_MASTER_URL = "https://mis.kotaksecurities.com/script-details/1.0/masterscrip/file-paths"


# ── Credentials ───────────────────────────────────────────────────────────────

def _load_env() -> dict:
    env_file = _HERE.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                if k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip()
    needed = ["KOTAK_CONSUMER_KEY", "KOTAK_MOBILE", "KOTAK_UCC", "KOTAK_MPIN", "KOTAK_TOTP_SECRET"]
    missing = [k for k in needed if not os.environ.get(k)]
    if missing:
        print(f"kotak: missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(3)
    return {
        "consumer_key": os.environ["KOTAK_CONSUMER_KEY"],
        "mobile":       os.environ["KOTAK_MOBILE"],
        "ucc":          os.environ["KOTAK_UCC"],
        "mpin":         os.environ["KOTAK_MPIN"],
        "totp_secret":  os.environ["KOTAK_TOTP_SECRET"],
    }


# ── Session cache ─────────────────────────────────────────────────────────────

def _load_session_cache() -> dict | None:
    try:
        if SESSION_CACHE.exists():
            s = json.loads(SESSION_CACHE.read_text())
            if s.get("expires_at", 0) > time.time() + 300:
                return s
    except Exception:
        pass
    return None


def _save_session_cache(data: dict, ttl: int = 21600):
    data["expires_at"] = time.time() + ttl
    SESSION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_CACHE.write_text(json.dumps(data))


# ── Auth ──────────────────────────────────────────────────────────────────────

def _wire_client(client: NeoAPI, sess: dict):
    """Set edit_token, edit_sid, base_url on a NeoAPI client object."""
    client.configuration.edit_token = sess["token"]
    client.configuration.edit_sid   = sess.get("sid", "")
    client.configuration.edit_rid   = sess.get("rid", "")
    if sess.get("baseUrl"):
        client.configuration.base_url = sess["baseUrl"]


def _authenticate(creds: dict) -> NeoAPI:
    print("kotak: [1/3] init NeoAPI client...", file=sys.stderr)
    client = NeoAPI(
        environment="prod",
        consumer_key=creds["consumer_key"],
        access_token=None,
        neo_fin_key=None,
    )

    totp = pyotp.TOTP(creds["totp_secret"]).now()
    print(f"kotak: [2/3] totp_login (TOTP={totp})...", file=sys.stderr)
    r2 = client.totp_login(
        mobile_number=creds["mobile"],
        ucc=creds["ucc"],
        totp=totp,
    )
    if not (r2 or {}).get("data", {}).get("token"):
        raise RuntimeError(f"totp_login failed: {r2}")
    print(f"kotak: [2/3] OK — ucc={r2['data'].get('ucc','?')}", file=sys.stderr)

    print("kotak: [3/3] totp_validate (mpin)...", file=sys.stderr)
    r3 = client.totp_validate(mpin=creds["mpin"])
    if not (r3 or {}).get("data", {}).get("token"):
        raise RuntimeError(f"totp_validate failed: {r3}")
    print(f"kotak: [3/3] OK — kType={r3['data'].get('kType','?')}", file=sys.stderr)

    sess = {
        "token":   r3["data"]["token"],
        "sid":     r3["data"].get("sid", ""),
        "rid":     r3["data"].get("rid", ""),
        "ucc":     r3["data"].get("ucc", ""),
        "baseUrl": r3["data"].get("baseUrl", ""),
    }
    _save_session_cache(sess)
    _wire_client(client, sess)
    return client


def _get_client(creds: dict) -> NeoAPI:
    cached = _load_session_cache()
    if cached:
        print("kotak: using cached session", file=sys.stderr)
        client = NeoAPI(
            environment="prod",
            consumer_key=creds["consumer_key"],
            access_token=cached["token"],
        )
        _wire_client(client, cached)
        return client
    return _authenticate(creds)


# ── Instrument master (symbol → token) ───────────────────────────────────────

def _build_master(consumer_key: str) -> dict:
    """Download NSE CM scrip master CSV and build {SYMBOL: token} map."""
    print("kotak: fetching scrip master file-paths...", file=sys.stderr)
    r = _req_lib.get(_SCRIP_MASTER_URL, headers={"Authorization": consumer_key}, timeout=15)
    r.raise_for_status()
    paths = r.json().get("data", {}).get("filesPaths", [])
    nse_cm_url = next((p for p in paths if "nse_cm" in p.lower()), None)
    if not nse_cm_url:
        raise RuntimeError(f"nse_cm CSV not found in file-paths: {paths}")

    print(f"kotak: downloading {nse_cm_url}...", file=sys.stderr)
    csv_r = _req_lib.get(nse_cm_url, timeout=30)
    csv_r.raise_for_status()

    mapping = {}
    reader = csv.DictReader(io.StringIO(csv_r.text))
    for row in reader:
        token = (row.get("pSymbol") or "").strip()
        ref   = (row.get("pScripRefKey") or "").upper().strip()
        trd   = (row.get("pTrdSymbol") or "").upper().strip()
        if not token or not ref:
            continue
        # Index by base symbol (pScripRefKey = "HDFCBANK") and trading symbol (pTrdSymbol = "HDFCBANK-EQ")
        mapping[ref] = token
        if trd and trd != ref:
            mapping[trd] = token

    MASTER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MASTER_CACHE.write_text(json.dumps(mapping))
    print(f"kotak: master cached — {len(mapping)} NSE_CM symbols.", file=sys.stderr)
    return mapping


def _get_master(consumer_key: str) -> dict:
    if MASTER_CACHE.exists():
        age = time.time() - MASTER_CACHE.stat().st_mtime
        if age < 86400:
            return json.loads(MASTER_CACHE.read_text())
    return _build_master(consumer_key)


# ── Market data ───────────────────────────────────────────────────────────────

def _ltp_from_quotes(quotes) -> str | None:
    items = quotes if isinstance(quotes, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        v = item.get("ltp") or item.get("last_price") or item.get("LastTradePrice")
        if v not in (None, "", "0", 0):
            return str(v)
    return None


def cmd_vix(client: NeoAPI):
    for tok in _VIX_TOKENS:
        try:
            q = client.quotes(instrument_tokens=[tok], quote_type="ltp")
            ltp = _ltp_from_quotes(q)
            if ltp:
                print(ltp)
                return
        except Exception as e:
            print(f"kotak: VIX token {tok['instrument_token']} failed: {e}", file=sys.stderr)
    print("kotak: India VIX not found via any candidate token", file=sys.stderr)
    sys.exit(1)


def cmd_quote(client: NeoAPI, creds: dict, symbol: str):
    sym    = symbol.upper().strip()
    master = _get_master(creds["consumer_key"])
    token  = master.get(sym) or master.get(sym + "-EQ")
    if not token:
        print(f"kotak: {sym} not in instrument master — check symbol spelling", file=sys.stderr)
        sys.exit(1)

    q   = client.quotes(
        instrument_tokens=[{"instrument_token": token, "exchange_segment": "nse_cm"}],
        quote_type="ltp",
    )
    ltp = _ltp_from_quotes(q)
    if ltp:
        print(ltp)
        return
    print(f"kotak: no LTP for {sym} (token={token}) — raw: {q}", file=sys.stderr)
    sys.exit(1)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: _kotak.py {auth|vix|quote SYMBOL|flush}", file=sys.stderr)
        sys.exit(1)

    subcmd = sys.argv[1]

    if subcmd == "flush":
        SESSION_CACHE.unlink(missing_ok=True)
        MASTER_CACHE.unlink(missing_ok=True)
        print("kotak: session and master cache flushed.")
        sys.exit(0)

    creds = _load_env()

    if subcmd == "auth":
        SESSION_CACHE.unlink(missing_ok=True)
        client = _authenticate(creds)
        cached = _load_session_cache()
        print(f"kotak: auth OK — ucc={cached.get('ucc')} sid={str(cached.get('sid',''))[:12]}...")
        client.logout()
        sys.exit(0)

    client = _get_client(creds)

    if subcmd == "vix":
        cmd_vix(client)
    elif subcmd == "quote":
        if len(sys.argv) < 3:
            print("_kotak.py: quote requires SYMBOL", file=sys.stderr)
            sys.exit(1)
        cmd_quote(client, creds, sys.argv[2])
    else:
        print(f"_kotak.py: unknown subcommand: {subcmd}", file=sys.stderr)
        sys.exit(1)
