# 2026-08-07 — PVNet phase-6 gate re-check after §124-§126: gate NOT run, deferred to a phase-5-model revisit

Date: 2026-08-07
Session/task: Verify whether the phase-6 PVNet deployment-speed gate (planned
in `docs/archive/research/plans/plan-value-targets-2026-08-07.md` §"phase 6") is still
worth running, after the winrate wave §124-§126 landed in commit 3f04e82.

## Decision

- **Do not run the paired 256-seed gate for the phase-6 PVNet knobs now.**
  Defer it to a phase-5 (value-only utility-target model) revisit.
- The phase-6 implementation itself stays committed unchanged
  (`STS_PVNET_COND_{TURN,DEPTH,BOSS}`, `STS_PVNET_CACHE` default ON); the cache
  is behavior-preserving and was verified identical cache-on/off, so no
  correctness gate is owed.
- §124a's "gate pending on the §124 baseline (not yet recorded)" note is
  superseded: the §124 references exist (`b2c_1k_64p.csv` 37.9%,
  `b4_3k_64p.csv` 42.6%) but the config they pair against is no longer the
  default leaf configuration.

## Rationale (verified against HEAD 3f04e82)

- §126 promoted the fresh honest-data V_combat GBM leaf to default ON in the
  fair-S3 path (α=0.3; three significant gates +12.5/+12.1/+12.5pp at
  ~2-2.4× cpu). The S3 per-expansion blend site is
  `if (VNet) … else if (PVNet && pvnetCondAllowed) …`
  (`BattleScumSearcher3.cpp:354-360`), so with the vnet default the PVNet leaf
  — and therefore the phase-6 knobs — never fires in the default stack.
  Gating it now would measure an off-default config (`STS_VNET` disabled +
  `STS_PVNET` loaded), with no default-promotion path.
- §126's own conditioning test weakens the phase-6 COND_* premise: vnet
  cond-boss at α=0.3/0.5 is flat (+0.8/+0.4pp, ~13-15% discordance) — "the
  value is spread across all rollout-heavy contexts, not just bosses"
  (EXPERIMENTS.md §126). The boss-conditioning idea that motivated
  `STS_PVNET_COND_BOSS` (from winrate-plan §4.3) is empirically dead for this
  wave.
- The §4.3 pre-registered rule ("null at both budgets closes the leaf line")
  is effectively consumed by §126's answer: the GBM leaf wins the leaf-evaluator
  question; the NN (PVNet) leaf channel stays closed (§102). The phase-6 knobs
  only become relevant if the phase-5 model (better targets, value-only) makes
  the NN leaf competitive again — that is the gate worth running then, paired
  against the §126 vnet default (`build/vnet_all_a03_1k.csv`, 50.4% @1k/64p).

## Alternatives considered

- Run the gate anyway vs the §124 rollout-only references — rejected: a
  positive PVNet-gated result would still lose to the vnet default on win and
  cpu (14-18× per-call leaf cost, §102); a null would consume GCP hours to
  confirm a closed line.
- Gate PVNet leaf vs vnet leaf at fixed compute — rejected: the blend site is
  mutually exclusive (else-if), so this is a new design (blend order/α
  interplay) beyond a phase-6 gate, and §102's fixed-compute verdict already
  covers the unfavorable direction.
- Flip the COND_* defaults off/remove them — rejected: they are opt-in,
  zero-cost when unset, and are the natural speed story for the phase-5
  revisit.

## Evidence

- HEAD 3f04e82 (winrate wave §124-§126): `BattleScumSearcher3.cpp:354-360`
  (VNet-first blend site), `:627-657` (evaluateLeaf PVNet-first), §126 gates
  and vnet cond-boss arms in `EXPERIMENTS.md`, `current-baselines.md`
  (vnet default, 50.4% @1k/64p / 55.1% @3k/64p headline).
- §124a smoke (`build/pv6_*.csv`), unchanged.

## Status and follow-up

- Plan file updated (`plan-value-targets-2026-08-07.md` phase 6: gate
  re-evaluated, deferred).
- Follow-up: when phase 5 (value-only utility-distribution model) lands, gate
  it + the phase-6 knobs vs `build/vnet_all_a03_1k.csv` at the §124-§126
  config; pre-registered rule stays "null at both budgets closes the leaf
  line".
