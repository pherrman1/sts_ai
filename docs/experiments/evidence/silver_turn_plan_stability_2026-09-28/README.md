# Native Silver within-turn plan stability — 2026-09-28

Descriptive diagnostic for ledger §367. It asks whether Silver re-searches
decisions whose outcome was already clear at the previous decision of the same
turn ("obviously played" cards), and how much budget that costs.

- `diagnostic.diff`: the `STS_SILVER_TREE_PROFILE` extension (`root_hash`,
  `turn_plan`, `turn_plan_stop`) against baseline `7952f00`.
- `flat_*` / `adaptive_*`: `bestbench` seeds 0..7, asc 0, fair, 1 thread, flat
  1,000 simulations and adaptive 500/10,000. `flat_off_binary1.*` is the
  profile-off parity arm.
- `flat10k_*`: flat 10,000, seeds 0..7 in four 2-seed shards (ledger §368),
  profiled with `diagnostic_card_fields.diff` (copy-insensitive card identity
  per plan step). Results columns matched a run without the card fields.
- `analyze_plan.py` → `summary*.txt`; `reorder.py` → `reorder*.txt`;
  `fresh_roots.py` → `fresh_roots_flat10k.txt` (agreement split by reused vs
  cap-restarted roots).
- `manifest.json`: commands, binary/model/artifact hashes.

Parity: profile-on and profile-off CSVs (all columns except wall time) are
identical for the flat arm, and both profiled arms reproduced byte-identical
results columns across the two diagnostic binaries.

See ledger §367 and §368 in [ledger-06](../../ledger-06.md) for results and interpretation.
