#!/usr/bin/env python3
"""NSE India public API client. No auth needed; uses browser-like session cookies."""
import http.cookiejar
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

NSE_BASE = "https://www.nseindia.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
API_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_BASE + "/",
    "Connection": "keep-alive",
    "X-Requested-With": "XMLHttpRequest",
}


def make_session():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    # Seed cookies via homepage (NSE requires nsit + nseappid cookies for API calls)
    for attempt in range(2):
        try:
            req = urllib.request.Request(
                NSE_BASE + "/",
                headers={
                    "User-Agent": UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            opener.open(req, timeout=10)
            return opener
        except Exception:
            if attempt == 0:
                time.sleep(1)
    return opener  # return even without cookies; fetch() will retry


def fetch(opener, path, retries=3):
    url = NSE_BASE + path
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=API_HEADERS)
            with opener.open(req, timeout=15) as r:
                raw = r.read().decode("utf-8", errors="replace")
                if not raw.strip() or raw.strip().startswith("<"):
                    raise ValueError("non-JSON response (got HTML or empty)")
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            if e.code in (429, 403) and attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
                _reseed(opener)
                continue
            print(f"nse: HTTP {e.code} for {path}: {body}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                _reseed(opener)
                continue
            print(f"nse: failed fetching {path}: {e}", file=sys.stderr)
            sys.exit(1)


def _reseed(opener):
    try:
        req = urllib.request.Request(
            NSE_BASE + "/", headers={"User-Agent": UA, "Accept": "text/html"}
        )
        opener.open(req, timeout=8)
    except Exception:
        pass


def wilder_atr(high, low, close, period=14):
    trs = []
    for i in range(1, len(close)):
        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return None
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return round(atr, 4)


def cmd_vix(opener):
    data = fetch(opener, "/api/allIndices")
    for item in data.get("data", []):
        if item.get("index") == "INDIA VIX":
            print(item["last"])
            return
    print("NA", file=sys.stderr)
    sys.exit(1)


def cmd_quote(opener, symbol):
    data = fetch(opener, f"/api/quote-equity?symbol={symbol.upper()}")
    pi = data.get("priceInfo") or {}
    price = pi.get("lastPrice") or pi.get("close")
    if price is None:
        # fallback: metadata block
        meta = data.get("metadata") or {}
        price = meta.get("lastPrice")
    if price is None:
        print("NA", file=sys.stderr)
        sys.exit(1)
    print(price)


def _fetch_history_rows(opener, symbol, trading_days):
    from datetime import date, timedelta

    to_dt = date.today()
    # Over-fetch calendar days to get enough trading days (weekends + holidays ~40%)
    cal_days = int(trading_days * 1.6) + 14
    fr_dt = to_dt - timedelta(days=cal_days)
    fr_str = fr_dt.strftime("%d-%m-%Y")
    to_str = to_dt.strftime("%d-%m-%Y")
    series = urllib.parse.quote('["EQ"]')
    path = (
        f"/api/historical/cm/equity"
        f"?symbol={symbol.upper()}&series={series}&from={fr_str}&to={to_str}"
    )
    data = fetch(opener, path)
    rows = data.get("data") or []
    # NSE returns oldest-first; keep most recent `trading_days` rows
    return rows[-trading_days:]


def cmd_history(opener, symbol, days=25):
    rows = _fetch_history_rows(opener, symbol, days)
    if not rows:
        print("NA", file=sys.stderr)
        sys.exit(1)
    result = {
        "open":  [float(r["CH_OPENING_PRICE"]) for r in rows],
        "high":  [float(r["CH_TRADE_HIGH_PRICE"]) for r in rows],
        "low":   [float(r["CH_TRADE_LOW_PRICE"]) for r in rows],
        "close": [float(r["CH_CLOSING_PRICE"]) for r in rows],
    }
    print(json.dumps(result))


def cmd_atr(opener, symbol, days=20):
    rows = _fetch_history_rows(opener, symbol, days)
    if len(rows) < 15:
        print("NA", file=sys.stderr)
        sys.exit(1)
    h = [float(r["CH_TRADE_HIGH_PRICE"]) for r in rows]
    l = [float(r["CH_TRADE_LOW_PRICE"]) for r in rows]
    c = [float(r["CH_CLOSING_PRICE"]) for r in rows]
    val = wilder_atr(h, l, c)
    if val is None:
        print("NA", file=sys.stderr)
        sys.exit(1)
    print(val)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: _nse_fetch.py {vix|quote SYMBOL|history SYMBOL [DAYS]|atr SYMBOL [DAYS]}",
            file=sys.stderr,
        )
        sys.exit(1)

    opener = make_session()
    subcmd = sys.argv[1]

    if subcmd == "vix":
        cmd_vix(opener)
    elif subcmd == "quote":
        if len(sys.argv) < 3:
            print("_nse_fetch.py: quote requires SYMBOL", file=sys.stderr)
            sys.exit(1)
        cmd_quote(opener, sys.argv[2])
    elif subcmd == "history":
        if len(sys.argv) < 3:
            print("_nse_fetch.py: history requires SYMBOL", file=sys.stderr)
            sys.exit(1)
        cmd_history(opener, sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 25)
    elif subcmd == "atr":
        if len(sys.argv) < 3:
            print("_nse_fetch.py: atr requires SYMBOL", file=sys.stderr)
            sys.exit(1)
        cmd_atr(opener, sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 20)
    else:
        print(f"_nse_fetch.py: unknown subcommand: {subcmd}", file=sys.stderr)
        sys.exit(1)
