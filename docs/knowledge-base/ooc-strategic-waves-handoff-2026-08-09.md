# OOC strategic investigation handoff — Waves 0A–0I

Date: 2026-08-09  
Purpose: give the next coding/research model a compact, evidence-backed state
of the corrected honest V4 investigation.

## Executive status

The main benchmark blocker was fixed. `search::g_potionKeepValue` was process
global even though `runFullRunOOC` recalculates it per fight while seeds run in
parallel. It is now `thread_local` in:

- `include/sim/search/BattleScumSearcher2.h`
- `src/sim/search/BattleScumSearcher2.cpp`

Repeated identical 8-seed runs then matched all `won`, `floor`, `act`, `hpEnd`,
and death fields. The corrected V4 was requalified on the frozen S3 + 7k-VNet
Act-3 stack: **31/64 (48.4%) ON vs 24/64 (37.5%) OFF, +10.9pp**, paired 95% CI
`[-1.6,+23.4]`pp. The result is positive but not individually significant;
128-seed confirmation remains required before promotion.

Do not use the earlier negative result as evidence against V4. It was generated
before the race fix and is recorded as invalid/inconclusive in `EXPERIMENTS.md`
§155.

## Frozen gameplay configuration

Unless explicitly stated otherwise:

```text
A0
STS_FAIR=1
STS_SEARCHER3=1
STS_S3_BELIEF=0
STS_S3_CHAIN=0
STS_S3_LIVE_VALID=1
STS_S3_PARTICLES=64
STS_VNET=build/v_combat_7k_tuned.txt
STS_VNET_ALPHA=0.3
STS_COLLECT_KEYS=0              # Act-3 objective
STS_STOP_AFTER_ACT=3
1,000 sims/decision
12 OpenMP threads
paired seeds 126700–126763
```

Models:

- corrected honest V4: `selfplay/models/ooc_strategic_tok_final.native`
- V4 SHA256: `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`
- VNet SHA256: `ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c`

The eight forbidden hidden features remain excluded:
`nextEliteId`, `nextFight0`, `nextFight1`, `nextFight2`, `remElites`,
`remFights`, `monOffset`, `eliteOffset`.

## Wave results

| Wave | Status | Result/evidence |
|---|---|---|
| **0A correctness/contract** | Complete | Python/C++ V4 contract/parity infrastructure, honest feature checks, action/candidate checks, and counterfactual map-detach fixes. Self-tests pass. |
| **0B seed-disjoint validation** | Fixed/complete | Trainers split complete seeds with empty train/validation intersection. A bug was found: group offsets assumed CSV rows were contiguous. Both trainers now sort by `(seed, decIdx)` first. Missing batch RNG initialization was also fixed. |
| **0C provenance** | Complete | `bestbench` writes `<results>.meta.json` with objective, seed block, flags, model-load state, and settings. |
| **0D deployment metrics** | Partial/implemented | `strategic_metrics.py` and `tools/analyze_strategic_metrics.py` implement gate-fire curves, override quality, fallback-relative advantage, and regret. Synthetic self-test passes. A real checkpoint prediction-CSV pipeline is not yet connected end-to-end. |
| **0E corrected V4 gate** | Requalified | ON 48.4% vs OFF 37.5%, +10.9pp, CI crosses zero. Artifacts: `build/ooc_v4_requal_s3_act3_off_64_1786292238.csv`, `...on...csv`, paired report and sidecars. |
| **0F override tracing** | Complete | `STS_OOC_STRATEGIC_TRACE` and analyzer work. Requalified ON trace: 3,419 opportunities, 1,834 owned, 53.6% overall fire rate. |
| **0G screen ablations** | Complete exploratory gate | Relative to full V4 48.4%: minus REST 48.4% (0.0pp), minus EVENT 40.6% (−7.8pp), minus SHOP 53.1% (+4.7pp), minus TREASURE 48.4% (0.0pp), minus BOSS RELIC 45.3% (−3.1pp). All 64-seed CIs are wide; only EVENT has a meaningful directional signal. Artifacts: `build/ooc_v4_requal_s3_act3_ablate_64_1786292838/`. |
| **0H margin sweep** | Complete exploratory gate | Margin 0.5: 45.3%; 1.0: 48.4%; 2.0: 48.4%; 5.0: 45.3%. Mean floors: 43.9, 43.5, 44.4, 43.0. Eight-seed trace fire-rate samples: 71.8%, 53.3%, 33.3%, 13.5%. Margin 1–2 is a small-sample plateau; no promotion yet. |
| **0I checkpoint selection** | Interface complete, experiment incomplete | Both trainers support `STRAT_SELECT_METRIC=val_pol_ce` (minimize, default) or `q_top1` (maximize). A three-epoch CUDA `val_pol_ce` run on the full 3.06M-row Tier-B dataset reached `val_pol_ce=0.6093`, `q_top1=0.2982`. The paired `q_top1` full run was stopped before training after resource pressure. No checkpoint-selection conclusion is valid. |

## Important artifacts and logs

- Plan: `docs/knowledge-base/plan-ooc-strategic-investigation-2026-08-09.md`
- Chronology: `EXPERIMENTS.md` §§155–162
- Metrics: `strategic_metrics.py`, `tools/analyze_strategic_metrics.py`
- Trace: `tools/analyze_strategic_trace.py`
- Ablation harness: `run_screen_ablate.sh`
- Requalified gate CSVs: `build/ooc_v4_requal_s3_act3_*_64_1786292238.csv`
- Requalified ablations: `build/ooc_v4_requal_s3_act3_ablate_64_1786292838/`
- Margin CSVs: `build/ooc_v4_margin_*_s3_act3_64_1786293919.csv`
- Determinism documentation: `docs/knowledge-base/behavior/determinism-and-rng.md`
- Race decision: `docs/knowledge-base/decision-log/2026-08-09-thread-local-potion-value.md`
- Split fix decision: `docs/knowledge-base/decision-log/2026-08-09-strategic-training-split-fix.md`

## What not to conclude

- The earlier S2-fair V4 result (+15.6pp) is promising but does not prove
  current S3 transfer.
- The pre-race S3 result (−23.4pp) is invalidated.
- 64-seed Wave 0E/0G/0H outcomes are exploratory, not deployment promotions.
- Runtime traces alone cannot measure harmful overrides because they contain no
  counterfactual labels. Use the Wave 0D prediction-CSV schema for that.
- Do not compare `STS_COLLECT_KEYS=0` Act-3 results with Heart/key-collection
  results. No fresh Heart gate has been run in this pass.
- Do not start Wave 1 fallback-relative labels or Wave 2 hidden-future
  marginalization until Wave 0I and the 128-seed V4 confirmation are complete.

## Resource/process safety

A full Tier-B token trainer materializes roughly 2.9 GB of state before model
memory and can overwhelm an IDE or cause excessive swap/output. The previous
IDE crash occurred during the attempted paired full-dataset checkpoint runs;
exact OS crash causality is unverified. Future training should:

1. use redirected logs, not an IDE console;
2. use a reduced Tier-B fixture first for `val_pol_ce` vs `q_top1` logic;
3. avoid concurrent CUDA trainers;
4. check `nvidia-smi` and `free -h` before launching;
5. retain `STRAT_EPOCHS` small for smoke tests;
6. never delete unrelated self-play buffers or model artifacts.

There may be other Pi workers running benchmark/search experiments. Do not kill
or broadly terminate them. Do not launch another large gameplay or training job
until the machine is clear enough to avoid CPU/GPU/RAM contention.

## Next exact actions

1. Run a tiny redirected trainer fixture using both selection metrics and verify
   the selected epoch differs/behaves as expected; do not use the 3.06M-row
   dataset for this test.
2. When no competing worker is using the machine, run the **128-seed** paired
   Wave 0E confirmation on the frozen stack. Keep `STS_COLLECT_KEYS=0` and
   `STS_STOP_AFTER_ACT=3` explicit.
3. If the 128-seed result confirms a positive effect, record it and consider
   the current V4/margin-1 stack provisional. If not, keep it diagnostic.
4. Only then decide whether to run a separate `STS_COLLECT_KEYS=1` Heart gate.
5. Use Wave 0D metrics and checkpoint outputs before any label redesign.

## Verification commands

Cheap checks:

```bash
git diff --check
python3 -m py_compile train_strategic.py train_strategic_tok.py strategic_metrics.py tools/analyze_strategic_metrics.py
python3 tools/analyze_strategic_metrics.py --self-test
python3 tools/strategic_split_selftest.py
python3 tools/ooc_strategic_contract_selftest.py
```

For gameplay, use the frozen environment above and a unique results path. The
automated seed ceiling is 128; prefer 8–16 for smoke checks and 64 for ordinary
focused gates.
