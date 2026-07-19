# Observation Mode — NO NEW DHAN ORDERS

Set by Sai, 2026-07-19 (in-session instruction).

- **Hold dates: 2026-07-20 through 2026-07-22 (inclusive). NO new orders on Dhan.**
  (Sai specified observing Mon 20 + Tue 21 and taking real trades on Thu 23;
  Wed 22 stays in observation by default until Sai says otherwise.)
- **Live entries resume: 2026-07-23.**
- Purpose: monitor v4 recommendation quality (10-min ABUNDANCE SCAN + ORB scans)
  and the corresponding journal entries (`journal/india/recommendations.jsonl`)
  before risking capital. Every ORB ENTRY signal is auto-journaled with
  deterministic ids (ORB-DATE-TICKER-SIDE) for EOD grading.
- While this file lists today's date as a hold date, `/trade-india` must STOP
  before proposing any order and reply "OBSERVATION MODE — no orders until
  2026-07-23".
- Scanners, journaling, Kotak feed, and EOD reports all run normally.

Remove or edit this file (human commit) to lift the hold early.
