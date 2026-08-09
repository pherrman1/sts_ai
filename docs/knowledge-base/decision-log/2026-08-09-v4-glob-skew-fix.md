# V4 token net trainer glob-block feature-order skew — fixed

Date: 2026-08-09

## Decision

Fix `train_strategic_tok.py` to build the 42-glob block from the correct
CSV columns. The deployed V4 model (`ooc_strategic_tok_final.native`) is
**not** replaced — it stays as the shipped artifact. The fix is a trainer
correctness change only; any future retrain must pass a paired gate before
deployment.

## What was wrong

`train_strategic_tok.py` built its 42-glob block by slicing CSV columns at
positions that assumed all 44 scalars were contiguous at state-block indices
0–43. The actual `strategicgen2` CSV interleaves the d/u/r/pot block (columns
32–1004) before the forward-map + map-position columns (1005–1016).

This caused a train/serve feature-order skew:

| glob slot | Trainer (old, wrong) | C++ inference (correct) |
|---|---|---|
| 24–35 | `d0..d11` (deck counts, CSV cols 32–43) | `fmDElite..curMapY` (forward-map + map position, CSV cols 1005–1016) |
| 40 (`canTakeEliteKey`) | derived from `d4` (CSV col 36) | derived from `fmCElite` (CSV col 1009) |
| 41 (`bossNear`) | derived from `d3` (CSV col 35) | derived from `fmDBoss` (CSV col 1008) |

## What was fixed

**`train_strategic_tok.py`** — glob construction (both passes):

- `glob[15:24]` → CSV cols 23:32 (pvShop..bottledPowId, 9 values — unchanged)
- `glob[24:34]` → CSV cols 1005:1015 (fmDElite..fmCTreasure, 10 values — was `d0..d10`)
- `glob[34:36]` → CSV cols 1015:1017 (curMapX, curMapY, 2 values — was `d10..d11`)
- Derived `canTakeEliteKey` → `fmCElite` from CSV col **1009** (was col 36 = `d4`)
- Derived `bossNear` → `fmDBoss` from CSV col **1008** (was col 35 = `d3`)

**Column-name assertions** added to fail training with a clear message if
`richHeader()` ever changes column order (rather than silently producing a
skewed model).

**Module docstring** fixed: 50→42 globals, 44→36 raw, 482→474 columns.

## C++ inference is unchanged

`buildTokState` (`apps/one_combat.cpp:3451`) has always had the correct
glob layout. The skew was purely in the Python trainer.

## Deployed model stays

The deployed `ooc_strategic_tok_final.native` (50-glob, leaky, trained with
this skew) stays as the shipped artifact. Its gate result (+20.3pp, §81) is the
known operating point. Past V4 retrains that changed feature representations
(§108 fixed-stats, honest-model gate) performed worse than the deployed model,
so the trainer fix is for correctness only; any future retrain with the fixed
trainer must pass a paired gate under S3−belief−chain before deployment.

## Rationale

**Inference**: the skew was discovered by code-reading the trainer's
positional slicing against the actual CSV column order produced by
`richHeader()`/`richRow()`. The gap between cols 31 (bottledPowId) and 1005
(fmDElite) is 973 columns — the entire d/u/r/pot block.

The deployed model works despite the skew because it was trained self-
consistently (the wrong columns were used for both train and export
normalization stats), and the C++ inference just happens to feed different
values into the same weight slots.

## Alternatives considered

- **Retrain and replace**: rejected — past V4 representation changes
  consistently underperformed the deployed artifact (offline→online inversion).
- **Change C++ to match the trainer**: rejected — the C++ layout is the
  intended one (forward-map features are semantically correct in those slots).
- **Do nothing**: rejected — the skew is a genuine correctness bug in the
  trainer that should be fixed so future retrains are trained on the right data.

## Evidence

- `train_strategic_tok.py` glob construction (lines 337–358 and 377–387)
- `apps/one_combat.cpp::buildTokState` (line 3451): C++ glob layout
- `apps/one_combat.cpp::richHeader`/`richRow` (lines 3320/3338): CSV column order
- `strategic_tok_net.py`: NGLOB=42, NRAW=36
- `docs/knowledge-base/decision-log/2026-08-09-v4-feature-leak-audit.md`: NGLOB=42 fix established

## Status

**Fixed** — trainer corrected, column-name assertions added, docs updated.

**Follow-up (same day):** Retrained with the fixed trainer →
`selfplay/models/ooc_strategic_tok_skewfix.native`. 64-seed paired gate
(S2 fair @1k, margin 1.0): **+15.6pp** (39.1% vs 23.4%, CI [+3.1,+28.1]),
floor +3.3, HP +5.1. First honest 42-glob V4 model to show a clear gate
benefit. Replaces `ooc_strategic_tok_final.native` as the shipped V4
artifact. See EXPERIMENTS.md §149.
