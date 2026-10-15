# Issue 13: Baseline cache key omits fixed native trees

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-02
- **Source:** [`operations/selfplay-loop.md`](../operations/selfplay-loop.md), "Blocking discrepancies"; [`behavior/determinism-and-rng.md`](../behavior/determinism-and-rng.md)

## Symptom

The baseline cache hashes `one_combat.elf` and current loop models, but native
OOC uses fixed tracked floor/win trees that are not included in the key. If
server-backed inference is restored, the key also omits `v_server.py` and
Python dependency versions. The script comment that baseline outcomes are
deterministic is not a verified invariant.

## Evidence

- `selfplay/loop.sh::baseline_cache_key` (line 203): hashes `one_combat.elf`
  and `selfplay/current/v_win.json`, not `build/v_rich_trees.txt` or
  `build/v_win_trees.txt`.
- `determinism-and-rng.md`: "The self-play baseline cache omits fixed native
  floor/win artifacts from its key and assumes deterministic outcomes without a
  current proof."

## Why it matters

A cache key that misses the artifacts that actually own native OOC decisions
can serve stale baselines when tracked trees change, silently skewing every
paired gate that reuses the cache.

## Candidate fix direction

Include the tracked floor/win tree hashes (and server/Python fingerprints if
server-backed inference is used) in `baseline_cache_key`; verify the
determinism assumption or remove it.

## Relevant code

- `selfplay/loop.sh::baseline_cache_key`, `run_gate_batch`

## Resolution (2026-08-02)

Fixed: `baseline_cache_key` now hashes `$BIN`, current models, `build/v_rich_trees.txt` + `build/v_win_trees.txt`, `v_server.py`, and both policy envs; the determinism comment now states it is an assumption.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
