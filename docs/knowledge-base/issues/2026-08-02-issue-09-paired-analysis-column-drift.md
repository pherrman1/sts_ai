# Issue 09: `paired_analysis.py` reads the wrong HP/time columns

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-02
- **Source:** [`evaluation/benchmark-protocol.md`](../evaluation/benchmark-protocol.md), "Known limitations"; [`behavior/invariants.md`](../behavior/invariants.md)

## Symptom

`paired_analysis.py::load` reads zero-based column 3 as HP and column 4 as
seconds, but the current `bestbench` producer stores `act` and `hpEnd` there;
seconds is column 9. Win and floor still align, so paired reports silently
report wrong HP/timing differences.

## Evidence

- `paired_analysis.py::load` (line 6): `"hp": int(s[3]), "sec": float(s[4])`.
- `apps/one_combat.cpp::bestBench` header:
  `seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec`.

## Why it matters

The self-play gate uses only win/floor (`floor + 100*WIN_WEIGHT*won`) and is
unaffected, but HP-end and timing analyses in `paired_report` are invalid,
which can mislead regeneration-capacity and quality conclusions.

## Candidate fix direction

Parse by header (or map columns explicitly): HP from `hpEnd` and seconds from
`sec`; add a schema assertion so a producer/consumer mismatch fails loudly.

## Relevant code

- `paired_analysis.py::load`, `paired_report`
- `apps/one_combat.cpp::bestBench`

## Resolution (2026-08-02)

Fixed: `paired_analysis.py::load` parses by header (HP from `hpEnd`, seconds from `sec`) and asserts the 10-column `bestbench` schema, failing loudly on drift. Verified against sample CSVs.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
