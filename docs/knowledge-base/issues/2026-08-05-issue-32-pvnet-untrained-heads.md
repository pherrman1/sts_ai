# Issue 32: PVNet turns/potion heads untrained but exported

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `train_combat_pvnet.py`

## Symptom

The PVNet `"turns"` head loss was a hard-coded constant 0.0
(`train_combat_pvnet.py::value_losses`, `lt = torch.tensor(0.0, ...)`) and the
`"potion"` head was trained only by a 0.01 shrinkage penalty toward zero — yet
both heads are exported in `combat_pvnet_v1` and reported by
`combat_pvnet_parity.py`/`eval_combat_pvnet.py`. Any consumer of the exported
`turns`/`potion` outputs gets init noise / ~0 values.

## Evidence

- `train_combat_pvnet.py:257-258` (lp shrinkage, lt constant 0.0; `LAMBDA` still
  lists `potion: 0.2`, `turns: 0.1` at `:37`).
- The fairgen value CSV had no `endTurn`/`potionsConsumed`/`pUsed*` columns, so
  no label was available (root cause).

## Why it matters

The exported contract claims two heads that were never trained; parity checks
pass because they compare the same untrained weights.

## Candidate fix direction

Emit rich labels from the producer (fairgen) and train real losses when
present; fail loudly otherwise.

## Relevant code

- `train_combat_pvnet.py::value_losses`
- `apps/one_combat.cpp` (`fairGen`/`runFairGenSeed`, rich-label suffix)

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree:
- `runFairGenSeed` now emits `endTurn,potionsConsumed,pUsed0..43` (same
  suffix as distgen), so future fairgen value CSVs carry labels.
- `train_combat_pvnet.py` detects rich labels, trains potion BCE + turns
  smooth-L1 (log1p) when present, and prints a loud warning otherwise.
- The PVNet retrain on rich-label data is queued in the rerun ledger
  (row "PVNet heads/layout"; GPU + fairgen regeneration gated).
