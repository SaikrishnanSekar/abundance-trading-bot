#!/usr/bin/env bash
# news.sh — Thin catalyst-news wrapper. Delegates to perplexity.sh with a
# hardened "India markets today" or "US markets today" query template.
# Usage:
#   bash scripts/news.sh india            # Today's India catalysts
#   bash scripts/news.sh us               # Today's US catalysts
#   bash scripts/news.sh symbol TICKER    # Ticker-specific catalyst check
#   bash scripts/news.sh vix              # VIX explanation if spiking

set -u

here="$(dirname "$0")"

case "${1:-}" in
  india)
    bash "$here/perplexity.sh" "India stock market today: top 3 market-moving catalysts right now (Nifty 50 / Bank Nifty), RBI + key macro headlines, Dow/Nasdaq overnight impact. Include tickers and cite sources. Mention India VIX level if elevated."
    ;;
  us)
    bash "$here/perplexity.sh" "US stock market today: top 3 market-moving catalysts right now (S&P 500 / Nasdaq), Fed watch, major earnings this week, semis/AI news. Include tickers and cite sources. Mention VIX level if elevated."
    ;;
  symbol)
    SYM="${2:?ticker required}"
    MKT="${3:-india}"
    if [ "$MKT" = "us" ]; then
      bash "$here/perplexity.sh" "Latest market-moving catalysts for US ticker $SYM in last 48 hours: earnings, analyst actions, sector news, guidance changes. Include citations. Flag if there is an earnings event within next 5 sessions."
    else
      bash "$here/perplexity.sh" "Latest market-moving catalysts for Indian ticker $SYM (NSE) in last 48 hours: earnings, management commentary, sector news, block deals. Include citations."
    fi
    ;;
  vix)
    bash "$here/perplexity.sh" "What is driving elevated volatility in Indian and US markets today? India VIX and US VIX context. Cite sources."
    ;;
  "")
    echo "Usage: news.sh {india|us|symbol TICKER [market]|vix}" >&2
    exit 1
    ;;
  *)
    echo "news.sh: unknown subcommand: $1" >&2
    exit 1
    ;;
esac
