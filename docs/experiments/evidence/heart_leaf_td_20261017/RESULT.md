# §515 Heart leaf (issue #605): offline gate on §503 VALIDATION, retrain and CONFIRM

**Verdict: td1 GATE_FAIL on VALIDATION (act-3 calibration); retrained td2 CONFIRM_FAIL
(act-1 calibration) although it beats Platt X2-B on CONFIRM BCE and AUC. Research-only, no
A/B.** The td2 section is at the end.

**td1:** Pre-registered in `PREREG.md`
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

## td2: retrain with a distilled heart1 critic, scored once on CONFIRM

Philipp chose "Retrain, then CONFIRM" (2026-10-17 18:13Z) and approved opening CONFIRM in the
thread (19:42Z). The candidate, the VALIDATION choices and the decision rule are in
`PREREG.md` amendment 2, written before CONFIRM was extracted. An independent review passed
the frozen commit `91bf3e28` and rehearsed the CONFIRM procedure on VALIDATION.

- Candidate `models/candidates/heart_leaf_td2/`: manifest `1b1ad13e…`, residual `c7a42e88…`
  (129 trees, TD round 2), critic `417769c0…` (600 trees, a regression of the heart1 value
  head on the v2 features; feature schema v3), Act-4 logit offset −0.713 from out-of-fold
  TRAIN. Native parity 2.1e-7 (`CompactTreeNet::marginFloat32` sums the critic like XGBoost).
- VALIDATION (used for the choices): BCE 0.3038 vs 0.3133, AUC 0.735 vs 0.699, act 3
  0.233/0.202 (gate FAIL by 0.001). `score_validation_td2.json`, `variants_td2.*`, `actcal_td2.*`.
- CONFIRM: all 32 §503 `SEALED-confirm` archives (640 runs, 83 Heart kills), `heartleaftail 0 0`
  on the `*.roots.jsonl` traces at `91bf3e28` gives 12,458 MAP roots with snapshots
  (`confirm_roots.jsonl` sha256 `fc12478e…`), then `heart_leaf_fit.py score --split confirm`
  (`score_confirm_td2.json`). One scoring; a first invocation pointed at the `*.trace.jsonl`
  files, which carry no roots, and stopped before any row was scored.

| CONFIRM (640 runs) | BCE | AUC | Act 1 pred/actual | Act 2 | Act 3 | Act 4 (not gated) |
|---|---:|---:|---|---|---|---|
| X2-B, TRAIN Platt | 0.3479 | 0.726 | 0.090 / 0.130 | 0.135 / 0.150 | 0.292 / 0.253 | 0.349 / 0.459 |
| **Heart leaf td2** | **0.3345** | **0.750** | **0.093 / 0.130** | 0.128 / 0.150 | 0.230 / 0.253 | 0.438 / 0.459 |

Per-act AUC (td2 vs Platt X2-B): 0.648 vs 0.614, 0.753 vs 0.705, 0.733 vs 0.704, Act 4 0.767 vs 0.750.

1. BCE lower than Platt X2-B: PASS. Paired run-bootstrap difference −0.0134 [−0.0189, −0.0073].
2. |mean − actual| ≤ 0.03 in acts 1-3: **act 1 0.037 FAIL** (run-bootstrap gap [−0.062, −0.012]);
   act 2 0.022 and act 3 0.023 PASS. Platt X2-B misses act 1 by 0.040 as well.
3. AUC not lower by more than 0.01: PASS (+0.024).

**Verdict: CONFIRM_FAIL**, so by the pre-registered rule no A/B runs on td2 and CONFIRM is spent.
The candidate ranks better than X2-B in every act and corrects the Act-4 level, but under-predicts
Act-1 Heart kills. **Inference:** this is systematic, not CONFIRM noise: TRAIN shows the same
under-prediction (0.093 vs 0.136 out of fold), while VALIDATION had a low Heart rate (0.103) and so
rejected the TRAIN act-1 offset (+0.45) in `actcal_td2`. A later candidate would need a new
held-out set to test that offset.

