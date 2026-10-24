# Leaf head, on-policy round 1: label the states the head's own search reaches (pre-registered, 2026-10-23)

Plan written before any data of this round. Philipp chose "Plan the on-policy round" (decision card, 2026-10-23
17:49Z) after §664. This PR brings the generator change (default off), the campaign files and this plan. The campaign
runs only after his typed go and a worker count, from a freeze on main (`tools/cloud/README.md`, "Freeze"). Seeds
reserved by the coordinator (2026-10-23 18:10Z): 111390000-111391999 and 111399990-111399999.

## Why

§664 (`../silver_leaf_label_data_20261023`): the end-to-end net trained on Silver's searched value at every root
(`qe2e`) orders exact leaf values better than every earlier head and wins first fights even without a playout. In the
3-source smoke it still scores below production at 50/50 with the playout: −2.7 points per fight [−3.5, −2.1], boss
fights −28.5 each (10 fights), hallway fights +7.0. Every head so far learned from roots that production's own
playout search reached. A search that trusts the head can steer into states its training never had, where the head
can be wrong with nothing to correct it (the compounding-error argument behind DAgger). This round tests that
explanation with the standard remedy: play with the head, label the states its search reaches with production's
search there, retrain on both, and test again.

## What changes: `STS_AZGEN_LABEL_SEARCH=1` (default off)

`one_combat silverazgen` with `STS_AZGEN_PRODUCTION_COMBAT=1` and a leaf head (`STS_SILVER_LEAF_HEAD`; the flag fails
without them, and `silverazfocusgen` refuses it):

- The fights play Silver with the head as leaf. After the played search at each root, a second searcher searches the
  same root as production does: the same configuration without the head (playout leaf, root and tree prior, boss
  prior playouts, root table), the same flat budget, its own retained graph rerooted along the played path under the
  same 32k reuse cap. It never chooses the action.
- Root rows: `edges` and `inheritedVisits` are the label search's, `playEdges` and `playInheritedVisits` the played
  search's; `chosen`, the wire (the played root) and the fight rows (`score` = the head's play) are as before. The
  label edges are written in the played root's edge order and action bits, because two roots that are equal for
  search can order the hand differently or hold the other copy of an equivalent card. The manifest counts the roots
  whose two edge sets could not be matched (`labelSearch.edgeFallbacks`); the feature extractor drops those. So
  `../silver_leaf_a20_data_20261022/pack_a20.py`, unchanged, gives `qchosen` = production's searched value at the
  states the head's play reaches, with the same features as the a20prod pack.
- The teacher id gains `-headplay`. The manifest records `labelSearch` only when the flag is on.
- Code: `src/sim/search/NativeSilverBackend.cpp` (`g_nativeSilverLabelSearch`, thread-local; the reroot and per-root
  configuration code now serves both searchers; the label search requires a flat budget) and
  `apps/one_combat/silver_synth_gen.cpp`.

The label is what production's search says at that state with the same new budget, having searched the fight's
earlier roots along the same path. It can inherit fewer visits than production does along its own path, since the
head may play an edge the label graph visited little; `shift.py` reports both searches' inherited visits.

## Checks (seeds 111399990-991; A20 natural, production chain and combat; main 09146204 against this change)

`check_label.sh BASE NEW OUT 1000`, 2 runs per mode, BASE = main 09146204 (one_combat sha256 c2e7fcf4...), NEW = this
change (c18a9a73...); output in `results/checks.txt`.

- Flag off: production play and head play give byte-identical rows with both binaries (951 and 1,612 rows); the
  manifests differ only in the binary hash and the rows path.
- Flag on: the play is identical to head play in every row (1,612 rows, 1,555 roots) apart from `edges` and
  `inheritedVisits` (now the label's) and the teacher id. Every root has a label (`labelRoots` 1,555) and one root
  is an edge fallback (0.06%). At the 30 roots where the head's path had not yet left production's (same history,
  same state), the label equals production's search exactly (30 of 30).
- `silversynthfeatures` keeps 1,554 of the 1,555 label roots (it drops the fallback as `rootEdgeMismatch`) and every
  root of the other two outputs (914 and 1,555).
- 10,000 simulations, the same seeds, three runs at once on 4 cores, with an earlier build that wrote the label edges
  in the label root's order (the searches are the same): production 1,484 roots in 1,026 s (0.69 s per root), head
  play 922 roots in 805 s (0.87 s), head play with the label 922 roots in 1,567 s (1.70 s). The label search inherits
  4,593 visits per root on average, the played search 6,018 and production along its own path 6,390 (act 4: 2,259,
  5,767 and 5,553).
- Peak memory at 10,000 simulations (first 8 minutes of one run): 0.83 GB with the label, 0.46 GB without; 4 lanes
  fit a 15 GB worker.
- `ctest -R "silver|one_combat"`: 26 of 29 pass, among them the 8 Silver unit tests of the `test` binary;
  `live_silver_importer`, `one_combat_tree_parity` and `one_combat_feature_regression` have no binary here (their
  build did not finish in 40 minutes). The full ctest was not run, and CI is down (GitHub billing).
- `shift.py` runs on the 1,000-simulation output (2 runs on the test seeds, not campaign data: the head's action is
  the label's at 66% of roots; the played search values the root 3.7 points above the label, +9.8 in boss fights).

## Campaign

- 256 units of 2 natural runs, seeds 111390000-111390511 (`units.txt`), queue schedule, 4 lanes per worker.
- `record_env.sh`: the a20prod campaign's environment (`../silver_leaf_a20_prod_20261022`: A20, student_sel argmax
  out of combat through the production chain, flat exact 10,000 simulations without the learned stop, production
  combat) plus `STS_SILVER_LEAF_HEAD_BLEND=0.5`, `_TURN_PENALTY=0`, `_WIN_CAP=0` and `STS_AZGEN_LABEL_SEARCH=1`.
  This is the configuration of qe2e's smoke row.
- `run_unit.sh`: that campaign's, with the head and trunk from RUN and a manifest check: rc=97 unless the run played
  the production chain, production combat with boss prior playouts, the frozen head and trunk at blend 0.5 without
  turn penalty or cap, and searched a label at every root (`labelRoots` = roots).
- Inputs (`campaign.manifest`, hash-checked): `student_sel.bin` (cf6bf7fb...), `q_e2e_head.txt` (c2c7418e...),
  `q_e2e_trunk.txt` (4efed23e...), as in §664.
- Freeze, after the go: merge this PR; set `code_commit` (main), `binary_sha256` and `workers` (his count) in
  `campaign.manifest`; publish the binary; fill in `BRIEF-worker.md`; independent pre-launch review (clean build
  against `binary_sha256`). The coordinator starts the workers.
- Frozen 2026-10-23 after Philipp's typed go (19:35Z: "let's do 512 runs on 32 workers"): `code_commit` a8b80139, main
  with this PR (#837) and four engine parity fixes merged just before it (#831 Hand of Greed, #833 Angry, #835 Time
  Eater, #836 Trip; §665-668), `binary_sha256` 0feb879d..., 32 workers. Known deviation: the a20prod campaign ran
  without those four fixes, so the two packs come from slightly different engines in the few states they touch. The
  smoke runs both nets on its own fixed binary, so its contrasts stay paired.

## Expected cost

A root costs 2.46 times production's at 10,000 simulations on the same machine (1.70 s against 0.69 s): the head plays
at 1.26 times production's cost and the label adds a production search. The production campaign
(`../silver_leaf_a20_prod_20261022`: 1,536 runs, about 778,000 roots) took 5 h 11 min on 8 workers, about 0.77
lane-seconds per root with its tail, and its natural runs averaged 515 roots. The head's runs end earlier (461 roots
per run against production's 742 in the checks), so 512 runs at 515 roots and 1.9 lane-seconds per root bound the
campaign at about 140 lane-hours. An average unit (2 runs) takes about 33 minutes, two runs into act 4 about an hour.

| workers (4 lanes each) | wall |
|---|---|
| 8 | about 4.5-5 h |
| 16 | about 2.5 h |
| 32 | about 1.5 h (the longest units set the tail) |

Afterwards, in this container on CPU: the packs, the three fits and the exact leaves take a few hours, each 16-source
smoke about 1.5 h. The qe2e smoke can run while the campaign runs.

## Analysis (pre-registered)

`E` = this directory, `L` = `../silver_leaf_label_data_20261023`; CPU only, on 4 cores.

1. Verify and extract: `python3 tools/cloud/verify_campaign.py $E --extract DEST`. Units with rc != 0 are rerun
   locally from their seeds.
2. Packs: this campaign's (`onpol`) with `../silver_leaf_a20_data_20261022/pack_a20.py` and the campaign binary;
   the production pack (`a20prod`, 777,993 roots) rebuilt by `L/build_pack.sh prod` (sha256 47efc292... as in §664).
   Roots of a fight that a stall cut short have no fight row, and `pack_a20.py` drops them; they are counted.
3. Shift (descriptive): `shift.py` on the units (how often the head's action is production's, production's estimate
   of what the head's choices cost, the gap between the two searches' root values, inherited visits; by act, room,
   turn), and the `qe2e` rows of step 4.
4. Retrain: `QE2E=checkpoints/q_e2e.pt SAVE=1 python3 $E/train_onpolicy.py a20prod_pack.npz onpol_pack.npz
   g7f_E/model.pt out` (§664's `e2e` recipe with the searched-value label: Adam, head lr 1e-3, trunk lr 3e-4 with
   weight decay 1e-5, batch 1024, early stop with patience 5, folds seed % 5): `qe2e` evaluated, `ref` (the recipe
   refit on the production pack) and `onpolicy` (fit on folds 0-2 of both packs, stop on fold 3 of both). Each is
   reported on fold 4 of each pack: RMSE and bias against the label by act, room, turn and act x room. The
   `onpolicy` net becomes `onp1` (`L/export_e2e.py`) and is checked against PyTorch on 300 leaves dumped by
   exact_combat_solver (`L/parity.py`; §664 found at most 1.2e-5 points).
5. Exact leaves (descriptive): `L/leaf_exact.py` with qe2e and onp1 on the capacity test's 69,734 leaves.
6. Smoke: `W=$W $E/run_smoke16.sh TAG HEAD TRUNK` for qe2e and onp1: the fight-level harness of §656 with its binary
   (83de6c12...), production at 10,000 simulations against the net as leaf at 50/50 without turn penalty or cap, on
   16 sources (111339997-999 as before, plus 111391000-012), R = 2. Then `pair.py OUT.json out_qe2e out_onp1`:
   onp1 − qe2e and each net − production, paired per fight, 95% bootstrap over the 16 sources; it stops unless
   production's arm is identical in both runs. The qe2e smoke can run while the campaign runs.

## Gates and what follows

- **G1, data.** Every unit verified with rc=0 after local reruns; at least 95% of the runs complete (a stall ends a
  run early: stalls are counted and reported); `edgeFallbacks` at most 1% of the roots. Otherwise stop and report.
- **G2, shift (descriptive; the prediction).** If the explanation holds, qe2e's fold-4 error against the label is
  larger on the on-policy pack than on the production pack, most in boss fights, and biased upward there (the head
  overvalues the states its search steers into). Read it next to the inherited-visit gap from `shift.py`: the label
  search inherits fewer visits along the head's path (checks: 4,593 against production's 6,390 per root; act 4:
  2,259 against 5,553), so its labels are noisier there even without a shift (pre-launch review note).
- **G3, fit** (decides whether onp1 gets a smoke). onp1's fold-4 RMSE on the on-policy pack at least 0.5 points
  below ref's, and on the production pack at most 0.3 points above ref's. The on-policy half is close to automatic
  for a net fitted on that pack; the production half and G4 carry the decision.
- **G4, screen** (decides whether a fight-level A/B is proposed). In the 16-source smoke, onp1 − qe2e has a positive
  mean score per fight over all fights and over boss fights, and onp1 − production over all fights is not WORSE
  (the bootstrap interval's upper bound is at least 0).

If G4 passes, the thread proposes the fight-level A/B of `../silver_leaf_head_ab_20261022` for onp1 (256 sources, about 140
lane-hours with its four arms), which needs Philipp's typed go and a worker count. If G3 or G4 fails, the round goes
to the ledger as a negative result, and nothing more is proposed on this line unless Philipp asks. No default changes
either way.

Power: 16 sources give a 95% interval of about ±5 points per fight for a score difference (the 64-source maxbackup
A/B had ±2.7), so G4 is a screen. A net no better than qe2e passes it about a quarter to a third of the time; one that
loses clearly in boss fights rarely does.

## Files

- Campaign: `record_env.sh`, `run_unit.sh`, `units.txt`, `campaign.manifest`, `BRIEF-worker.md`.
- Checks: `check_label.sh`, `compare_label.py`, `results/checks.txt`.
- Analysis: `shift.py`, `train_onpolicy.py`, `run_smoke16.sh`, `pair.py`; from §664: `pack_a20.py`, `build_pack.sh`,
  `export_e2e.py`, `parity.py`, `leaf_exact.py`, the smoke's `run_unit_smoke.sh` and `analyze2.py`.
- `pair.py` on §664's archived smoke rows (qe2e at 50/50 and qe2e alone) reproduces both rows of its table (−2.710
  [−3.500, −2.143] and −39.810 [−48.256, −33.857] per fight), with production's arm identical in both runs.
