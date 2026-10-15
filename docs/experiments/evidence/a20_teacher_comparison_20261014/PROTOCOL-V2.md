# A20 gen6 E teacher comparison — authorized follow-up design

The user accepted a larger fixed resource limit and flushed progress/timing
after each replay, and instructed continuing the comparison. This is a new
attempt with a fresh, fixed panel; §472's incomplete attempt and its freeze
remain historical evidence. Its exact frozen tooling is preserved in
`gen6E-attempt-1/frozen-source.tar.gz` and Git producer `dc941156`.

The scientific question, state selection, CTM/model identities, controller
settings, RAW reference equality, independent-future redraw and analysis are
the same as [the original design](PROTOCOL.md). The completed first attempt's
sources cannot substitute for this panel and are not pooled with it.

## Fixed identity and conditions

- Gen6 version **E**, unchanged native v2 file from PR #541 commit
  `0f1b70f278fbc188d9ab96688d67004855d88db8`, SHA256
  `ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228`.
- PR #524 A20 CTM, unchanged FAST4L, STD2 and candidate manifest hashes in
  the runner. The later calibrated CTM is not substituted.
- Plain/prior Silver at **2k and 10k per decision**, four paired futures per
  setting; prior K=8, weight 400 and root bonus on.
- Original-future plain10k control, exact complete RAW state equality; fixed
  six chronological slots before outcome/support filtering; CTM expectation
  and 32 state samples; source A20 Ironclad, fixed V4 policy, OOC MCTS off.

## Prospective panel and resources

Excluded canary **97150801**. Four cohort sources **97150810–97150813**.
These fresh local pilot seeds are fixed before any follow-up outcome; no
global sealed-holdout claim. Missing or unsupported slots stay missing; no
replacement or seed extension. Up to 24 cohort states, 384 redrawn Silver
forecast fights and 24 original-future controls, plus four source runs.

Hard per-source limits: **600 CPU seconds and 900 wall seconds**, one thread
per source and at most two concurrent sources. At most **five attempts**
including the excluded canary; maximum allocated CPU is **3000 seconds**.
The first attempt used 57–96 CPU seconds for completed sources and failed at
180 seconds on a source reaching all six slots. The new cap provides headroom
for that observed workload; it is not an estimate of eventual runtime.

No retry, resume, replacement or cap increase during this follow-up. The
canary must finish and pass all checks before cohort launch. Preserve a
failure and report it. No quality metrics from an incomplete panel.

## Progress contract and prelaunch checks

The opt-in A20 harness writes `.progress.jsonl` with flushed records for
`source_start`, `trajectory_complete`, `state_start`, `ctm_complete`,
`arm_start`, `arm_complete`, `state_complete` and `source_complete`.
Each record identifies the source and cumulative thread CPU; state records
identify fight/act/floor/encounter. Replay records identify setting, repeat
and budget; completion includes combat CPU, phase CPU, decisions, simulations
and validity. Data streams flush before each progress record, so a forced
kill leaves complete earlier rows and a durable active-replay identity.
Combat CPU keeps the existing `playoutBattle` scope; logging is outside it.
Phase CPU includes copying, callbacks and logging before the completion record.

Focused tests must verify immediate visibility while streams remain open,
write-failure rejection, progress completeness/order/identity/timing, exact
seed/resource/schema pins, and unchanged forecast math. Review the final
diff before committing and freeze the clean source, actual Release binary,
all models, runner/analyzer, both protocols, analysis contract and environment.
All game-seed commands use the repository seed guard. Existing outputs are
exclusive and cannot be overwritten.

## Decision rule

The successful verdict is **DESCRIPTIVE_COMPARISON_MEASURED** only if all four
sources complete, provenance/RAW controls/progress/counts pass, and each source
has at least one supported matched state. Otherwise **INVALID_OR_INSUFFICIENT**.
Use the original analysis contract: equal-source principal summaries, pooled
descriptive summaries, independent-reference fidelity, paired controller
contrasts, variance and measured cost. No confidence intervals, population
winner, optimal-budget, training, OOC decision-quality or default-promotion
claim follows from four sources. This follow-up supersedes only the first
attempt's seeds/resources/observability for the new attempt, not its verdict.

Knowledge impact: the resulting experiment belongs in the ledger and current
research status. The progress interface is documented with the opt-in harness.
