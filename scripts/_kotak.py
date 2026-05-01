#!/usr/bin/env python3
"""
Kotak Neo realtime data client.  No pip dependencies — stdlib only.

Auth flow (3 steps):
  1. POST /oauth2/token           consumer_key (Basic auth, no secret)  → session_token
  2. POST /login/v2/validate      mobile + password                     → triggers 2FA
  3. POST /login/otp/validate     mobile + TOTP (RFC 6238)              → {token, sid, ucc}

Session cached in system tmpdir (~6 h). Re-auth transparent on expiry.

Instrument master (symbol → Kotak token) cached in data/kotak_master.json (refreshed daily).

Commands:
  python3 scripts/_kotak.py auth              test full auth, print session info
  python3 scripts/_kotak.py vix               India VIX as float
  python3 scripts/_kotak.py quote SYMBOL      live LTP as float (NSE equity)
  python3 scripts/_kotak.py flush             delete cached session (force re-auth)
"""

import base64, csv, hashlib, hmac, io, json, os, struct, sys, time
import urllib.error, urllib.parse, urllib.request
from pathlib import Path

AUTH_BASE = "https://napi.kotaksecurities.com"
GW_BASE   = "https://gw-napi.kotaksecurities.com"
LAPI_BASE = "https://lapi.kotaksecurities.com"

_HERE         = Path(__file__).resolve().parent
SESSION_CACHE = Path(__file__).resolve().parent.parent / "data" / ".kotak_session.json"
MASTER_CACHE  = Path(__file__).resolve().parent.parent / "data" / "kotak_master.json"

# ── TOTP (RFC 6238, SHA-1, 30 s, 6 digits) ───────────────────────────────────

def _totp(secret: str) -> str:
    s = secret.upper().replace(" ", "").replace("-", "")
    pad = (8 - len(s) % 8) % 8
    if pad:
        s += "=" * pad
    key     = base64.b32decode(s)
    counter = struct.pack(">Q", int(time.time()) // 30)
    h       = hmac.new(key, counter, hashlib.sha1).digest()
    offset  = h[-1] & 0x0F
    code    = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % 1_000_000).zfill(6)


# ── HTTP ─────────────────────────────────────────────────────────────────────

def _req(url, body=None, headers=None, method=None, form=False):
    hdrs = {"Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        if form:
            data = urllib.parse.urlencode(body).encode()
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json"
    if method is None:
        method = "POST" if data is not None else "GET"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            raw = ""
            try:
                raw = e.read().decode("utf-8", errors="replace")[:600]
            except Exception:
                pass
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"HTTP {e.code} {url}\n{raw}") from e
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Request failed {url}: {e}") from e


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
    needed = ["KOTAK_CONSUMER_KEY", "KOTAK_MOBILE", "KOTAK_PASSWORD", "KOTAK_TOTP_SECRET"]
    missing = [k for k in needed if not os.environ.get(k)]
    if missing:
        print(f"kotak: missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(3)
    return {
        "consumer_key": os.environ["KOTAK_CONSUMER_KEY"],
        "mobile":       os.environ["KOTAK_MOBILE"],
        "password":     os.environ["KOTAK_PASSWORD"],
        "totp_secret":  os.environ["KOTAK_TOTP_SECRET"],
    }


# ── Session cache ─────────────────────────────────────────────────────────────

def _load_session() -> dict | None:
    try:
        if SESSION_CACHE.exists():
            s = json.loads(SESSION_CACHE.read_text())
            if s.get("expires_at", 0) > time.time() + 300:
                return s
    except Exception:
        pass
    return None


def _save_session(data: dict, ttl: int = 21600):
    data["expires_at"] = time.time() + ttl
    SESSION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_CACHE.write_text(json.dumps(data))


# ── Authentication ────────────────────────────────────────────────────────────

def _authenticate(creds: dict) -> dict:
    # ── Step 1: OAuth2 session token (consumer_key, no secret) ──
    b64 = base64.b64encode(f"{creds['consumer_key']}:".encode()).decode()
    print("kotak: [1/3] requesting session token...", file=sys.stderr)
    r1 = _req(
        f"{AUTH_BASE}/oauth2/token",
        body={"grant_type": "client_credentials"},
        headers={"Authorization": f"Basic {b64}"},
        form=True,
    )
    sess_token = r1.get("access_token") or r1.get("token")
    if not sess_token:
        raise RuntimeError(f"Step 1 — no access_token. Response: {r1}")
    print("kotak: [1/3] OK", file=sys.stderr)

    # ── Step 2: Login with mobile + password ──
    print("kotak: [2/3] login mobile+password...", file=sys.stderr)
    r2 = _req(
        f"{AUTH_BASE}/login/1.0/login/v2/validate",
        body={"mobileNumber": creds["mobile"], "password": creds["password"]},
        headers={"Authorization": f"Bearer {sess_token}", "sid": sess_token},
    )
    if r2.get("errorCode") or r2.get("error"):
        raise RuntimeError(f"Step 2 login failed: {r2}")
    # Some API versions return final token already at step 2 (TOTP pre-verified)
    d2 = r2.get("data") or {}
    if d2.get("token"):
        print("kotak: [2/3] direct token (TOTP pre-verified)", file=sys.stderr)
        return _extract_session(d2)
    print("kotak: [2/3] OK — proceeding to TOTP", file=sys.stderr)

    # ── Step 3: 2FA with TOTP ──
    otp = _totp(creds["totp_secret"])
    print(f"kotak: [3/3] 2FA TOTP={otp}...", file=sys.stderr)
    r3 = _req(
        f"{AUTH_BASE}/login/1.0/login/otp/validate",
        body={"mobileNumber": creds["mobile"], "otp": otp},
        headers={"Authorization": f"Bearer {sess_token}", "sid": sess_token},
    )
    if r3.get("errorCode") or r3.get("error"):
        raise RuntimeError(f"Step 3 2FA failed: {r3}")
    d3 = r3.get("data") or r3
    if not d3.get("token"):
        raise RuntimeError(f"Step 3 — no token in response: {r3}")
    print(f"kotak: [3/3] OK — ucc={d3.get('ucc','?')}", file=sys.stderr)
    return _extract_session(d3)


def _extract_session(d: dict) -> dict:
    return {
        "token":      d["token"],
        "sid":        d.get("sid", d["token"]),
        "rid":        d.get("rid", ""),
        "ucc":        d.get("ucc", ""),
        "hsServerId": d.get("hsServerId", ""),
    }


def _get_session() -> dict:
    s = _load_session()
    if s:
        return s
    creds = _load_env()
    s = _authenticate(creds)
    _save_session(s)
    return s


# ── Instrument master ─────────────────────────────────────────────────────────

def _auth_headers(sess: dict) -> dict:
    return {
        "Authorization": f"Bearer {sess['token']}",
        "sid":           sess["sid"],
        "Auth":          sess["token"],
        "rid":           sess.get("rid", ""),
        "hs_server_id":  sess.get("hsServerId", ""),
    }


def _build_master(sess: dict) -> dict:
    """
    Download Kotak instrument master and build symbol → {token, segment} map.
    Tries two endpoints in order; caches result for 24 h.
    """
    print("kotak: downloading instrument master...", file=sys.stderr)

    # Endpoint A — JSON instruments list (newer API)
    mapping = {}
    try:
        resp = _req(
            f"{GW_BASE}/market-feeds/1.0/market-feeds/instruments",
            method="GET",
            headers=_auth_headers(sess),
        )
        instruments = resp if isinstance(resp, list) else resp.get("data", [])
        for inst in instruments:
            sym   = (inst.get("pSymbol") or inst.get("symbol") or "").upper().strip()
            token = str(inst.get("pSymbolCode") or inst.get("instrument_token") or "").strip()
            seg   = (inst.get("pExchSeg") or inst.get("exchange_segment") or "").lower()
            srs   = (inst.get("pSeries") or inst.get("series") or "EQ").upper().strip()
            if sym and token and "nse_cm" in seg and srs == "EQ":
                mapping[sym] = {"token": token, "segment": "nse_cm"}
    except Exception as e:
        print(f"kotak: instruments endpoint A failed ({e}), trying CSV master...", file=sys.stderr)

    # Endpoint B — CSV scrip master (fallback)
    if not mapping:
        try:
            req = urllib.request.Request(
                f"{LAPI_BASE}/trade/instruments/master",
                headers={**_auth_headers(sess), "Accept": "text/csv,application/octet-stream,*/*"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8", errors="replace")
            reader = csv.DictReader(io.StringIO(raw))
            for row in reader:
                sym   = (row.get("pSymbol") or row.get("Symbol") or "").upper().strip()
                token = str(row.get("pSymbolCode") or row.get("InstrumentToken") or "").strip()
                seg   = (row.get("pExchSeg") or row.get("ExchangeSegment") or "").lower()
                srs   = (row.get("pSeries") or row.get("Series") or "EQ").upper().strip()
                if sym and token and "nse_cm" in seg and srs == "EQ":
                    mapping[sym] = {"token": token, "segment": "nse_cm"}
        except Exception as e:
            print(f"kotak: CSV master also failed ({e})", file=sys.stderr)

    if not mapping:
        raise RuntimeError("Could not build instrument master from either endpoint")

    MASTER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MASTER_CACHE.write_text(json.dumps(mapping))
    print(f"kotak: master cached — {len(mapping)} NSE_CM EQ instruments.", file=sys.stderr)
    return mapping


def _get_master(sess: dict) -> dict:
    if MASTER_CACHE.exists():
        age = time.time() - MASTER_CACHE.stat().st_mtime
        if age < 86400:  # 24 h
            return json.loads(MASTER_CACHE.read_text())
    return _build_master(sess)


# ── Market data ───────────────────────────────────────────────────────────────

def _quote_call(sess: dict, tokens: list) -> list:
    """POST market-feeds; returns list of quote dicts."""
    resp = _req(
        f"{GW_BASE}/market-feeds/1.0/market-feeds",
        body={"instrument_tokens": tokens, "quote_type": ""},
        headers=_auth_headers(sess),
    )
    data = resp.get("data") or resp
    if isinstance(data, dict):
        data = list(data.values())
    return data if isinstance(data, list) else [data]


def _extract_ltp(items: list) -> str | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("last_price", "ltp", "LastTradePrice", "lastPrice", "close"):
            v = item.get(key)
            if v not in (None, "", 0):
                return str(v)
    return None


def cmd_vix(sess: dict):
    """India VIX — try known Kotak NSE index tokens in order."""
    candidates = [
        ("nse_index", "26017"),  # standard NSE VIX code
        ("nse_index", "13"),
        ("nse_index", "26000"),
        ("bse_index", "999920041"),
    ]
    for seg, tok in candidates:
        try:
            items = _quote_call(sess, [{"exchange_segment": seg, "instrument_token": tok}])
            ltp = _extract_ltp(items)
            if ltp:
                print(ltp)
                return
        except Exception as e:
            print(f"kotak: VIX seg={seg} tok={tok} → {e}", file=sys.stderr)
    print("kotak: India VIX not found via any candidate token", file=sys.stderr)
    sys.exit(1)


def cmd_quote(sess: dict, symbol: str):
    """Live LTP for an NSE equity symbol."""
    master = _get_master(sess)
    sym = symbol.upper().strip()
    entry = master.get(sym)
    if not entry:
        print(f"kotak: {sym} not in instrument master — check symbol spelling", file=sys.stderr)
        sys.exit(1)
    items = _quote_call(sess, [{"exchange_segment": entry["segment"], "instrument_token": entry["token"]}])
    ltp = _extract_ltp(items)
    if ltp:
        print(ltp)
        return
    print(f"kotak: no LTP for {sym} — raw: {items}", file=sys.stderr)
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

    if subcmd == "auth":
        SESSION_CACHE.unlink(missing_ok=True)  # force fresh auth
        sess = _get_session()
        print(f"kotak: auth OK — ucc={sess.get('ucc')} sid={str(sess.get('sid',''))[:12]}...")
        sys.exit(0)

    sess = _get_session()

    if subcmd == "vix":
        cmd_vix(sess)
    elif subcmd == "quote":
        if len(sys.argv) < 3:
            print("_kotak.py: quote requires SYMBOL", file=sys.stderr)
            sys.exit(1)
        cmd_quote(sess, sys.argv[2])
    else:
        print(f"_kotak.py: unknown subcommand: {subcmd}", file=sys.stderr)
        sys.exit(1)
