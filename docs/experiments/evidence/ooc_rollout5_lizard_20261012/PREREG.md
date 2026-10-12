# Pre-registration: rollout5 with the Lizard-capable CTM (ledger §446)

Written and committed before any cohort seed ran with the arm. Philipp's go: 2026-10-12 11:01Z in the project thread
"can we try again with the lizard capable ctm? on 8 workers on the same 128 seeds?" (after "did we ever do the rollout5
on 128 seeds?"). The same-commit control arm is his choice on this thread's decision card (see Control below).

## Question

§430 (`r5`, `STS_OOC_MCTS_LEAF_COMBATS=5`) won 112/128 vs §422 rollout3 115/128 (−2.3 pp [−10.2, +5.5], NOT_SHOWN),
but fell back to V4 on 37.1% of OOC decisions, 98–100% of the support aborts being active Lizard Tail states the #418
CTM refuses. §423 removed those aborts for rollout3 with the Lizard-capable `pathb_r2_lizard` CTM (fallback 2.4%,
111/128). Does rollout5 with the Lizard-capable CTM win more runs than rollout3 with the same CTM on the same seeds?

## Arms ([arm_env.sh](arm_env.sh))

| arm | environment |
|---|---|
| `r5liz` | the §423 `lizard` environment (§422 rollout3 + explicit `pathb_r2_lizard` fast CTM, production Brew fallback, active Lizard on, research-candidate manifest `64da1776…`), with `STS_OOC_MCTS_LEAF_COMBATS` 3 → 5 |
| `lizard` | the unchanged §423 environment (same-commit control) |

Both arms pin `STS_OOC_PUBLIC_FUTURES=0`: #496 made 8 the default after §422/§423/§430 ran, so 0 keeps the arms on the
noncombat-future regime of those runs. `arm_env.sh` refuses to run if the §423 environment does not hold
`STS_OOC_MCTS_LEAF_COMBATS=3` exactly once or already sets `STS_OOC_PUBLIC_FUTURES`.

## Control: why a same-commit rerun ([RERUN-423-70000000.md](RERUN-423-70000000.md))

Before freezing, §423 seed 70000000 was rerun on the run commit with arm `lizard`. It diverged from §423 at OOC
decision 8 (Face Trader, option 1 instead of option 0). The same harness on §423's commit `cf801ef2` reproduced the
first decisions byte for byte, so a code change merged since §423 moved the search, not the harness. The bisect is in
the rerun note. The old §423, §430 and §422 runs therefore cannot serve as exact paired controls on this commit, and
the `lizard` arm is rerun here on the same binary and seeds. If Philipp declines the control (8 workers instead of 16),
only `r5liz` runs and the primary comparison is against §423, labelled approximate (`primary_pairing`), with the
same thresholds.

## Provenance

- Code commit [CODE_COMMIT](CODE_COMMIT) (main after #496). The run commit may differ from it only in docs and tools
  ([worker.sh](worker.sh) refuses otherwise, including changes to the sourced §422/§423 `arm_env.sh` or the candidate
  manifest). Each worker builds `one_combat` and refuses to run unless its sha256 equals [binary.sha256](binary.sha256).
- Seeds 70000000–70000127 (the §422 cohort, reused on purpose for pairing). 16 workers: for each arm, worker W = 1..8
  runs seeds 70000000+16(W−1) .. +15 as one-seed units, 4 at a time.
- Smoke (planning container, this binary and `run_unit.sh`, seeds 80009000–80009001, not cohort seeds): see [SMOKE.md](SMOKE.md).
- Per-unit timeout 6 h. Silver stalls are caught per seed by `bestbench` (`[bestbench-seed-failure]`); such seeds drop out
  of the pairs. No seed is rerun or replaced.
- Units write to the worker's local disk (`$HOME/r5l-ARM-wWW/out/`). When all 16 are done, the worker uploads
  `/mnt/project-files/ooc-rollout5-lizard-446/ARM-wWW.tar` and then `ARM-wWW.DONE.txt` (with the tar's sha256).

## Analysis ([tools/analyze_rollout5_lizard.py](../../../../tools/analyze_rollout5_lizard.py))

Pairs are cohort seeds with a result row in `r5liz`, the same-commit `lizard` control (`lizard_main`) and the old
controls (§423 `lizard`, §430 `r5`, §422 `rollout3` and `off`; every old file read must match its evidence hash).
**Primary:** Δwin = win(`r5liz`) − win(`lizard_main`), paired seed bootstrap 95% CI (10,000 resamples, seed 446).

- **IMPROVED** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

**Secondary (descriptive, cross-commit):** the same difference against §423, §430, §422 rollout3 and §422 off;
exact McNemar p, Δfloor (CI) and Δ end HP, boss deaths, seconds per run, MCTS CPU, owned and fallback share,
support aborts and simulations per run. `lizard_main` vs §423 shows how much the code change since §423 moved
rollout3 itself (descriptive).

**Reading.** rollout3 wins about 87–90% on these seeds; 128 pairs resolve about ±7 pp. NOT_SHOWN is the likely label
and does not show the arms are equal. An IMPROVED result would need a fresh-seed confirmation before any default
proposal.

## Validity

- All 128 units of each arm rc=0 apart from listed stall failures; any other nonzero rc, crash or missing seed makes the
  result INVALID until explained. Old-control hash mismatches make it INVALID.
- Every log prints `[ooc-mcts-config]` with `"leafValue":"native"`, `"prior":"policy"`, `"simulations":2048`,
  `"combatModel":"selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native"`, `"activeLizardCorrection":true`
  and `"leafCombats":5` (`r5liz`) or `3` (`lizard`), and `[ctm-research-candidate] candidate_id=pathb-r2`.

## Decision

Descriptive screen. No default change whatever the label: OOC MCTS stays off (ADR-0027). Philipp decides what comes
next.
