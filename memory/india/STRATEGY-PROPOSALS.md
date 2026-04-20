# Strategy Proposals — India

Bot writes proposed rule changes here. Human approves by committing the corresponding edit to `TRADING-STRATEGY.md`. Bot NEVER edits `TRADING-STRATEGY.md` directly.

## Gates (enforced by `scripts/proposal-check.sh`)

- Minimum-N:
  - 5 trades → operational tweak
  - 10 trades → sleeve weight shift
  - 20 trades → structural change
- Cooldown: same `dimension:` cannot be re-proposed for 14 days after acceptance/rejection.
- Suppression: `dimension:` rejected 3 times → suppressed for 30 days after 3rd rejection.

## Block format (strict — required for parser)

```
## YYYY-MM-DD · <short name>
- dimension: <slug — e.g. stop_tightening_step, vix_gate_threshold, sleeve_a_weight>
- evidence_n: <N trades>
- current_rule: <quote from TRADING-STRATEGY.md>
- proposed_rule: <specific change>
- expected_impact: <one-liner>
- risk: <one-liner>
- cooldown_until: YYYY-MM-DD  (auto: +14d)
- status: PENDING

<free-text rationale, evidence summary with trade IDs, MFE/MAE distribution if relevant>

Awaiting human approval. Commit TRADING-STRATEGY.md edit to accept, or move this block to STRATEGY-PROPOSALS-REJECTED.md to reject.
```

---
