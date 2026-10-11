# Pre-registration: four one-setting rollout3 variants (ledger §427–§430: s4096 §427, wnarrow §428, wbroad §429, r5 §430)

Written and committed before any cohort seed ran with a variant. Philipp's go: 2026-10-11 13:41Z in project thread
"OOC MCTS 10-floor depth feasibility": "can you try the following things on teh same 128 seeds: 4096 simulations,
different progressing widening for the chance nodes (one cofnig for mroe and one for fewer), and rollout 5 isntead of 3.
use 8 cloud workers each for those 4 configs."

## Question

§422: rollout3 (2048 simulations, chance widening `K=2, alpha=0.5`, 3 rollout combats) won 115/128 vs 101/128 for MCTS
off. §424: at 512 simulations it won 108/128. Does any single change to rollout3 win more runs on the same seeds?

## Arms ([arm_env.sh](arm_env.sh))

Each arm is the §422 `rollout3` environment (its `arm_env.sh` is sourced: production pathb-r2 CTM, V4 prior, native
leaf, early stop on) with exactly one setting changed. `arm_env.sh` refuses to run if the §422 environment no longer
holds the replaced line exactly once.

| arm | change | what it does |
|---|---|---|
| `s4096` | `STS_OOC_MCTS_SIMS` 2048 → 4096 | twice the search budget |
| `wnarrow` | `WIDEN_K` 2 → 1, `WIDEN_ALPHA` 0.5 → 0.25 | fewer sampled outcomes per chance node: deeper, narrower tree |
| `wbroad` | `WIDEN_K` 2 → 4, `WIDEN_ALPHA` 0.5 → 0.75 | more sampled outcomes per chance node: shallower, wider tree |
| `r5` | `STS_OOC_MCTS_LEAF_COMBATS` 3 → 5 | each leaf plays 5 imagined combats (V4 policy + CTM) before the native value |
| `off`, `rollout3` (controls) | §422 runs on seeds 70000000–127 | existing, `/mnt/project-files/ooc-rollout3-replication/wNN/` |

Chance widening caps the particles of a chance node at `ceil(K·N^alpha)` after `N` visits (`OocMctsPlanner::chanceWideningLimit`);
decision nodes are fully expanded. At `N` = 100 the caps are 4 (`wnarrow`), 20 (§422) and 127 (`wbroad`). The two
widening settings are the existing `06_narrow` and `07_broad` definitions in `tools/ooc_mcts_parameter_search.py`; they
were never run at this scale. **Default chosen here**: Philipp asked for "one for more and one for fewer" without values.

`r5` needs a code change: `STS_OOC_MCTS_LEAF_COMBATS` accepted only 0, 1 and 3. Commit `0ee840b1` also accepts 5 (in
the live control parser and the adapter constructor); the continuation, its 1,024-step limit and all other values are
unchanged. The adapter self-test now runs the exact-horizon continuation check for 1, 3 and 5 combats and still
rejects 2 and 4 (`oocmctsselftest` PASS).

## Control reuse (launch gate)

The new binary (`3269ece9…`, built from `0ee840b1`) differs from the §422 binary (`39cdac96…`). Reusing the §422 controls
needs it to play rollout3 identically. Before freezing, §422 seed 70000000 is rerun with the new binary and this
`run_unit.sh` (arm `rollout3`). Its result row (all columns but `sec`), MCTS action log and support trace must be
byte-identical to §422 ([§423 rerun](../ooc_rollout3_lizard_20261010/RERUN-422-70000000.md)), as recorded in
[RERUN-422-70000000.md](RERUN-422-70000000.md). Any deviation means the plan is redone with fresh control arms.

## Provenance

- Code commit [CODE_COMMIT](CODE_COMMIT). The run commit may differ from it only in docs and tools ([worker.sh](worker.sh)
  refuses otherwise). Each worker builds `one_combat` and refuses to run unless its sha256 equals
  [binary.sha256](binary.sha256).
- Seeds 70000000–70000127 (the §422 cohort, reused on purpose for pairing). 32 workers: for each arm, worker W = 1..8 runs
  seeds 70000000+16(W−1) .. +15 as one-seed units, 4 at a time.
- Smoke (planning container, this binary and `run_unit.sh`, seeds 72000003–005, not cohort seeds): see [SMOKE.md](SMOKE.md).
- Per-unit timeout 6 h. Silver stalls are caught per seed by `bestbench` (`[bestbench-seed-failure]`); such seeds drop out
  of that arm's pairs. No seed is rerun or replaced.
- Units write to the worker's local disk (`$HOME/r3v-ARM-wNN/out/`). When all 16 are done, the worker uploads
  `/mnt/project-files/ooc-rollout3-variants/ARM-wNN.tar` and then `ARM-wNN.DONE.txt` (with the tar's sha256).

## Analysis ([tools/analyze_rollout3_variants.py](../../../../tools/analyze_rollout3_variants.py))

Per arm, pairs are cohort seeds with a result row in the arm and both §422 arms. **Primary:** Δwin = win(arm) −
win(§422 rollout3), paired seed bootstrap 95% CI (10,000 resamples, seed 427).

- **IMPROVED** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

Four arms are labelled separately with no multiplicity correction. **Secondary (descriptive):** Δwin vs §422 off (CI),
exact McNemar p, Δfloor (CI) and Δ end HP for both comparisons, boss deaths, seconds per run, MCTS CPU, owned and
fallback share, support aborts and simulations per run.

**Reading.** rollout3 already wins 89.8% on these seeds; 128 pairs resolve about ±7 pp against it (§423: [−10.9, +4.7]).
NOT_SHOWN is the likely label for every arm and does not show the arms are equal. An IMPROVED arm would need a
fresh-seed confirmation before any default proposal.

## Validity

- The launch gate above passes.
- All 128 units of an arm rc=0 apart from listed stall failures; any other nonzero rc, crash or missing seed makes that
  arm INVALID until explained. Every §422 file the analysis reads must match §422's `data-sha256.txt`.
- Every log prints `[ooc-mcts-config]` with `"leafValue":"native"`, `"prior":"policy"`, the production
  `combat_model=selfplay/models/combat_transition_deepsets_pathb_r2.native` and the arm's values of `"simulations"`,
  `"wideningK"`, `"wideningAlpha"` and `"leafCombats"`.

## Decision

Descriptive screen. No default change whatever the labels: OOC MCTS stays off. Philipp decides what comes next.
