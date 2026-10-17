# §511 Heart leaf v1 (issue #605): offline gate on §503 VALIDATION

**Verdict: GATE_FAIL (act-3 calibration), research-only.** Pre-registered in `PREREG.md`
(plus the v2-feature amendment) before the full fit.

## Setup

- Code `d6cf4b8` (features v2) / `a7891dd` (heart1 value export); tail binary sha256
  `e976634c…3c88`, environment `tail_env.sh` (§503 producer stack: student C prior and
  rollout policy, rollout3, `LEAF_VALUE=native`, keys on, 512 sims; no traces).
- Rows: every §503 TRAIN (1,088 runs, 148 Heart kills) and VALIDATION (320 runs, 33) MAP root
  with a native snapshot: 27,114 roots (55% of MAP roots; Act 4 is thin, 78 VALIDATION roots).
  CONFIRM and §497 TEST were not opened.
- Tails: `heartleaftail 111159000 16`, 16 live-configured rollout3 continuations per root,
  372,489 non-terminal ends. Data on the share: `heart-leaf-td/v2/` (`SHA256SUMS`).
- Fit: `tools/heart_leaf_fit.py fit` (w = 0.5, 3 TD rounds, XGBoost depth 5, eta 0.03, early
  stop on VALIDATION). Round 1 had the lowest VALIDATION BCE (rounds 2 and 3: 0.3076, 0.3086).
- Artifact: `models/candidates/heart_leaf_td1/heart_leaf.json` (sha256 `12530a98…`), 204-tree
  residual `6d7a06bd…`, slope 0.799, base −3.274. Native parity on 2,000 roots 2.8e-7.

## Gate (VALIDATION MAP roots, run-weighted)

| | BCE | AUC | Act 1 pred/actual | Act 2 | Act 3 | Act 4 (not gated) |
|---|---:|---:|---|---|---|---|
| public X2-B raw | 1.484 | 0.699 | 0.742 / 0.103 | 0.771 / 0.119 | 0.898 / 0.202 | 0.916 / 0.423 |
| X2-B, TRAIN Platt | 0.3133 | 0.699 | 0.086 / 0.103 | 0.129 / 0.119 | 0.292 / 0.202 | 0.344 / 0.423 |
| **Heart leaf td1** | **0.3065** | **0.724** | 0.085 / 0.103 | 0.132 / 0.119 | **0.240 / 0.202** | 0.592 / 0.423 |

Per-act AUC (leaf vs Platt X2-B): 0.575 vs 0.556, 0.707 vs 0.675, 0.718 vs 0.679, Act 4 0.707 vs 0.646.

1. BCE lower than Platt X2-B: PASS (0.3065 vs 0.3133).
2. |mean − actual| ≤ 0.03 in acts 1-3: 0.018, 0.013 PASS; **act 3 0.038 FAIL** (X2-B Platt: 0.090).
3. AUC not lower by more than 0.01: PASS (+0.025).

173 VALIDATION runs reached Act 3, so the act-3 rate has a standard error of about 0.03; the miss
is about 1.3 SE. It still fails the rule as written.

Gain shares of the added columns are small: x2bMargin 1.6%, HP fraction 0.2%, key inputs ≤ 0.1%,
Dagger/Searing 0 (no Dagger in the data; Searing Blow rare). Top splits: relic 15, act, floor,
relic 73. **Inference:** the §503 runs give the key inputs little variation to learn from
(Sapphire is almost always taken in Act 1); the #611 key-flag runs are the planned source.

Smoke (not strength): one A20 Act-1 unit, seed 111159001, `bestbench 10000 1 20`,
`STS_OOC_MCTS_LEAF_HEART_MODEL=…/heart_leaf.json`: model loaded, rc 0, 34/35 decisions
MCTS-owned, 0 unsupported combats, Act 1 cleared, 104 s.

## heart1's value head on the same roots (Philipp's question, descriptive)

`heart1_critic.py` on `h1rows.jsonl` (heart1.bin `1e92f2a6`), TRAIN Platt fits, VALIDATION:

| Act | X2-B AUC | heart1 critic AUC | X2-B + heart1 |
|---|---:|---:|---:|
| 1 | 0.556 | 0.601 | 0.586 |
| 2 | 0.675 | 0.736 | 0.724 |
| 3 | 0.679 | 0.778 | 0.740 |
| 4 | 0.646 | 0.741 | 0.698 |
| pooled | 0.699 | 0.531 | 0.708 |

heart1's critic ranks states within an act better than X2-B and the new leaf, but its level
hardly moves between acts (Platt mean 0.113 in Act 3 vs actual 0.202), so pooled it ranks worst.
**Inference:** a distilled heart1-critic input could add within-act signal to the tree leaf.
