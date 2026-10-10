# Pre-registration: Lizard-capable CTM inside rollout3 OOC MCTS (ledger §423)

Written and committed before any cohort seed ran with the candidate. Philipp's go: 2026-10-10 23:33Z, the
"128 seeds, cloud" option on the decision card "Run the Lizard-fixed rollout3 on the 128 §422 seeds to compare
with current rollout3?" in project thread "OOC MCTS 10-floor depth feasibility" (his request before it:
"first fix the lizard tail issue").

## Question

In §422, rollout3 OOC MCTS fell back to V4 on 19.8% of OOC decisions. 99% of the 2,791 support aborts behind
those fallbacks were active Lizard Tail states the production CTM cannot price: Fairy Potion + active Tail
(1,889, `active_unqualified_lizard`) and Entropic Brew + active Tail (875,
`active_lizard_entropic_brew_unsupported`). Does rollout3 with a CTM that prices those states win more runs
than §422 rollout3 on the same seeds?

## Candidate ([candidate-v3-lizard.json](candidate-v3-lizard.json))

`selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native` (sha256 `c6d56bbc…`) is the production
pathb-r2 fast artifact (`90806c25…`) with only its JSON header changed by `tools/ctm_lizard.py extend --brew --fairy`
(no `--fast-r`): capabilities `lizardFairy` (compose the Fairy Potion before the Tail, using the unchanged production
fast r) and `lizardBrew` (Brew states use the standard child with its own r). Tensors, the plain-Tail r model and
the standard (Brew fallback) artifact are unchanged. The v3 manifest (`64da1776…`, candidateId `pathb-r2`) differs
from the embedded production manifest only in the fast sha256 and `capabilities.fast`. It loads as a research
candidate, never as the default. No C++ change: same binary as §422.

`lizardBrew.rModel` comes from `tools/ctm_lizard.py fit` ([lizard-fit.json](lizard-fit.json),
[stdout](lizard-fit.stdout.json)) on `one_combat ctmlizardfeatures` rows of the cloud Path B scope corpora
`lizard_fairy` and `lizard_brew` (`/mnt/project-files/ctm-pathb/part-*/lizard_{fairy,brew}-*.jsonl`, 40 files each,
CSV sha256s in the fit receipt; copies in `/mnt/project-files/ooc-lizard-fix/`). The standard child's L2 is 0 (chosen on
VALIDATION, which has 2 Tail-fired Brew rows). §412 left both capabilities off because the r models were worse than a
constant on VALIDATION. Here the relevant alternative is not a constant r but a V4 fallback for the whole root.
Calibration of the composed survival on these corpora (descriptive, in-sample for TRAIN; production fast r for Fairy):

| cohort | rows | Tail fired | predicted win | observed win |
|---|---|---|---|---|
| Fairy + Tail | 11,719 | 119 | 0.9987 | 0.9984 |
| Brew + Tail | 2,652 | 43 | 0.9982 | 0.9977 |

Smoke (not cohort seeds; 72000000–001 with `STS_FORCE_RELIC=LIZARD_TAIL`, this arm environment, scratch copy of the same
artifact and manifest): production rollout3 owned 33/138 and 37/127 decisions (102 and 87 Lizard aborts); the
candidate owned 118/121 and 117/120 with 0 support aborts and `[ctm-research-candidate] candidate_id=pathb-r2`.
All four runs won; candidate end HP 16 and 14 vs 68 and 71 (two seeds; descriptive only).

## Arms ([arm_env.sh](arm_env.sh))

| arm | setting | runs |
|---|---|---|
| `lizard` | §422 `rollout3` environment unchanged (its `arm_env.sh` is sourced), plus `STS_OOC_MCTS_COMBAT_MODEL` = the candidate, `STS_OOC_MCTS_BREW_FALLBACK_MODEL` = production standard pathb-r2, `STS_OOC_MCTS_ACTIVE_LIZARD=1`, the candidate manifest and its sha256 | new, this run |
| `rollout3` (control) | §422 rollout3 results, seeds 70000000–127 | existing, `/mnt/project-files/ooc-rollout3-replication/wNN/`, hashes in §422 `data-sha256.txt` |

**Why reuse the control.** Same binary (`39cdac96…`, built from `cd405b4c`), same seeds, same environment apart from the
five CTM variables. Release `one_combat` is bit-reproducible across containers. Before freezing, seed 70000000 was rerun
with the §422 `run_unit.sh` in this container; its result row and MCTS action log are compared with §422's (see Validity).
A deviation would make the comparison invalid, and the plan would be redone with a fresh control arm.

## Provenance

- Code commit `cd405b4c` ([CODE_COMMIT](CODE_COMMIT)); the run commit may differ from it only in docs, tools and the
  candidate model file ([worker.sh](worker.sh) refuses otherwise). Each worker builds `one_combat` and refuses to run
  unless its sha256 equals [binary.sha256](binary.sha256), the candidate model is `c6d56bbc…` and the manifest is `64da1776…`.
- Seeds 70000000–70000127 (the §422 cohort, reused on purpose for pairing). 16 workers; worker W runs block W−1 as 8
  one-seed `lizard` units, 4 at a time. No new smoke: the forced-Tail smoke above used the same artifact bytes and env.
- Expected CPU (**Inference** from §422 and the smoke): about 1,000–1,400 s per run, about 45 CPU-hours, about 1 h per
  4-CPU worker after the build.
- Per-unit timeout 6 h. Silver stalls are caught per seed by `bestbench` (`[bestbench-seed-failure]`); such seeds drop
  out of the pair. No seed is rerun or replaced.
- Output only to `/mnt/project-files/ooc-rollout3-lizard/wNN/`.

## Analysis ([tools/analyze_rollout3_lizard.py](../../../../tools/analyze_rollout3_lizard.py))

Pairs: cohort seeds with a result row in both `lizard` and §422 `rollout3`. **Primary:** Δwin = win(lizard) −
win(rollout3), paired seed bootstrap 95% CI (10,000 resamples, seed 423).

- **IMPROVED** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

Descriptive: exact McNemar p, Δfloor (CI), Δ end HP, boss deaths, seconds per run, MCTS CPU, owned and fallback share,
support aborts, Lizard aborts and simulations per run for both arms, and lizard − §422 `off` (CI).

**Reading.** About 20% of rollout3 decisions change hands, so the expected effect is a few points at most
(**Inference**). 128 pairs resolve roughly ±6 pp here, so NOT_SHOWN is the likely label and does not show the arms are
equal. A clear fallback drop with no win change would still say the Lizard aborts were not what limited rollout3.

## Validity

- The rerun of §422 seed 70000000 matches §422 in its result row (all columns but `sec`) and its MCTS action log.
- All 128 units rc=0 apart from listed stall failures; any other nonzero rc, crash or missing seed makes the result
  INVALID until explained. Every §422 file the analysis reads must match §422's `data-sha256.txt`.
- Every `lizard` log prints `[ctm-research-candidate] candidate_id=pathb-r2`, a `[live OOC MCTS ON …]` line naming
  `combat_transition_deepsets_pathb_r2_lizard.native` with `active_lizard_correction=1`, and `[ooc-mcts-config]` with
  `"leafValue":"native"`, `"leafCombats":3`, `"prior":"policy"`, `"simulations":2048`.

## Decision

Descriptive comparison. No default change whatever the label: OOC MCTS stays off and the production CTM stays as is.
IMPROVED would justify proposing the capabilities for the production manifest (its own gate). Philipp decides.
