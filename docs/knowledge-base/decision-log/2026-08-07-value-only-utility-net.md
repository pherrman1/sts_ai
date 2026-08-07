# 2026-08-07 — Phase 5 (value-only utility-distribution model) executed: fresh-data + direct-target leaf model ~4× better calibrated than the tracked PVNet offline; nothing deployed

Date: 2026-08-07
Session/task: Execute phase 5 of `docs/knowledge-base/plan-value-targets-2026-08-07.md`
(value-only model trained on the terminal-utility distribution target), per
user request. User also asked why this line modifies neither the PVNet nor
the VNet — answered: it is a third, offline research artifact.

## Decision

- Trained `build/v_combat_utility.txt` (native format `combat_utility_v1`):
  value-only 14-token encoder (D=128, 2 layers, 4 heads) + single 51-bin
  categorical head over R = 0 | 50+endHp, CE loss, on the fresh §127 datagen
  rows (`build/fair34_v.csv`, 225k, vnet-era controller). Held-out seed CE
  2.69 (12 epochs, GPU).
- **Nothing deployed changes**: the PVNet and VNet artifacts are untouched;
  no C++ integration in this phase. The transformer cannot be the runtime
  leaf (14-18× per call, §102; the vnet owns the leaf at α=0.3, §126).
- Deferred: shared-encoder variant (dual-CSV policy pass), C++ loader +
  `leafValue` for `combat_utility_v1` (only useful with a deployment gate),
  sibling-ranking eval (needs phase-2/3 data).

## Rationale

- Phase 5 answers the plan's research questions offline: does a direct
  terminal-utility target beat the win/death/quantile reconstruction, and
  (later) does policy sharing hurt value quality? The answers transfer to
  the deployable model: the vnet (GBM) retrain — the other agent's active
  line — can adopt the same fresh-data + direct-target recipe.
- The user's "why not the vnet?" is answered by ownership: improving the
  vnet = retraining the GBM, which is exactly the combatgen/retrain line in
  progress; this phase feeds that line evidence rather than competing with
  it.

## Evidence (30,000 identical held-out val rows of fair34_v.csv)

| metric | tracked PVNet | utility model |
|---|---:|---:|
| win Brier | 0.2505 | **0.0647** |
| win ECE | 0.3298 | **0.0688** |
| death BCE | 2.2076 | **0.2287** |

- Finding 1: the tracked PVNet miscalibrates badly on the new distribution
  (0.25 vs 0.107 Brier recorded on its own data) — the distribution-gap
  premise of the plan's phases 2-4.
- Finding 2: fresh data + direct utility target is ~4× Brier / ~5× ECE better
  on identical rows. Caveat: data and target changed together; a target-only
  ablation on shared data is a follow-up.
- Artifacts: `build/v_combat_utility.txt`, `build/eval_utility_fair34.json`,
  `build/eval_pvnet_fair34.json`, logs. Code: `train_combat_utility.py`,
  `eval_combat_utility.py`, `combat_pvnet_parity.py` (utility-format parse).

## Status and follow-up

- §128 recorded in EXPERIMENTS.md; plan file phase-5 status updated.
- Follow-ups (in priority order when they become relevant): (1) clean
  target-only ablation (same training rows, win/quantile heads vs 51-bin
  head); (2) shared-encoder variant; (3) fold the recipe into the vnet
  retrain line (distribution/utility targets in `train_value_combat.py`);
  (4) C++ loader only when a deployment gate exists.
