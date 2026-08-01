# Issue 16: PVNet sweep provenance is unverified

- **Status:** open
- **Tier:** High
- **Last verified:** 2026-08-02
- **Source:** [`evaluation/current-baselines.md`](../evaluation/current-baselines.md), "Known limitations"

## Symptom

The recorded Searcher3/PVNet experiment (best 100-sim policy-only point 66.4%)
omits the seed range and exact complete command, and labels its OOC stack
"heuristic OOC baseline + PUCT (GBM policy)" without defining that stack.
Separately, the tracked PVNet's training data is described as fair, but the
archived producer invocation records `STS_SEARCHER3=1` without `STS_FAIR=1`,
and the raw dataset is not tracked. Project-fair integration provenance is
therefore unverified.

## Evidence

- `current-baselines.md` baseline table and "Known limitations".
- `EXPERIMENTS.md` final section "Phase 4b PVNet alpha sweep".

## Why it matters

The 66.4% point is the strongest headline near the current default, but without
seeds, command, and fair-mode provenance it cannot be reproduced, compared
paired, or trusted as evidence for enabling PVNet by default.

## Candidate fix direction

Rerun the sweep with a recorded seed block, exact command, pinned model hashes,
and `STS_FAIR`/`STS_SEARCHER3` flags; verify training-data provenance or label
the claim **Unverified** in the ledger.

## Relevant code

- `EXPERIMENTS.md` "Phase 4b PVNet alpha sweep"
- `apps/one_combat.cpp::main` (PVNet/DIST_VNET parsing)

## Resolution (2026-08-02)

Not addressed: rerunning the PVNet sweep with recorded provenance needs machine time and was deferred by choice (2026-08-02). `current-baselines.md` keeps the sweep marked unverified.

## Closed by

*Fixed in the 2026-08-02 working tree. No change; remains open.*
