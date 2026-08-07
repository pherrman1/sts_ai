# 2026-08-07 — Winrate-plan §3.4+§3.5 merged pipeline: fairgen datagen launched on GCP with the new 22-feature producer

Date: 2026-08-07
Session/task: User asked which plan is active and whether §3.4 should run
(another agent is collecting combatgen data for a better vnet). Answer:
winrate plan executed through Wave 2; §3.4 is the last Wave-1 item and the
prerequisite for any prior-quality line. Launched §3.4 and merged §3.5 into
one datagen/retrain/gate pipeline.

## Decision

- **§3.4 datagen running on GCP sts-test** (started 2026-08-07, ~50 min):
  `fairgen 1000 1000 0 0.3 build/fair34_{v,p,o}.csv 400000` with
  `STS_LIVE_VALID=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64
  STS_VNET=build/v_combat_honest.txt STS_VNET_ALPHA=0.3`.
- **Recorded deviation from the plan as written:** explicit `STS_VNET` +
  `STS_VNET_ALPHA=0.3`. The plan (§3.4) predates the §126 vnet promotion and
  only demands `STS_LIVE_VALID=1`; but §126's own stance is to align datagen
  with the deployed controller (which now has the vnet leaf at α=0.3), and an
  explicit `STS_VNET` without the alpha would silently use the legacy α=0.5.
  The deviation is documented in the plan file and this entry.
- **§3.5 merged into 3.4's pipeline (no second datagen):** implemented the 8
  subset-content action features now, before the datagen rows freeze.
- No conflict with the vnet agent: their combatgen (value rows) runs locally;
  fairgen (policy rows) is a different producer on the idle GCP box.

## Implementation (§3.5)

- `src/sim/search/CombatValueNet.cpp`: `kActionNames` extended with
  `aSelectSize, aSelTotalCost, aSelAtk, aSelSkl, aSelPow, aSelUpgraded,
  aSelPlayOrder, aSelObtainWeight` (`kNumAction` 14→22, derived); filled in
  `combatFillActionFeatures` for SINGLE/MULTI_CARD_SELECT — multi indices
  resolve against the hand (GAMBLE/EXHAUST_MANY), single indices against
  hand/discard/exhaust pools per `CardSelectTask`, discovery/codex contribute
  size only. Appended AFTER the original 14 so the PVNet action encoder
  (reads the first 14) and old GBM models (model-nfeat based) are unaffected.
- Backward-compat fixes required by the width change: S2/S3
  `computeEdgePriors` PVNet branches hardcoded the stride `n*14` — with 22
  features this would have mis-filled the action buffer (overlap) — now
  stride by `combatPolicyFeatureCount() - combatFeatureCount()`; the
  `policystats` mode's 14-slot `act` array was a write-overflow risk — now
  `actionN`-sized; `eval_combat_pvnet.py` / `combat_pvnet_parity.py` assert
  exactly-14 action columns — now slice the first 14.
- Verified: local 1-seed fairgen smoke emits 1793-col policy rows
  (1766+22+5); GAMBLE/EXHAUST_MANY rows show distinct subset combos (6/8
  distinct in the smoke — previously all identical).

## Rationale

- §124c (prior-guided rollouts, −7.0pp) showed the tracked prior is stale;
  §3.4's retrained prior is the prerequisite for any prior-quality line, and
  §3.5 rides the same rows. One datagen + one retrain + one gate covers both
  plan items.
- Sequencing mattered: changing the producer after the datagen would have
  forced a second datagen (~50 min wasted); the restart cost was ~7 min.

## Alternatives considered

- Run §3.4 exactly as written (no vnet in fairgen) — rejected: the policy
  rows would reflect the pre-vnet controller and the §126 alignment stance
  argues for matching deployment.
- Two separate datagens (§3.4 then §3.5) — rejected: one merged pipeline is
  the plan's own intent ("rides 3.4's pipeline").
- Gate the new features behind an env — rejected: the features are additive
  and the old model path is unaffected; a knob would only risk drift between
  datagen and deployment.

## Evidence

- Local smoke: `fairgen 1 100` → `/tmp/t35_{v,p,o}.csv` — 22 action cols,
  distinct subset features on select rows. `ctest` 5/5.
- GCP: `build/fair34_p.csv` header = 1793 cols with `aSelectSize` present;
  log shows `[V_combat leaf value ON: ... alpha 0.3]`; pid confirmed running
  (1000 seeds, seedOffset 400000).

## Status and follow-up

- When the datagen finishes: `train_policy.py build/fair34_p.csv` → export v2
  prior → offline `policystats` vs tracked → paired 256-seed gate at B2
  config (v2 vs `build/policy_trees_c.txt`). Pre-registered: a null closes
  the prior-v2 line.

## Verdict (2026-08-07, gate §127 — appended, supersedes "gate pending")

- **Null — line closed per the pre-registered rule.** Paired 256-seed @1k/64p
  (block 126700, full V4 stack + vnet default): v2 prior **48.4% vs tracked
  50.4% = −2.0pp (95% CI [−8.2,+4.3])**, floor −1.5 (CI [−2.9,−0.1]), HP
  −4.2, cpu equal (73.8 vs 75.7 s/run); discordant 71/256 (tracked-only 38,
  v2-only 33). Control reproduced the §126 reference exactly (129/256).
- Offline the v2 is better (CE/KL −0.09 on the new rows after fixing a
  pre-existing policystats action-feature bug), but the improvement does not
  transfer to the deployed PUCT stack — the same pattern as §124c
  (prior-guided rollouts). Both prior-quality lines now closed; the tracked
  prior stays deployed. v2 artifact kept:
  `build/policy_trees_c_v2.txt` (sha256 30ea8598…).
- The §3.5 multi-select features remain implemented and are part of future
  datagen (22-action-feature schema, backward-compatible) — the feature line
  itself was not the failure; prior calibration improvements were.

