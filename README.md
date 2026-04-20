# trading-bot — Dual-Market Autonomous Trading Agent

Stateless, cloud-scheduled trading agent for India (Dhan/NSE) + US (Alpaca). Built on top of Claude Code cloud routines. Git as memory. Hard rules as gates. Propose-only self-evaluation subsystem.

**Owner:** Sai
**Capital:** ₹50,000 Dhan (live) + ~$800 Alpaca (paper → live after Month 2)
**Target:** ₹20–25k/mo India + $75–100/mo US

## Architecture

No Python bot process. Claude Code is the bot. Every scheduled routine:
1. Clones this repo (main branch).
2. Injects env vars from the cloud routine config (never from .env in cloud mode).
3. Reads the strategy + memory files.
4. Calls only the bash wrappers under `scripts/` (never curls APIs directly).
5. Writes memory as it goes.
6. Commits + pushes to main before exiting.

Three invariants:
- **Stateless runs** — each routine is fresh.
- **Git as memory** — everything important is a markdown file committed to main.
- **Hard rules as gates** — discipline is enforced in code, not interpretation.

## Quickstart (local smoke test)

```bash
cp env.template .env
# fill .env with your credentials (keep private — .env is gitignored)
bash scripts/dhan.sh funds        # should print Dhan account margin
bash scripts/alpaca.sh account    # should print Alpaca equity/cash
bash scripts/notify.sh "hello"    # should hit your Telegram
```

Run the ad-hoc slash commands inside Claude Code:
```
/portfolio-india
/portfolio-us
```

## Directory layout

```
trading-bot/
├── CLAUDE.md                 Agent rulebook (auto-loaded)
├── README.md                 This file
├── env.template              Credential template
├── .gitignore                Excludes .env, node_modules, etc
├── scripts/                  API wrappers (bash only, no curl in prompts)
│   ├── dhan.sh               India DhanHQ
│   ├── alpaca.sh             US Alpaca v2
│   ├── perplexity.sh         Research (sonar model)
│   ├── news.sh               Moneycontrol/ET/X scraping
│   ├── notify.sh             Telegram bot
│   ├── vix.sh                India VIX + US VIX
│   ├── postmortem.sh         T1 trade post-mortem writer
│   ├── pulse.sh              T2 hourly position pulse
│   └── score.sh              T3 rolling metrics
├── .claude/commands/         Ad-hoc slash commands
├── routines/                 Cloud-scheduled prompt files
│   ├── india/                5 workflows + pulse + monthly-recal + watchlist-approve = 8
│   └── us/                   Same 8 for US
├── data/
│   └── nse_securities.json   Dhan securityId ↔ ticker lookup
└── memory/                   Persistent state (committed to main)
    ├── india/                12 markdown files
    └── us/                   12 markdown files
```

## The watchlist approval flow

You never get surprised by a trade. Every morning:
- **09:00 IST** — Telegram posts the India watchlist. Reply `Y 1,2` or `Y all` or `N`.
- **21:00 IST** — Telegram posts the US watchlist. Same format.

No reply = no trades that session. Default is safe.

## The self-evaluation subsystem (v1.1)

Every exit triggers a post-mortem. Every 60 minutes, a pulse checks open positions. Every day, a graded score is written. Every week, the bot writes a proposal diff. Every month, a deep recal.

**Propose-only authority**: the bot never autonomously changes hard rules. You approve proposals via commits.

## Onboarding

See `SETUP.md` (separate document) or the Setup section of your strategy document for step-by-step for Alpaca paper, Perplexity API, and Telegram bot. GitHub and Dhan are already done.

## Known gotchas

- **Dhan token expires every 30 days** — calendar reminder at day 25.
- **Alpaca `trail_percent` is a string** in JSON, not a number.
- **India MIS auto-square-off at 15:20 IST** — bot exits at 15:15 IST to avoid this.
- **PDT rule for US** — bot respects `daytrade_count < 3` on sub-$25k account.
- **Never create a .env in cloud routines** — credentials must come from cloud env, never committed.

## License

Private / personal use only.
