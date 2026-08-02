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

## Re-check 2026-08-02: headline does not reproduce

The closest reconstructable configuration was run on the recorded block
(`STS_FAIR=1 STS_SEARCHER3=1 STS_PVNET=build/v_combat_pvnet.txt
STS_PVNET_ALPHA=0 ./build/one_combat bestbench 100 128 0 126700`, tracked
PVNet sha256 `05d80929...`, policy prior auto-loaded; EXPERIMENTS.md §72):

- default Searcher2 fair @100 sims: **4.7% / 29.5 floor / 2.0 HP**
- PVNet α=0 @100 sims: **8.6% / 26.4 / 4.2** (paired +3.9pp win, CI [−0.0,
  +8.6]; floor −3.1, CI [−5.6, −0.6])
- PVNet α=1.0 @100 sims: **5.5% / 24.4 / 2.8** (α-ordering claim holds)

**Finding:** the recorded 66.4% does not reproduce on the current checkout and
the recorded seed block; no 60–70% combination exists on the current binary.
Most plausible explanation (labelled **Inference**, investigation note
`2026-08-02-pvnet-664-headline-not-reproducible.md`): the sweep ran on
pre-fix Searcher3 (sweep dated 07-30; issues 03–07 fixed 08-02), so the number
belongs to a buggy search that no longer exists — notably issue 06
(PVNet-only priors zero) contradicts the sweep's "PVNet priors guide PUCT"
claim for the α=0 point. If PVNet is ever candidate for default, first
re-derive what made the headline on post-fix code with recorded provenance.

## Closed by

*Fixed in the 2026-08-02 working tree. No change; remains open (headline
falsified as recorded; root-cause of the original number unknown).*
