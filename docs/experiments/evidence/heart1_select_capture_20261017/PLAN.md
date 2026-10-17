# heart1 card-select capture and student C re-distillation (plan, 2026-10-17)

Status: proposed. The capture needs Philipp's authorization and a coordinator seed block; nothing here has run
beyond the smoke below. No § number taken. Capture seeds: 111156100–111156163 (coordinator block).
PR #597 (logits-only forward) also edits `priorLogits`; when it lands, the serving forward there becomes
`logitsOnly=true` (bit-identical logits) and the teacher keeps the full pass (value).

## Why

Student C (`studentc.bin` `eff2f74f…`), the A20 Heart stack's OOC tree prior and rollout policy, was distilled on
1,009,708 heart1-labelled tree nodes with **0 CARD_SELECT rows**, keys off, acts 1–3 only
(audit-2026-10-17 `heart1-distill.md`, findings 1–2). Philipp, 2026-10-17 16:10Z: "okay we definitely want to
distill the card_select thing".

## Capture

- Hook: `STS_OOC_HEART1_CAPTURE` in `heart1::priorLogits` (`apps/one_combat/heart1_policy.cpp`). Node rows every
  `_EVERY`-th prior call; select rows for each card select (UPGRADE, REMOVE, TRANSFORM, TRANSFORM_UPGRADE,
  DUPLICATE, OBTAIN) that a rest, shop-removal, event or boss-relic source opens on a state copy, every
  `_SELECT_EVERY`-th. The tree reaches those selects only as compound candidates, so the old capture never saw
  them. Labels: heart1 (`STS_OOC_HEART1_TEACHER=heart1.bin`, `1e92f2a6…`); `serve` = student C's logits.
- Environment (`arm_env.sh`, mode `cap`): the §504 control arm C copied literally, i.e. the current A20 Heart
  stack: keys collected, no act stop (Act 4 included), student C tree prior and rollout policy, 512 sims.
  **Keys and Act 4 are included** because student C is used on exactly these states today and its agreement
  with heart1 there falls to 61–73% (audit finding 2), and because heart1 itself was trained with keys and Act 4,
  so its labels there are in distribution. The old keys-off rows stay in the training set.
- States come from student-C trees and student-C rollouts (the old capture used V4-prior trees), i.e. the states
  the new student will serve.
- Rows also carry `act` and `deck_misc` (card `misc` in deck order), so the queued student C input change
  (relic counters, act, Ritual Dagger damage) can train on the same capture.

## Smoke (seeds 111156000–111156003, this container, binary of the first commit)

- Parity: seed 111156000 with and without capture: identical MCTS summary row (94 OOC decisions, 20,346 sims,
  14,116 prior builds, …; only wall/CPU columns differ) and identical result (floor 51). The capture is observation
  only.
- Cost at `_EVERY=8`, `_SELECT_EVERY=1`: 379 s → 2,034 s for 111156000 (5.4x); about 35 ms per written row
  (heart1 forward). Rows per run: 52,935 / 41,396 / 68,977 (111156002 reached Act 4), about 55% select rows.
- Student C vs heart1 top-1 on these rows (seeds 111156000/001): REMOVE 0/10,976 and 13/12,055; TRANSFORM
  0/864 and 3/612; TRANSFORM_UPGRADE 0/894 and 1/334; UPGRADE 21% and 42%; DUPLICATE 75–90%; OBTAIN 74–75%.
  Node rows: 85–98% by screen (shop lowest).

## Proposed run (needs authorization)

- 64 A20 seeds 111156100–111156163, 8 cloud workers x 8 seeds, 4 units at a time, `_EVERY=16`,
  `_SELECT_EVERY=4`. A check on the final binary at these rates (seed 111156003, stopped after Act 1): 9,021 rows
  (5,199 node, 3,822 select), 382 s, rc=0, `deck_misc` present. **Inference**: 20–30k rows and ~20–25 min per
  full run, about 1.3–1.8M rows, ~25 core-h, ~1–1.5 h wall, ~0.4 GB gzipped on the share (`heart1-select-capture/`).
- Units: `run_unit.sh` (4 h timeout); worker lifecycle `worker.sh setup|run|status W`. Freeze `CODE_COMMIT` and
  `binary.sha256` before launch.

## Training (Philipp's 3060 Ti, via the coordinator)

- `tools/heart1/distill.py` with student C's recipe (`--dim 64 --layers 2 --mult 2 --heads 4 --trim-map --amp`),
  `--init` from student C's state dict, on the old capture (1.01M rows) plus the new one, held-out seeds
  `seed % 8 == 7`. Export with `tools/heart1/export_heart1_weights.py --allow-other-checkpoint --n-heads 4 --trim-map`.
- Offline gate on held-out seeds of the new capture, against student C on the same rows: REMOVE, TRANSFORM and
  UPGRADE top-1 vs heart1 (now 0%, 0%, 21–42%); node-row top-1 by act and key state; and no more than 1 pp
  top-1 loss on the old held-out capture rows (93.0%).
- The new student is a new artifact and defaults off: it replaces `studentc.bin` only by an explicit
  `STS_OOC_HEART1` path, and #591's non-UPGRADE card-select exclusion stays until Philipp decides.
