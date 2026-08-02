# 2026-08-02: Phase 5 round 2 — per-screen value heads, card gate neutral

## Decision

Replaced the single screen-blind value head of the Phase-5 strategic net with
one value head per screen (screens 1..8, shared state encoder), retrained on
the same 200-seed Tier-A dataset, and re-ran the identical one-ply card gate
at margins 1.0 and 5.0. Binary format bumped to `OOC_STRAT_V2`; the one-ply
caller now scores successor states with the head of the successor screen
(`OocStrategicNet::predictValue(state, screen)`). Also fixed the trainer's
CPU-bound data path (per-batch gathers over the 549MB state tensor → one
group-permuted gather per epoch, contiguous batch slices, batch 4096).

## Rationale

- **Inference:** the round-1 value head was screen-blind by construction (the
  `screen` column fed only the policy head), so V(s) was a regression pooled
  over an 8-screen distribution dominated 53/26% by REWARDS/MAP; one-ply card
  overrides regressed §70 (−10.9pp at margin 1.0).
- **Inference:** the §70 decision rule said: isolate the value-head structure
  first — it is the smallest change, and its output (per-screen held-out MAE)
  decides between Tier-B labels and a rest/shop gate next.

## Alternatives considered

- Gating rest/shop with the pooled head — rejected for round 2: repeating the
  card bet on an unmeasured hypothesis; the pooled head has no screen
  conditioning at all.
- Tier-B one-ply labels — deferred until per-screen MAE showed whether the
  value signal is usable anywhere (it is: REST/SHOP/TREASURE ≈ 0.6–1.0 MAE).

## Evidence

- Per-screen held-out value MAE: TREASURE 0.59, REST 0.73, SHOP 0.97,
  BOSS_RELIC 1.42, MAP 1.64, REWARDS 2.13, CARD_SELECT 2.63, EVENT 5.21
  (10·won+endHp scale; full table EXPERIMENTS.md §71).
- Paired fair 128-seed gate (1,000 sims, seeds 126700–126827): both margin 1.0
  and 5.0 → **21.1%/37.5/8.6, per-seed identical to baseline**. The card gate
  never overrides (successor margins below the gate under the MAP head).
- §70 comparison: pooled head −10.9pp (m=1) / −3.9pp (m=5); per-screen heads
  0.0pp at both.
- CPU/GPU during training: 350–400% CPU / ~35% GPU before the batching fix;
  127–154% CPU / up to 53% GPU after; 60 epochs finish in well under a minute.

## Facts/corrections

- `train_strategic.py` defaults to CUDA when available and prints `device:` at
  startup; CPU-only runs are opt-in via `STRAT_DEVICE=cpu`. AGENTS.md now
  records the training convention.
- The value-head parity assert needed 2e-4 tolerance (float32 accumulation
  across 8 heads; logit matches to ~8e-6).

## Status

Closed as a round. Card gate is now provably neutral (per-seed identical at
both margins). Next, per §71: (1) gate one-ply on REST/SHOP/TREASURE where the
per-screen heads are strong (0.6–1.0 MAE); (2) Tier-B labels specifically for
REWARDS/EVENT ranking if needed.
