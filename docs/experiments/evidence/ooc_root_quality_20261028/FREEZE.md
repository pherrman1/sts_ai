# Phase-1 freeze (root quality, card rewards)

- Code commit `4868ae57` (research flag `STS_OOC_ROOT_PROBE_GRID`, default off); RUN_COMMIT = the commit that adds
  this file (campaign files only on top of the code commit).
- Binary `dc0a5fa3…` (`linux-gcc-release-x86-64-v3`), built locally at the code commit.
- Inputs: student_sel `cf6bf7fb…`, SR head `SR_crn_r2_s2_ep20` `28523fb5…` (the §712 copies on the share).
- Environment: §712 arm A verbatim (`run_unit.sh` COMMON) + probe flags; grid `x2b:0,x2b:1,x2b:3,x2b:5,sr:0,sr:1,sr:3,sr:5`,
  4 seeds, 16,384 simulations, exit after the probe row.
- Units: 144 (`units.txt`, from `roots.tsv`), replays of used seeds 111387000–111387255 only; 32 workers × 4 lanes,
  queue schedule.

## Smokes (2026-10-28, this binary, cloud container)

| check | result |
|---|---|
| probe-on vs probe-off game, 111387000 (probe at 37, small grid) | identical, 141/141 rows (header aside) |
| main vs §712 A record, 111387000 | first difference at row 127 (decision 58, map MCTS, floor 13): main is not bit-exact with the §712 games; roots are validated on main (PREREG) |
| full grid cost, 111387001/9, one seed | 1,006 core-s for 8 configurations; all searches 16,384, no errors |
| analysis, 111387001/9, 4 seeds × 1,024 | `analyze_phase1.py` runs; σ_D, ρ_eff, P_self, horizon profile produced |
| fork `9:1:<a_ref key>` vs `9:1:-`, 111387001 | identical, 120/120 rows apart from `by` (forced_decision vs heart1_screen) |
