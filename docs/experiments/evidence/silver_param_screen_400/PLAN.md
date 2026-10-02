# #400 Stage 1: Silver search-parameter heterogeneity screen (frozen plan)

Status: **pre-registered, not yet run.** Written before any cohort seed ran;
only the one-seed smoke below has executed. Results go to the experiment
ledger with the run's evidence packet.

## Question

Do different combat contexts prefer different native Silver search constants
strongly enough that a per-combat choice beats the single best global choice?
This screens for heterogeneity only. It is not a global retune, and it builds
no controller (Stage 2 of #400 runs only if this passes).

## Baseline and intervention

- Baseline: exact-10k ordinary project-fair native Silver teacher (flat 10,000
  simulations at every root, `STS_SILVER_EXACT_ROOT_BUDGETS=1`, adaptive off,
  allocated reuse cap 32,768), default V4-gated OOC policy chain, keys off,
  Ascension 0. Teacher constants: exploration 25/25, chance and end-turn
  widening `C=3.7028`, `alpha=0.52389`.
- Intervention: `one_combat silverparams400gen` plays each source seed with the
  baseline, captures a detached pre-battle copy of **every** real fight
  (outcome-blind, no selection), and replays each fight under five arms that
  differ only in the search constants. Same state, agent, hidden future and
  simulation budget per arm.

| Arm | Change from control |
|---|---|
| `control` | none; must reproduce the source fight exactly (outcome, terminal HP, post-battle HP, first action) |
| `c12` | exploration 12.5 (decision and chance children) |
| `c50` | exploration 50 |
| `wa040` | widening alpha 0.40 (chance and end-turn) |
| `wa065` | widening alpha 0.65 |

The constants reach the searcher only through a thread-local override that
this mode sets; production and every other mode leave it unset.

## Cohort and budget

- Source seeds `40000000..40000127` (128; prefix unused in `docs/`, `tools/`,
  `apps/`, `EXPERIMENTS.md`). Four shards of 32 seeds, one process each,
  `OMP_NUM_THREADS=1`, every invocation through `tools/seed_guard.sh`.
- Smoke (not pooled): seed `40009000`, 26 fights, control replay 26/26,
  about 485 CPU-seconds per seed (source about 85 s, arms about 3.1 s per fight
  per arm). Projection for 128 seeds: about 17 CPU-hours, about 4.5 hours wall
  on a 4-CPU cloud container, about 3,300 fights.
- Stop rule: a shard that exits nonzero is kept as evidence and not retried or
  replaced; the analysis then runs on complete shards only and says so.

## Metric and decision rule

Implemented in `tools/analyze_silver_param_screen_400.py` (self-test in ctest).

- Q = `signedOutcome` per fight (win: terminal HP / max HP; loss: minus the
  enemy HP fraction left). A fight counts only when all five arms are valid
  and the control replay matched.
- Split by source seed: `sha256("silver-param-400-v1:{seed}")[:8] / 2^32`
  below 0.5 is DISCOVERY, otherwise CONFIRMATION.
- Context cell = room class (NORMAL / ELITE / BOSS / OTHER) x act.
- On DISCOVERY: `global*` = arm with the best pooled mean Q; `cell*` = best arm
  per cell with at least 20 fights, else `global*`.
- On CONFIRMATION: D = mean over fights of `Q[cell*] - Q[global*]`, 95%
  source-seed-clustered bootstrap (2,000 replicates, seed 0).
- Verdict:
  - `ADAPTIVE_SEARCH_PARAMS_SIGNAL`: D >= 0.01, CI lower bound > 0, and the
    per-cell policy uses at most 1.10x the CPU of `global*`. Proceed to Stage 2.
  - `ADAPTIVE_SEARCH_PARAMS_NOT_JUSTIFIED`: every cell picks `global*`, or the
    CI upper bound is below 0.01. Close Stage 1.
  - `INCONCLUSIVE` otherwise: gather only enough additional matched fights to
    resolve the leading alternatives (needs new authorization).
- Reported but not part of the verdict: `global*` minus control on
  CONFIRMATION (a global retune is a separate question), per-cell deltas with
  CIs for every arm, win-rate and potion-use deltas, CPU ratios.

Smoke noise: per-fight paired SD of Q differences was 0.04-0.08, so the
CONFIRMATION half (about 1,650 fights) should resolve D to roughly +/-0.005.
