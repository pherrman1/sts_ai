# Gumbel tuning whole-run Test 2: node reuse cap, G16CAP against §775's G16 + mb4

Pre-registered in [../wholerun/PREREG.md](../wholerun/PREREG.md) ("Test 2"): Test 1 (§777) was NOT_SHOWN, so Test 2 is
**G16CAP − G16**, with §775's 1,024 G16 games as the control (Test 1's sentinel: 32 of 32 identical with this binary,
REUSE_VALID). Test 1's counters: the cap resets on 4.92% of C2's reroots and 4.50% of the 32 sentinel G16 games'
reroots, above the PREREG's 1% skip line, so the test runs.

- Authorization: Philipp, 2026-11-09 20:53 CET ("node cap danach ebenfalls"), order after the hallway card and the
  go for tonight's run on 2026-11-10 at 00:22 CET ("Jo klingt gut, go").
- Units: `units.txt`, 1,024 lines `SEED G16CAP` for §775's seeds 111378256-111379279 in ascending order. One game per
  unit. `run_unit.sh` is ../wholerun/run_unit.sh unchanged (arm G16CAP = G16 + `STS_SILVER_NODE_REUSE_CAP=262144`).
- Binary b5090b16 (code 13bb97ec), Test 1's, from the share's binary cache. Share
  `combat-plan/gumbel-tuning-wholerun-test2`.
- Analysis: ../wholerun/analyze.py as frozen with the PREREG. Its `test2` part compares G16CAP from the new units
  with §775's G16 and is valid only with the sentinel, which it evaluates from the new units' G16 games, so NEW_UNITS
  is one directory holding Test 1's extracted units (1,056, with the 32 sentinel G16 games) and this campaign's
  (1,024): `python3 -I ../wholerun/analyze.py NEW_UNITS REF_UNITS OUT [CLAIMS_LIST]`. Gate as Test 1: SPRT gainer
  (H1 +2 pp, alpha 0.05, beta 0.05, look 64), every seed runs; `verify_campaign.py` 1,024 of 1,024 before the analysis.
- Smoke (local, 2026-11-10 00:25 CET): G16CAP-111379281 (a smoke seed) rc 0 in 42 s, log shows "research node reuse
  cap 262144" and the tree reuse line with reuse_cap=262144, 0 cap resets.
- Cost: about 165 lane-hours (G16's 512 s per run × 1.1 for the larger cap, PREREG).
