# A20 teacher comparison: harness prepared, artifact access pending

No scientific canary or comparison has run. The bounded diagnostic compares
the unchanged PR #524 A20 CTM with plain/prior Silver at **2k and 10k**
simulations per combat decision. The prior will be the newest completed,
exported general MLP from **generation 5 or 6**, pinned before any outcomes.
There is no trained student or production-default change.

The initial gen3 choice was amended before collection at the user's request.
[PR #535](https://github.com/pherrman1/sts_ai/pull/535) records the gen5 training
window in `/mnt/project-files/silver-az-mlp/gen5/train/`, but the inspected
repository/loop branch, releases, Actions artifacts and accessible local
directories contain no gen5/gen6 model file or published hash. The documented
source is the [existing Claude session](https://claude.ai/code/session_017opPEhx2VSme8yGQdArarV).
The next prerequisite is to export the completed model and its SHA256 from
that environment to an accessible file or repository artifact. An in-progress
gen6 checkpoint or an older-model substitution does not satisfy this design.

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

## Execution after artifact recovery

From the clean reviewed repository commit, replace the artifact placeholders
with the completed gen5/gen6 export and its verified source hash:

```sh
python3 docs/experiments/evidence/a20_teacher_comparison_20261014/run_pilot.py \
  prepare build/a20-teacher-comparison/run-1 \
  --prior /absolute/path/to/combat_policy_mlp_gen5.txt \
  --prior-generation 5 --prior-sha256 VERIFIED_SHA256 \
  --prior-source EXPORT_SOURCE \
  --ctm-dir build/issue507-pilot/run/ctm
python3 docs/experiments/evidence/a20_teacher_comparison_20261014/run_pilot.py \
  canary build/a20-teacher-comparison/run-1
python3 docs/experiments/evidence/a20_teacher_comparison_20261014/run_pilot.py \
  cohort build/a20-teacher-comparison/run-1
```

Preparation builds Release and freezes actual binary/model/tooling hashes and
the complete environment. The canary must pass before the cohort command
will launch. Every seed command goes through the seed guard. Outputs and
attempt latches are exclusive; failed attempts are preserved without retry.
Keep the checks, review, freeze, receipts and raw outputs with the eventual
evidence packet. This preparation packet is not a completed experiment.

## Verification

Debug and Release builds of `one_combat` passed. Six focused CTests passed in
each build: `teacher_schema_compat`, `learned_stop_teacher_contract`,
`vwin_refresh_policy_export`, `ctm_offline_score_rows`, `a20_teacher_runner`
and `a20_teacher_analysis`. Direct Python runs passed **19 analyzer tests**
and **6 runner tests**, including a synthetic canary/cohort through the actual
runner dispatch. No game is executed by these fixtures. Logs are in `checks/`.

Independent implementation and analysis reviews addressed the initialized-RNG
coupling, RAW source/control equality, legitimate escape classification and
runner/analyzer schema agreement. Real-model loading of the newer prior and
scientific canary behavior remain unverified until artifact recovery. The
full repository test suite and gameplay were not run for this preparation.

Knowledge impact: the ledger/index and maintained research page correct the
historical forecast interpretation and identify the pending A20 comparison.
The protocol and analysis contract specify the opt-in research interface.
