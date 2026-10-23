# ADR-0057: The A20 rollout3 leaf speaks calibrated Heart probability (M0) by default

Date: 2026-10-23
Status: accepted

## Context

- **The level problem.** rollout3 ends a surviving rollout in raw X2-B, while a death scores 0 and a Heart kill 1.
  Stage 0 of the value-head plan (`docs/experiments/evidence/value_death_price_20261023/`) fit
  sigmoid(a_act + b · logit X2-B) to the Heart outcomes of current-stack A20 runs: a = (−2.5384, −2.9227, −3.6523,
  −3.6334), b = 1.0535. Relative to that calibrated value, raw X2-B over-prices a death 3.3× (act 1) to 7.7× (act 3).
- **The A/B.** The value-level 2×2 A/B (`docs/experiments/evidence/value_level_ab_20261023/`, 1,024 paired A20 seeds)
  found that the calibrated leaf (M0) kills the Heart more often:
  - main effect +2.15 pp [+0.10, +4.25], IMPROVED; M − A alone +1.37 pp [−1.17, +4.00];
  - deaths move from act 3 to acts 1–2, and Act-4 arrivals convert more often (57.1% → 60.7%).
- **The learned OOC stop.** It was trained on X2-B-scale roots and stays precise on M0's scale
  (`docs/experiments/evidence/value_m0_stop_check_20261023/`): its leader is the full search's choice at 99.76% of
  p ≥ 0.99 checkpoints, and none of its fast-root stops changed a pick.
- **The skipped confirmation.** The PREREG asked for a confirmation on fresh seeds before a default. A 2,048-seed A vs
  M confirmation would come out IMPROVED only about one time in three if the true gain is about 1.4 pp. On 2026-10-23
  at 14:11Z Philipp chose "Make M0 the default now" over "Confirm first (2,048 seeds)".

## Decision

- **Offline** (`configureLiveOocMcts`): with `STS_OOC_MCTS_LEAF_CALIBRATION` unset, the plain rollout3 X2-B leaf takes
  `a20LeafCalibration()` on states at ascension 20. The plain leaf means:
  - `STS_OOC_MCTS=1`, `STS_OOC_MCTS_LEAF_VALUE=native` and `STS_OOC_MCTS_LEAF_COMBATS=3`;
  - the process win model is the public X2-B that M0 was fit on: the file
    `models/candidates/v_win_x2b_public_trees.txt` (SHA256 `e2d3aa65…`, the pin `kHeartLeafAnchorSha256`). It is the
    OOC MCTS default (ADR-0029), whether loaded by default or named in `STS_WIN_NET`;
  - no other leaf model and no heart1 value head;
  - no leaf or sibling capture, and no leaf compare.
- **Banner and header.** The banner prints `leaf_calibration=-2.5384,-2.9227,-3.6523,-3.6334:1.0535
  leaf_calibration_min_ascension=20`; the config header carries `leafCalibration` and `leafCalibrationMinAscension`.
- **Live advisor** (`LiveOocMctsPolicy`): the research stack (the advisor default) does the same at ascension 20, when
  its leaves run rollout3 (qualified map history) and `STS_LIVE_OOC_WIN_MODEL` is that X2-B file (the release
  default). `searchModel.leafCalibration` reports it.
- **Rollback.** `STS_OOC_MCTS_LEAF_CALIBRATION=0` restores the raw anchor, offline and live.
- **Research use.** An explicit `a1,a2,a3,a4:b` stays the research option: it applies at every ascension with its own
  checks, offline only.
- **Unchanged leaves.** Other leaves keep the raw anchor:
  - the screen leaves, `direct`, and leaf counts other than 3;
  - live leaves that stop at the map checkpoint;
  - any other win model, such as B0 (`STS_WIN_NET=1`, or B0 as `STS_LIVE_OOC_WIN_MODEL`).
  Captures and the leaf compare keep it too, because their designs and recorded `x2b` anchors assume it.

## Consequences

- **Play changes** at A20 under OOC MCTS with the rollout3 leaf: offline runs, data generators on the production OOC
  stack, and live play. Below A20 nothing changes.
- **Older runs** reproduce with `STS_OOC_MCTS_LEAF_CALIBRATION=0`: gen 0–3, the value-level A/B's arms A and S, the
  stage 1–2 replay and the stop check. Freeze files must record the setting.
- **Not measured:**
  - the live advisor's 512-simulation search with M0;
  - the fresh-seed confirmation (skipped, Philipp's call).
  The gain's size is uncertain (about 0 to 4 pp). Part of it may come through PUCT's exploration scale rather than the
  death price.
- **Act 4.** M0 does not change act-4 decisions:
  - a rollout3 leaf from an act-4 root plays to the end of the game and ends in a death or a Heart kill (stage 1–2
    replay: identical picks at all 396 act-4 roots);
  - live leaves that stop at the map checkpoint keep the raw anchor.
- **Later candidates.** Stage-4 value candidates are tested against M0. A learned leaf value replaces the calibration;
  it does not stack on it.
