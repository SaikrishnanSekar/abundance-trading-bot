"""
NSE Bhavcopy downloader — fetches daily EOD OHLCV for all universe stocks.

Downloads one ZIP per trading day from NSE archives, extracts OHLCV for every
ticker in our universe (N50 + NXT50 + MID50), and merges into per-ticker JSON
files under data/bhav_cache/.

Run:
  python scripts/fetch_nse_bhav.py              # last 180 trading days, all groups
  python scripts/fetch_nse_bhav.py --days 60    # last 60 trading days
  python scripts/fetch_nse_bhav.py --groups N50 NXT50

Output files: data/bhav_cache/TICKER_daily.json
Format: [{dt: "YYYY-MM-DD", open: X, high: X, low: X, close: X, volume: X}, ...]

NSE archives URL (free, no auth):
  https://archives.nseindia.com/content/historical/EQUITIES/YYYY/MON/cmDDMONYYYYbhav.csv.zip
"""
import sys, os, io, json, csv, time, urllib.request, urllib.error, argparse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT     = Path(__file__).parent.parent
BHAV_DIR = ROOT / "data" / "bhav_cache"
IST      = timezone(timedelta(hours=5, minutes=30))

BHAV_DIR.mkdir(parents=True, exist_ok=True)

UNIVERSE_N50 = [
    "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO",
    "BAJAJFINSV", "BAJFINANCE", "BHARTIARTL", "BEL", "BPCL",
    "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "INDUSINDBK",
    "INFY", "ITC", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SHRIRAMFIN",
    "SUNPHARMA", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TCS",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
]

UNIVERSE_NXT50 = [
    "ADANIENT",   "ADANIGREEN",  "AMBUJACEM",  "BAJAJHLDNG", "BANKBARODA",
    "BERGEPAINT", "BOSCHLTD",    "CANBK",      "CHOLAFIN",   "COLPAL",
    "CONCOR",     "DABUR",       "DLF",        "DMART",      "GAIL",
    "GODREJCP",   "HAVELLS",     "INDHOTEL",   "INDUSTOWER", "IOC",
    "IRCTC",      "IRFC",        "LICI",       "LODHA",      "LUPIN",
    "MARICO",     "MUTHOOTFIN",  "NAUKRI",     "NYKAA",      "OFSS",
    "PERSISTENT", "PIDILITIND",  "PNB",        "RECLTD",     "SAIL",
    "SRF",        "TATAPOWER",   "TIINDIA",    "TORNTPHARM", "TORNTPOWER",
    "TVSMOTOR",   "UNIONBANK",   "UPL",        "VEDL",       "VOLTAS",
    "ETERNAL",    "JSWENERGY",   "ZYDUSLIFE",  "PPLPHARMA",  "PAYTM",
]

UNIVERSE_MID50 = [
    "ABCAPITAL",  "APLAPOLLO",   "ASTRAL",     "AUROPHARMA", "BALKRISIND",
    "BANKINDIA",  "BATAINDIA",   "BHARATFORG", "BIOCON",     "COFORGE",
    "CROMPTON",   "DELHIVERY",   "FEDERALBNK", "GMRAIRPORT", "GODREJPROP",
    "IDFCFIRSTB", "INDIAMART",   "JKCEMENT",   "JUBLFOOD",   "KALYANKJIL",
    "KPITTECH",   "LTTS",        "MANAPPURAM", "MAXHEALTH",  "MPHASIS",
    "NHPC",       "OBEROIRLTY",  "PAGEIND",    "PIIND",      "POLICYBZR",
    "POLYCAB",    "RBLBANK",     "SJVN",       "SUNDRMFAST", "SUPREMEIND",
    "TATACHEM",   "TATACOMM",    "VGUARD",     "ABFRL",      "CESC",
    "DIXON",      "HUDCO",       "INDIANB",    "IREDA",      "JBCHEPHARM",
    "KAYNES",     "MOTILALOFS",  "NUVAMA",     "PRESTIGE",   "SOLARINDS",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    # No Accept-Encoding — urllib cannot auto-decompress gzip; keep it plain text
    "Referer":         "https://www.nseindia.com/",
    "Connection":      "keep-alive",
}


def _trading_dates(n_days: int) -> list[date]:
    """Return last n_days calendar dates that are Mon-Fri, sorted oldest-first."""
    today = datetime.now(IST).date()
    result = []
    d = today - timedelta(days=1)   # start from yesterday
    while len(result) < n_days:
        if d.weekday() < 5:         # Mon=0 … Fri=4
            result.append(d)
        d -= timedelta(days=1)
    return list(reversed(result))


def fetch_bhav_csv(dt: date) -> bytes | None:
    """Download NSE sec_bhavdata_full CSV for a given date.
    URL: archives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv
    Returns None on 404 (holiday / weekend / future date)."""
    dd   = dt.strftime("%d")    # 01, 15, …
    mm   = dt.strftime("%m")    # 01, 05, …
    yyyy = dt.strftime("%Y")
    url  = (f"https://archives.nseindia.com/products/content/"
            f"sec_bhavdata_full_{dd}{mm}{yyyy}.csv")
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return None           # holiday or weekend
        print(f"    HTTP {e.code} for {dt.isoformat()}")
        return None
    except Exception as e:
        print(f"    Error {dt.isoformat()}: {e}")
        return None


def parse_bhav(data: bytes) -> dict:
    """Parse sec_bhavdata_full CSV → {SYMBOL: {open, high, low, close, volume}} EQ only.
    Columns have leading spaces: ' SERIES', ' OPEN_PRICE', ' CLOSE_PRICE', ' TTL_TRD_QNTY'."""
    result = {}
    try:
        text   = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            # All non-SYMBOL columns have a leading space in their name
            series = row.get(" SERIES", "").strip()
            if series != "EQ":
                continue
            sym = row.get("SYMBOL", "").strip()
            if not sym:
                continue
            try:
                result[sym] = {
                    "open":   round(float(row[" OPEN_PRICE"].strip()),  2),
                    "high":   round(float(row[" HIGH_PRICE"].strip()),  2),
                    "low":    round(float(row[" LOW_PRICE"].strip()),   2),
                    "close":  round(float(row[" CLOSE_PRICE"].strip()), 2),
                    "volume": int(float(row[" TTL_TRD_QNTY"].strip())),
                }
            except (ValueError, KeyError):
                continue
    except Exception as e:
        print(f"    Parse error: {e}")
    return result


def load_cache(ticker: str) -> dict:
    """Load existing per-ticker daily cache as {dt_str: bar}."""
    f = BHAV_DIR / f"{ticker}_daily.json"
    if not f.exists():
        return {}
    try:
        bars = json.loads(f.read_text(encoding="utf-8"))
        return {b["dt"]: b for b in bars if "dt" in b}
    except Exception:
        return {}


def save_cache(ticker: str, cache: dict):
    """Save per-ticker daily cache, sorted by date."""
    bars = sorted(cache.values(), key=lambda b: b["dt"])
    f    = BHAV_DIR / f"{ticker}_daily.json"
    f.write_text(json.dumps(bars, separators=(",", ":")), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="NSE Bhavcopy history downloader")
    parser.add_argument("--days",   type=int, default=180,
                        help="How many trading days back to fetch (default 180)")
    parser.add_argument("--groups", nargs="*", choices=["N50", "NXT50", "MID50"],
                        default=["N50", "NXT50", "MID50"],
                        help="Which groups to update (default: all)")
    parser.add_argument("--delay",  type=float, default=0.8,
                        help="Seconds between downloads (default 0.8)")
    args = parser.parse_args()

    group_map = {"N50": UNIVERSE_N50, "NXT50": UNIVERSE_NXT50, "MID50": UNIVERSE_MID50}
    seen, universe = set(), []
    for g in args.groups:
        for t in group_map[g]:
            if t not in seen:
                seen.add(t); universe.append(t)

    dates = _trading_dates(args.days)

    print(f"NSE Bhavcopy downloader | {datetime.now(IST).strftime('%Y-%m-%d %H:%M')} IST")
    print(f"Groups : {', '.join(args.groups)}  ({len(universe)} tickers)")
    print(f"Dates  : {dates[0].isoformat()} to {dates[-1].isoformat()}  ({len(dates)} trading days)")
    print(f"Delay  : {args.delay}s per download")
    print()

    # Load existing caches
    caches = {t: load_cache(t) for t in universe}
    already_have = {t: set(caches[t].keys()) for t in universe}

    hits = misses = holidays = errors = 0

    for dt in dates:
        dt_str = dt.isoformat()

        # Skip if ALL universe tickers already have this date
        need_any = any(dt_str not in already_have[t] for t in universe)
        if not need_any:
            hits += 1
            continue

        data = fetch_bhav_csv(dt)
        if data is None:
            holidays += 1
            # Mark all tickers as "checked" for this date (holiday = no data)
            continue

        parsed = parse_bhav(data)
        if not parsed:
            errors += 1
            print(f"  {dt_str}  empty parse")
            time.sleep(args.delay)
            continue

        new_for_date = 0
        for ticker in universe:
            if ticker in parsed and dt_str not in already_have[ticker]:
                bar = {"dt": dt_str, **parsed[ticker]}
                caches[ticker][dt_str] = bar
                already_have[ticker].add(dt_str)
                new_for_date += 1

        n_found = sum(1 for t in universe if dt_str in already_have[t])
        print(f"  {dt_str}  {n_found}/{len(universe)} tickers  (+{new_for_date} new)")
        misses += 1
        time.sleep(args.delay)

    # Save all caches
    print("\nSaving caches...")
    for ticker in universe:
        if caches[ticker]:
            save_cache(ticker, caches[ticker])

    # Summary
    print(f"\nDone.")
    print(f"  Downloaded : {misses} days")
    print(f"  Already had: {hits} days (skipped)")
    print(f"  Holidays   : {holidays} days (no data)")
    print(f"  Errors     : {errors}")
    print()

    # Per-group coverage report
    for g in args.groups:
        tickers = [t for t in group_map[g] if t in seen]
        counts = [(t, len(caches[t])) for t in tickers]
        counts.sort(key=lambda x: x[1])
        avg = sum(c for _, c in counts) / len(counts) if counts else 0
        min_t, min_c = counts[0]  if counts else ("?", 0)
        print(f"  [{g}]  avg {avg:.0f} days/ticker | min: {min_t} ({min_c} days)")


if __name__ == "__main__":
    main()
