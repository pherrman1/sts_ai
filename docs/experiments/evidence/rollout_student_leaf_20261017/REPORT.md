# §494 rollout student as a native OOC MCTS leaf: port, parity and smoke

Date: 2026-10-17. Status: **port only, default off; no gameplay claim.**

## What changed

`STS_OOC_MCTS_LEAF_STUDENT=<weights.bin>` replaces the rollout3 leaf value of
non-terminal OOC MCTS leaves with the §494 rollout-target student
(`heart_rollout_distill` Net `attention`, selected fit `attention`, init 0,
epoch 3): the public heart1 leaf record (`heart1::buildPublicLeafRecord`) plus the
leaf's X2-B anchor predicts `sigmoid(net + logit(anchor))`. Leaves the record
builder or the encoder rejects fall back to the unchanged rollout. Requires
`STS_OOC_MCTS=1`, `STS_OOC_MCTS_LEAF_VALUE=native` and no leaf win model; refused
with the leaf/sibling capture modes and in the live advisor.

Weights are exported, not vendored:
`python3 tools/rollout_student_export.py export selected.pt vocabulary.json student494.bin`
(restricted unpickler, tensors only).

| File | SHA-256 |
|---|---|
| §494 `selected.pt` | `caa1d43bb2dd454d957295e5b2f7638cdd8693487d4457c39c6d0bbcc653c3ec` |
| §494 `vocabulary.json` | `0905ce8d25cef77b1dfbd29c16bbb49bcbab9cd947bf5dbece593e33261f9c41` |
| exported `student494.bin` | `653db96ef1de23cbb6498fa1673de525708cc68ab2edaeca56516ec60557f4d9` |
| heart1 prior `studentc.bin` | `eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509` |

Copies with `SHA256SUMS`: project share `rollout-student-494/`.

## Parity (no seeds)

- The float64 numpy reference (`rollout_student_export.py reference`) reproduces
  the §494 fit's selected VALIDATION metrics.
- `one_combat rolloutstudentscore` vs that reference on all 21,291 §494
  TRAIN+VALIDATION leaves (`corpus-train-validation.tar`): max |Δ| 2.2e-7,
  0 unsupported rows. About 3 ms/row including JSON I/O.

## Act-1 smoke (one fresh seed, 74072260, `STS_STOP_AFTER_ACT=1`)

Arm C environment (heart1 prior/leaf policy with `studentc.bin`, native leaf,
rollout3, 512 sims, cpuct 1.5, widen 4/0.75, depth 32, early stop, tree rules,
8 public futures, fair play, Silver exact), A20,
`tools/seed_guard.sh one_combat bestbench 10000 1 20 74072260 <csv>`:

| Arm | Act 1 | Floor | Wall s | OOC decisions | Sims | MCTS CPU s | CPU s/decision | Student leaves / fallbacks |
|---|---|---|---|---|---|---|---|---|
| student on | won | 16 | 65.8 | 38 | 10,656 | 40.2 | 1.06 | 10,654 / 0 |
| student off | lost (encounter 18, floor 16) | 16 | 143.2 | 35 | 9,975 | 124.8 | 3.56 | – |

The smoke shows the path runs end to end, every leaf is supported, and MCTS CPU per
decision drops about 3.4x at equal sims. One seed says nothing about strength.

## Next

The pre-registered A20 paired A/B is in [PLAN.md](PLAN.md). It has not run and
waits for Philipp's explicit authorization.
