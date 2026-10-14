# A20 teacher comparison: gen6 E follow-up complete

The [fresh v2 follow-up](gen6E-attempt-2/RESULTS.md) completed all four sources,
14 supported states and 14 exact controls: **DESCRIPTIVE_COMPARISON_MEASURED**.
The [first attempt](gen6E-attempt-1/RESULTS.md) remains **INVALID_OR_INSUFFICIENT**
after one source hit its 180-second CPU cap; it is not pooled into v2.
The user authorized an observability/resource follow-up under
[PROTOCOL-V2.md](PROTOCOL-V2.md): flushed per-replay progress, 600 CPU/900 wall
seconds per source and a fresh fixed panel. The first attempt is not pooled
into it. Its original frozen tooling is archived in
`gen6E-attempt-1/frozen-source.tar.gz`; the current runner/analyzer implement v2.
The bounded diagnostic compares
the unchanged PR #524 A20 CTM with plain/prior Silver at **2k and 10k**
simulations per combat decision. The user selected the completed
**generation 6 version E** general MLP, pinned before any outcomes.
There is no trained student or production-default change.

The initial gen3 choice was amended before collection at the user's request.
[PR #535](https://github.com/pherrman1/sts_ai/pull/535) records the gen5 training
window in `/mnt/project-files/silver-az-mlp/gen5/train/`, but the inspected
repository/loop branch, releases, Actions artifacts and accessible local
directories contain no gen5/gen6 model file or published hash. The documented
source is the [existing Claude session](https://claude.ai/code/session_017opPEhx2VSme8yGQdArarV).
That earlier access blocker is now resolved: [PR #541](https://github.com/pherrman1/sts_ai/pull/541)
published gen6 E at commit `0f1b70f278fbc188d9ab96688d67004855d88db8`.
Its `combat_policy_mlp_g6_E.txt` bytes were recovered and verified against
SHA256 `ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228`.
The [protocol](PROTOCOL.md) records its exact path and the v2 inference
dependency, now integrated from `main` merge
`531db3e33d5c38674b123932f0d701b066ef21a7` as requested by the user.
Eenc and the generic gen6 version-D export are different models and are not used.

## Why these settings

Two budgets crossed with prior off/on isolate the benefit of additional search
from the benefit of the prior. The 10k plain arm matches the frozen combat
controller underlying this line of work. The 2k arm tests a useful cheaper
teacher candidate; the earlier general MLP at 2k had positive A0 fight-level
evidence (§460), which motivates testing the architecture without qualifying
the new model at A20. A 64/256/40k sweep would add cost and questions before
this small comparison establishes useful A20 evidence.

The [protocol](PROTOCOL.md) fixes four source runs, six chronological fight
slots per source, four paired futures per Silver condition, one excluded
canary, 180 CPU/240 wall seconds per source and two concurrent jobs. Absent or
unsupported slots are never replaced. The [analysis contract](ANALYSIS-CONTRACT.md)
separates forecast fidelity against an independent original-future plain10k
reference, paired combat outcomes, repeat variance and measured cost. It does
not declare an optimal budget or a population winner from four source runs.

## Mechanism corrections

Inspection of the original §408 producer found that battle initialization
overwrote four attempted RNG redraws from the unchanged game seed. Its Silver
forecasts shared part of the reference fight's hidden future. The historical
numbers remain as-run evidence, with this interpretation correction recorded
in the ledger and current research page.

The new A20-only mode redraws the detached battle seed as well as carried
streams, preserving native initialization's four-stream correlation. A
synthetic check inspects the initialized battle streams. Original-future
controls require exact source RAW persistent-state JSON equality, including
combat RNG; RAW HP consistently includes combat-end healing. Legitimate
Smoke Bomb escapes are explicit outcomes, while health, hook and capture
failures remain invalid. Historical modes retain their behavior.

## Execution with the selected artifact

The attempt used the following commands. These output paths now exist and
must not be overwritten or retried. These are historical commands from
producer `dc941156`, not instructions for the current v2 runner:

```sh
python3 docs/experiments/evidence/a20_teacher_comparison_20261014/run_pilot.py \
  prepare build/a20-teacher-comparison/gen6E-run-1 \
  --prior docs/experiments/evidence/silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt \
  --prior-generation 6 \
  --prior-sha256 ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228 \
  --prior-source https://github.com/pherrman1/sts_ai/blob/0f1b70f278fbc188d9ab96688d67004855d88db8/docs/experiments/evidence/silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt \
  --ctm-dir build/issue507-pilot/run/ctm
python3 docs/experiments/evidence/a20_teacher_comparison_20261014/run_pilot.py \
  canary build/a20-teacher-comparison/gen6E-run-1
python3 docs/experiments/evidence/a20_teacher_comparison_20261014/run_pilot.py \
  cohort build/a20-teacher-comparison/gen6E-run-1
```

Preparation builds Release and freezes actual binary/model/tooling hashes and
the complete environment. The canary must pass before the cohort command
will launch. Every seed command goes through the seed guard. Outputs and
attempt latches are exclusive; failed attempts are preserved without retry.
Keep the checks, review, freeze, receipts and raw outputs with the eventual
evidence packet. The first attempt's complete and partial outputs are now
preserved under `gen6E-attempt-1/`.

## Verification

Debug and Release builds of `one_combat` passed. Six focused CTests passed in
each build: `teacher_schema_compat`, `learned_stop_teacher_contract`,
`vwin_refresh_policy_export`, `ctm_offline_score_rows`, `a20_teacher_runner`
and `a20_teacher_analysis`. Direct Python runs passed **19 analyzer tests**
and **6 runner tests**, including a synthetic canary/cohort through the actual
runner dispatch. No game is executed by these fixtures. Logs are in `checks/`.

Independent implementation and analysis reviews addressed the initialized-RNG
coupling, RAW source/control equality, legitimate escape classification and
runner/analyzer schema agreement. Real-model loading of gen6 E, independent
synthetic parity and the first scientific canary passed; the first cohort did
not complete. The v2 canary and full fresh cohort passed all progress and
data checks; see `gen6E-attempt-2/RESULTS.md` and `checks/v2-outcome-review.txt`.
The integrated Release
producer and unit-test builds passed; seven focused CTests passed (the six
above plus `silver_searcher`, 1.63 seconds). Independent review of the merged
v2 inference support passed; see `checks/gen6E-main-review.txt`. The
full repository test suite and gameplay were not run for this preparation.

Knowledge impact: the ledger/index and maintained research page correct the
historical forecast interpretation and record both A20 attempts.
The protocols and analysis contract specify the opt-in research interface.

## Authorized v2 execution

The completed follow-up prepared `build/a20-teacher-comparison/gen6E-run-2` from a clean reviewed commit
with the same E model, generation, SHA256, source URL and CTM paths above;
then executed `canary` and, after it passed, `cohort` with that new directory.
The current runner fixes canary `97150801`, cohort `97150810–97150813`,
600 CPU/900 wall seconds per source and two concurrent jobs. Every completed
replay flushes CSV data and a JSONL timing/progress record; each start record
identifies the active replay if the process is subsequently killed.

The new runtime schema is `ctm_vs_silver_teacher_a20_v2`; the new freeze schema
is `a20_teacher_comparison_freeze_v2`. The analyzer checks ordered progress
against the selected panel and each replay's budget, decisions, simulations
and combat CPU. Its scientific metrics/decision rule are unchanged. Do not
relax this attempt or overwrite its completed outputs.
