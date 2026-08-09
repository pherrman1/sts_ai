# 2026-08-09 — WinNet::load truncation validation + native-OOC banner truthfulness

Date: 2026-08-09
Session/task: Fix WinNet::load truncated-tree silent corruption and the
misleading `[native OOC floor/win GBMs ON]` banner in apps/one_combat.cpp.

## Decision

`WinNet::load` (`apps/one_combat.cpp`, `struct WinNet`) now defaults `ok=false`
and sets it only after validation passes:

- `f.good()` must hold after reading `ntrees`, and `ntrees >= 1`;
- `f.good()` is checked after every node read, and node fields are stored only
  after the read succeeds (no uninitialized feature indices);
- each tree's final node must be a leaf (`feat == -1`);
- after the last tree, a probe read must reach clean EOF (no trailing data).

A failed load prints a path-specific `WinNet:` error to stderr and returns
false. The `[native OOC floor/win GBMs ON; no v_server required]` banner in
`main` now prints only when `g_floorNet.ok && g_winNet.ok`; otherwise the
`[native V_win NOT loaded; win-rest helpers will use v_server fallback]`
warning prints instead.

## Rationale

Previously `ok=true` was set unconditionally after parsing: a file truncated
before `ntrees` loaded as a zero-tree model (silent constant predictions), and
mid-node truncation fed uninitialized ints to `predict()` as feature indices
(UB/heap over-read). The banner also claimed "floor/win GBMs ON" when the win
model had just failed to load. Rejecting `ntrees < 1` is safe because the
exporter (`export_win_model.py`) always writes at least one tree, and the
final-node-is-leaf invariant holds for every tree in both tracked artifacts
(1060/1060 and 1256/1256 trees verified).

## Alternatives considered

- Per-model separate status lines instead of a gated banner — the plan allowed
  either; a single gated banner plus the existing per-path warning keeps output
  stable for consumers that grep for the banner.
- Verifying only the node count vs declared `nn` instead of the leaf check —
  the count is inherently enforced by the read loop; the leaf check adds a
  structural sanity check with no false positives on real artifacts.

## Evidence

- `apps/one_combat.cpp` — `WinNet::load` (validation), `main` (banner gate).
- `export_win_model.py` — writer never emits `ntrees 0`; XGBoost dump order
  puts a leaf last per tree.
- `winnettest_selftest.py` + `CMakeLists.txt` (`winnettest_selftest` CTest
  entry) — regression fixtures: truncated-before-ntrees, zero-tree,
  mid-tree-truncation, non-leaf final node (all must exit nonzero), and a
  positive control predicting 0.5.
- `build/v_win_trees.txt`, `build/v_rich_trees.txt` — leaf invariant spot-check.

## Status and follow-up

- Implemented; `one_combat winnettest` now exits nonzero on malformed trees.
- The `STS_WIN_NET` env block still ignores `g_winNet.load`'s return value;
  a failure there is later retried by the native-OOC block, which now
  surfaces the failure in the banner. No follow-up required for the fix.
