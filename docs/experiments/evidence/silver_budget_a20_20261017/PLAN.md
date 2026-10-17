# A20 Silver budget test: pre-registered plan (frozen with this folder)

Authorization: Philipp 2026-10-17 ("yes set up a20 silver budget test"; card "Add learned+prior";
16:32Z "maybe do 512 seeds then on 8 workers."). Code commit `CODE_COMMIT` (= main e413c1f, the merge of PR #603 head 685f7eb; review
PASS 2026-10-17, delta 17:21Z). No ledger § is claimed here; the result gets the next free § when it is recorded.

## Question
At A20, can Silver's learned stopping (ADR-0026 GBT `gbt-770201c31f7b`, threshold 0.0323, checkpoints
250..10k) replace the flat exact 10k Silver budget used by the research stack without losing play, and does
the gen-6 MLP prior (§476) on top change that?

## Arms (same binary, same seeds, paired; `arm_env.sh`)
| Arm | Silver settings |
| --- | --- |
| F (control) | `STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_LEARNED_STOP=0` (flat 10k) |
| L | as F with `STS_SILVER_LEARNED_STOP=1` |
| LP | L + `STS_SILVER_ROOT_PRIOR=g6_E STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_SILVER_TREE_PRIOR_MIN_VISITS=8` |

g6_E = `docs/experiments/evidence/silver_prior_arch_20261014/models/gen6/combat_policy_mlp_g6_E.txt`
(sha256 in `weights.txt`). Common: A20 (`bestbench 10000 1 20 SEED`), full runs to the Heart
(`STS_STOP_AFTER_ACT=0`, `STS_COLLECT_KEYS=1`), `STS_FAIR=1`, one thread per process.

**OOC policy** (Philipp's standing rule: OOC play comes from the heart1 distill, never V4 or heuristics):
every out-of-combat decision is made by student C `policyStep` (`STS_OOC_HEART1=studentc.bin`, sha256 in
`weights.txt`, no OOC MCTS). No `STS_OOC_STRATEGIC_*` variable is set, so no V4 net is loaded. Only the
key-collection rule runs before the student (`run_driver.cpp` order: heart_key, heart1, chain).
`STS_OOC_DECISION_TRACE` records the deciding policy per OOC decision; the report lists the counts per arm
and every decision not made by `heart1` or `heart_key`. Smoke (seeds 111135002, 111135004): 91 of 92 OOC
decisions by `heart1`, 1 by `heart_key`.

## Seeds and size
512 seeds, 111135100-111135611 (`SEEDS`), 8 workers (`NWORKERS`); worker W runs 111135100+64(W-1) .. +63
in all three arms, 4 units at a time. Unit timeout 2 h (rc 124).

## Endpoints and decision rules (`tools/analyze_silver_budget_a20.py`)
A seed counts only when all three arms finished with rc 0 and wrote its result row; dropped seeds are listed.
- **Primary:** reached Act 4 (`act >= 4` or `won`), paired by seed, L − F and LP − F, Newcombe (1998,
  method 10) 95% interval.
  - NON_INFERIOR when the lower bound > −5 pp.
  - LOSS_SHOWN when the upper bound < 0.
  - Otherwise NOT_SHOWN. A 3 pp reading is reported but is not the gate.
- **Secondary (descriptive):** Heart kills (same paired interval, exact McNemar p), mean floor, mean process
  CPU seconds per run (the cost lever), OOC decision counts per policy.
- LP vs L: descriptive only.

## Frozen-binary smoke (seed 111135002, not part of the test)
F floor 25, L floor 41, LP floor 29; CPU 26.2 / 22.4 / 16.5 s. OOC decisions: F 71 heart1 + 1 heart_key, L 114 + 3,
LP 85 + 2; none by the chain.

## Cost estimate (Inference from 2 smoke seeds)
Learned stopping ≈ 0.45–0.5x of flat CPU, LP ≈ 1.15x of L. ≈ 2 min CPU per seed for all three arms →
17–20 core-hours; per worker about 1–1.5 h wall plus a 4–9 min build.
