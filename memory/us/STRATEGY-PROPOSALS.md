# Strategy Proposals — US

Bot writes proposed rule changes here. Human approves by committing the edit to `TRADING-STRATEGY.md`. Bot NEVER edits `TRADING-STRATEGY.md`.

## Gates (enforced by `scripts/proposal-check.sh`)

- Minimum-N:
  - 5 trades → operational tweak
  - 10 trades → sleeve / tilt weight
  - 20 trades → structural change (incl. paper→live flip)
- Cooldown: 14 days per `dimension:` after acceptance or rejection.
- Suppression: 3 rejections on same dimension → 30-day block.

## Block format (strict — required for parser)

```
## YYYY-MM-DD · <short name>
- dimension: <slug — e.g. trail_tighten_at_15pct, earnings_window_sessions, ai_semi_tilt_weight>
- evidence_n: <N trades>
- current_rule: <quote from TRADING-STRATEGY.md>
- proposed_rule: <specific change>
- expected_impact: <one-liner>
- risk: <one-liner>
- cooldown_until: YYYY-MM-DD
- status: PENDING

<free-text rationale, trade IDs, MFE/MAE distribution if relevant>

Awaiting human approval. Commit TRADING-STRATEGY.md edit to accept, or append to STRATEGY-PROPOSALS-REJECTED.md with dim:<slug> to reject.
```

Paper→Live flip is a structural proposal (≥ 20 trades of paper evidence + 2 months beating target + discipline ≥ 4/5 + dd < 15%). The human physically edits `.env`; bot only proposes.

---
