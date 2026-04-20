#!/usr/bin/env bash
# score.sh — Rolling N-trade metrics. Reads the 23-field POST-MORTEMS.md schema.
#
# Usage:
#   bash scripts/score.sh india 5
#   bash scripts/score.sh us 20
#
# Computes: win_rate, avg_R, expectancy_R, profit_factor, avg dim scores,
#           rule_breach_count (discipline <= 2), grade A-F.
#
# Grading (spec-aligned, discipline on 1-5 scale):
#   A: discipline_avg >= 4.5 AND (win_rate >= 60 OR profit_factor >= 2.0)
#   B: discipline_avg >= 4.0 AND win_rate >= 50
#   C: discipline_avg >= 3.0 AND expectancy_R >= 0
#   D: discipline_avg < 3.0  OR (total_pnl < 0 AND rule_breach_count > 0)
#   F: rule_breach_count > 0 AND total_pnl_abs_pct < -1.0 (session-level cap breach)

set -u
MARKET="${1:?market required (india|us)}"
N="${2:-5}"

FILE="memory/${MARKET}/POST-MORTEMS.md"
if [ ! -f "$FILE" ]; then
  echo "score.sh: $FILE not found; no trades yet."
  exit 0
fi

export FILE MARKET N

python3 - <<'PY'
import os, re, pathlib, statistics, sys

p = pathlib.Path(os.environ['FILE']).read_text()
N = int(os.environ['N'])
MARKET = os.environ['MARKET'].upper()

blocks = re.split(r'^## ', p, flags=re.MULTILINE)
trades = []
for b in blocks[1:]:
    head, _, body = b.partition('\n')
    parts = [x.strip() for x in head.split('·')]
    if len(parts) < 4:
        continue
    def field(name):
        m = re.search(rf'^-\s*{re.escape(name)}:\s*(.+)$', body, re.MULTILINE)
        return m.group(1).strip() if m else None
    def fnum(name):
        v = field(name)
        if v is None: return None
        # strip trailing unit and %, keep sign
        v2 = re.match(r'([-+]?[0-9]*\.?[0-9]+)', v)
        try:
            return float(v2.group(1)) if v2 else None
        except Exception:
            return None
    def fint(name):
        v = fnum(name)
        return int(v) if v is not None else None

    trades.append({
        'ts': parts[0], 'sym': parts[1],
        'outcome_code': parts[2],
        'pnl_pct_head': parts[3].rstrip('%'),
        'R_multiple': fnum('R_multiple'),
        'R': fnum('R'),
        'pnl_abs': fnum('pnl_abs'),
        'pnl_pct': fnum('pnl_pct'),
        'entry_q': fint('entry_quality'),
        'mgmt_q':  fint('mgmt_quality'),
        'rsch_q':  fint('research_quality'),
        'disc':    fint('discipline'),
        'sector':  field('sector'),
    })

sample = trades[:N]
n = len(sample)
if n == 0:
    print(f"{MARKET}_TRADES=0"); sys.exit(0)

def vals(k):
    return [t[k] for t in sample if t.get(k) is not None]

wins = [t for t in sample if t['outcome_code'] and t['outcome_code'].startswith('WIN_')]
losses = [t for t in sample if t['outcome_code'] and t['outcome_code'].startswith('LOSS_')]
winrate = len(wins) / n * 100

R_mults = vals('R_multiple') or []
avg_R = statistics.mean(R_mults) if R_mults else 0
# Expectancy (R): winrate% * avg_win_R + (1-winrate) * avg_loss_R
win_Rs  = [t['R_multiple'] for t in wins   if t.get('R_multiple') is not None]
loss_Rs = [t['R_multiple'] for t in losses if t.get('R_multiple') is not None]
avg_win_R  = statistics.mean(win_Rs)  if win_Rs  else 0
avg_loss_R = statistics.mean(loss_Rs) if loss_Rs else 0
expectancy_R = (len(wins)/n) * avg_win_R + (len(losses)/n) * avg_loss_R

# Profit factor: gross wins / abs(gross losses) in R terms (fall back on pnl_abs)
gross_win = sum(t['pnl_abs'] for t in wins   if t.get('pnl_abs') is not None)
gross_loss = -sum(t['pnl_abs'] for t in losses if t.get('pnl_abs') is not None)  # positive
if gross_loss > 0:
    profit_factor = gross_win / gross_loss
else:
    profit_factor = float('inf') if gross_win > 0 else 0

total_pnl = sum(t['pnl_abs'] for t in sample if t.get('pnl_abs') is not None)
total_pnl_pct = sum(t['pnl_pct'] for t in sample if t.get('pnl_pct') is not None)

disc_scores = vals('disc')
entry_scores = vals('entry_q')
mgmt_scores  = vals('mgmt_q')
rsch_scores  = vals('rsch_q')
disc_avg   = statistics.mean(disc_scores) if disc_scores else 0
entry_avg  = statistics.mean(entry_scores) if entry_scores else 0
mgmt_avg   = statistics.mean(mgmt_scores)  if mgmt_scores  else 0
rsch_avg   = statistics.mean(rsch_scores)  if rsch_scores  else 0

# Rule breach: discipline score <= 2 on the 1-5 scale
rule_breach_count = sum(1 for d in disc_scores if d <= 2)

# Spec-aligned grade (discipline 1-5 scale).
# Order matters: F takes precedence over every higher grade to avoid masking a
# rule-breach + net-negative-PnL session behind an accidentally-decent expectancy.
pf = profit_factor if profit_factor != float('inf') else 999
if   rule_breach_count > 0 and total_pnl < 0:          grade = 'F'
elif disc_avg >= 4.5 and (winrate >= 60 or pf >= 2.0): grade = 'A'
elif disc_avg >= 4.0 and winrate >= 50:                grade = 'B'
elif disc_avg <  3.0:                                   grade = 'D'
elif disc_avg >= 3.0 and expectancy_R >= 0:            grade = 'C'
else:
    # Disc_avg >= 3.0 but expectancy_R < 0 and no rule breach: discipline is
    # adequate yet the strategy is bleeding. Still D — below break-even is
    # below break-even regardless of how "clean" the losses were.
    grade = 'D'

def pf_str():
    return 'inf' if profit_factor == float('inf') else f"{profit_factor:.2f}"

print(f"{MARKET}_TRADES={n}")
print(f"{MARKET}_WINRATE={winrate:.1f}%")
print(f"{MARKET}_AVG_R={avg_R:+.2f}")
print(f"{MARKET}_EXPECTANCY_R={expectancy_R:+.2f}")
print(f"{MARKET}_PROFIT_FACTOR={pf_str()}")
print(f"{MARKET}_AVG_WIN_R={avg_win_R:+.2f}")
print(f"{MARKET}_AVG_LOSS_R={avg_loss_R:+.2f}")
print(f"{MARKET}_TOTAL_PNL={total_pnl:+.2f}")
print(f"{MARKET}_TOTAL_PNL_PCT={total_pnl_pct:+.2f}%")
print(f"{MARKET}_AVG_ENTRY={entry_avg:.2f}")
print(f"{MARKET}_AVG_MGMT={mgmt_avg:.2f}")
print(f"{MARKET}_AVG_RESEARCH={rsch_avg:.2f}")
print(f"{MARKET}_AVG_DISCIPLINE={disc_avg:.2f}")
print(f"{MARKET}_RULE_BREACH_COUNT={rule_breach_count}")
print(f"{MARKET}_GRADE={grade}")
PY
