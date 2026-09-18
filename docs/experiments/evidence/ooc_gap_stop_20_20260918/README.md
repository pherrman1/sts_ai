# OOC 20% gap-stop quality evidence

This packet records the two quality cohorts run against the same frozen
execution artifact. The binary was not rebuilt between cohorts.

## Frozen provenance

- Source SHA: `495fa147517fdc42e631c513bde5a87b3bb25144`
- `one_combat` SHA256:
  `9a3b8c2bd1e563c691926d823c43767430d03c11b97a9c5f0d924e616beb1250`
- Runtime for the successful independent cohort: project-fair, Act-3 stop,
  keys off, Silver backend, native OOC MCTS, 2,048 simulations, V4 policy,
  allocated 32,768 reuse cap, OMP1 isolated processes. The earlier attempted
  Stage-C cohort initially used OMP12 before its rescue/inconclusive status;
  it is not represented by the raw bundle below.
- Treatment-only setting: `STS_OOC_MCTS_GAP_STOP_20=1`.
- No checkpoint, root-lock, or CPU-profile diagnostic mode was enabled.

## Earlier cohort: runtime inconclusive

The predeclared paired cohort `12003000..12003063` is closed as
`OOC_GAP_STOP_20_QUALITY_INCONCLUSIVE_RUNTIME`. Control seed `12003058`
became a long-tail runtime pathology under the original execution and also
failed to complete when isolated under OMP1. It was not replaced; treatment
was not launched for the incomplete gate. Four other isolated control reruns
matched their OMP12 outcomes and all non-time MCTS counters. The partial 63
control rows remain diagnostic evidence only and are not part of a quality
estimate.

The separate 16-pair smoke established the mechanism/speed result: -41.4%
total OOC simulations, -36.6% median MCTS CPU, and -13.0% median full-run CPU.
The smoke's 9/16 versus 10/16 outcome was not promoted to a quality result.

## Independent 64-pair confirmation

The fresh paired cohort `12004000..12004063` completed all 64 controls before
any treatment runs, followed by all 64 treatments. No process exceeded the
600-second ceiling and no seed was replaced. Raw ignored artifacts are
retained under `build/ooc_gap_stop_20_20260918/fresh12004000/`.

The compact checked-in raw bundle is under [`raw/`](raw/), with 64 seed files
per arm for each result CSV, metadata JSON, MCTS trace CSV, and support JSONL
format. The checked-in [analysis JSON](analysis.json) contains the
machine-readable paired summary; [SHA256SUMS](SHA256SUMS) covers every
checked-in raw file and the analysis JSON.

| Metric | Control | Treatment | Paired delta |
|---|---:|---:|---:|
| Wins | 44/64 (68.8%) | 44/64 (68.8%) | 0.0 pp |
| Mean floor | 48.16 | 47.41 | -0.75 |
| Mean ending HP | 39.88 | 33.31 | -6.56 |

Paired outcomes were 36 both-win, 12 both-lose, 8 control-only, and 8
treatment-only; 16/64 pairs were discordant. Deterministic paired bootstrap
95% CIs were:

- win-rate delta: **0.0 pp [-12.5, +12.5] pp**;
- floor delta: **-0.75 [-2.61, +1.05]**;
- ending-HP delta: **-6.56 [-15.39, +2.13]**.

Trace arithmetic and frozen provenance checks passed for all 128 runs. Control
had 42 unsupported combats/support aborts across 9 seeds and zero gap-stop
events. Treatment had 27 unsupported combats/support aborts across 11 seeds;
gap-stop coverage occurred on all 64 seeds (5,708 gap-stop events). These
support abnormalities are reported, not silently discarded.

## Current status and next gate

The 64-pair confirmation is **`PROMISING`**, not “equivalent”: its win-rate
CI does not exclude zero, while its negative floor/HP point estimates remain
unresolved. The 20% threshold is frozen and no threshold sweep is planned.
Before default promotion, run the independent paired cohort
`12005000..12005127` with the same frozen artifact and robust one-seed OMP1
execution. A strengthened floor/HP disadvantage requires investigation even
if the win-rate remains flat.
