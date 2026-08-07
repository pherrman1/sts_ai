# 2026-08-07 — Prior-guided S3 rollouts (STS_S3_ROLLOUT_POLICY): implemented opt-in, smoke fires, gate pending

Date: 2026-08-07
Session/task: User question "could we use the prior belief instead of true
random rollout?" — answered by implementing policy-prior-guided rollouts in
Searcher3 behind an env flag (default off).

## Decision

- `STS_S3_ROLLOUT_POLICY=1`: `BattleScumSearcher3::playoutRandom` samples
  rollout actions from the **GBM policy prior** (`computeEdgePriors`, the
  same distribution PUCT priors use) instead of the static `rolloutWeight`
  heuristic. Default off; the heuristic branch is untouched (unset =
  byte-identical). Restricted to the GBM policy net — a PVNet policy-head
  forward per rollout step would cost ~14-18× a sim.
- This revives the parked §119 "Phase 3 (policy-guided rollouts)" line, with
  the §126 vnet context: the rollout outcome now carries 70% of the leaf
  blend (α=0.3), so rollout quality matters more than pre-vnet.
- Pre-registered gate (pending, GCP): paired 256-seed @1k/64p on the §126
  config vs `build/vnet_all_a03_1k.csv` (50.4%); then @3k if positive. Null
  or negative closes the line.

## Rationale

- **Inference:** the current rollout is NOT truly random — it is weighted by
  a static hand-authored bias (ATTACK=8, POWER=3, others=2, END_TURN/
  POTION=1). Replacing that bias with the learned GBM prior (which §103
  showed ties the PVNet policy head at 8× lower cost) is the cheapest
  high-value rollout upgrade available; the tree already computes the same
  prior at every expansion.
- Restricting to the GBM net mirrors §103's verdict and keeps the per-rollout
  cost dominated by tree evals (~µs each) rather than transformer forwards.
- Known risk (pre-registered): prior-guided rollouts can collapse rollout
  diversity, making Q estimates self-consistent but overconfident; the
  heuristic mix (temperature) is the obvious follow-up knob if the pure-prior
  version loses.

## Alternatives considered

- Mix prior + heuristic weights (e.g., α-blend) — deferred: keep the first
  version pure (one knob, clean signal); the mixture is a natural follow-up
  if the pure-prior gate collapses.
- Apply to Searcher2 too — deferred: the vnet default (the line this serves)
  is fair-S3; S2's `playoutRandom` has the same structure if the S3 gate
  turns positive.
- Use the PVNet policy head for rollouts — rejected: per-step transformer
  forwards destroy the per-sim cost budget (§102 14-18×).

## Evidence

- Local smoke (8 seeds @300 sims, §126 default stack): control 12.5% win /
  38.2 floor / 7.5 cpu-s·run vs policy-rollout 25.0% / 44.0 / 18.2 — behavior
  fires on most seeds (won differs seed 6), banner prints; 8-seed win deltas
  are noise, 2.4× cpu is real (per-step GBM evals). `ctest` 5/5.
- Artifacts: `build/pri0_{ctl,pol}.csv` + logs. Code:
  `BattleScumSearcher3::playoutRandom`, `apps/one_combat.cpp` env parse.

## Status and follow-up

- Gate pending on GCP (§124b in EXPERIMENTS.md). If positive: consider the
  α-mix knob, an S2 port, and updating `current-baselines.md` only on a
  headline change.

## Verdict (2026-08-07, gate §124c — appended, supersedes "gate pending")

- **Falsified, line closed.** Paired 256-seed gate @1k/64p (full V4 stack,
  block 126700, vnet α=0.3 default): policy-prior rollouts **43.4% vs 50.4%
  control = −7.0pp (95% CI [−13.7, −0.4])**, floor −1.3 (CI [−2.6, 0.0]),
  HP −6.7, at 2.7× cpu (83.8 vs 30.5 cpu-s/run). Discordance 30%
  (control-only 47, policy-only 29). The control arm reproduced the §126
  reference exactly (129/256 = 50.4%), so the pairing is clean.
- The GBM policy prior (trained on older-policy visit distributions) actively
  hurts rollout play — the known diversity-collapse risk materialized (or
  worse: the prior is simply stale). No @3k re-gate (pre-registered: only if
  positive). Env stays opt-in, no default change.
- Follow-up only through the winrate-plan §3.4 prerequisite: retrain the
  policy prior on current-stack (vnet-era) data first, then optionally retest
  with a prior+heuristic mixture. Not pursued as a standalone line.
- Artifacts: `build/pri1_ctl_256.csv` (md5 4106e1de…), `build/pri1_pol_256.csv`
  (md5 4ef1416c…), logs on sts-test. EXPERIMENTS.md §124c.
