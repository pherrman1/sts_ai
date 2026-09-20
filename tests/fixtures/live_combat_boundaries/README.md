# Live combat boundary regression evidence

These are integration fixtures and raw driver traces, not a gameplay-quality
experiment. Gzip files preserve the original bytes; uncompressed SHA-256 values
and deployed component hashes are recorded in [manifest.json](manifest.json).

- `fresh-a0.jsonl.gz`: the original 351-action trace, ending at the floor-22
  unknown hand selector. Its summary reports an integration error.
- `fresh-a0.jsonl.failure.json.gz`: the corresponding complete failure packet.
  `test_live_game_driver.py` uses its actual MCP screen as a regression fixture,
  including `can_pick_zero=true`. The EventRoom variant changes only room type;
  it is a synthetic regression, not evidence of a live event fight.
- `review-continuation.jsonl.gz`: continuation after deploying the corrected
  advisor and inspector. The original floor-22 selector had already been
  completed before this continuation. The save resumed at floor-22 rewards.
  At floor 24, action 13 uses Gambler's Brew; actions 14–16 encounter
  `HAND_SELECT`, retain `inspector_boundary=combat`, and receive Silver
  `UNSUPPORTED` with `silver_unmapped_selection_task`. Deterministic fallback
  selects two cards and confirms. Action 16's post-state returns to normal
  combat and actions 17–29 continue beyond the selection. All three selection
  observations have distinct sequence/hash identities in the same session.
  The 30-action continuation ends in normal death at floor 24, with zero
  mapping failures. All actions use explicit unsupported fallback (20 combat,
  10 OOC); this trace does not establish Silver or V4 gameplay quality.

The continuation reproduces the original *failure class*, not the exact
floor-22 combat. Event combat classification and exact `canPickZero` projection
are covered by Java, native importer, protocol, and driver regressions; a live
EventRoom fight was not reproduced. The full inspector snapshots are not
embedded in the continuation trace; the trace records the correlated evaluator
and MCP post-state, with large full-game payloads represented by size/hash.

Focused check output is retained in [review-focused-tests.log](review-focused-tests.log)
and [review-java-tests.log](review-java-tests.log). To inspect raw traces:

```sh
gzip -dc tests/fixtures/live_combat_boundaries/review-continuation.jsonl.gz
gzip -dc tests/fixtures/live_combat_boundaries/fresh-a0.jsonl.failure.json.gz
```
