# Smokes (2026-11-01, author container, binary b8f0628b… built at e55f4827)
- Equivalence: §731's `run_unit.sh` on its units 1 and 2 with this binary and §731's variants.tar: all 32 rows
  identical to §731's uploaded rows in every column but CPU (state, id, encounter, seeds, HP, potions, valid, won, HP
  left, potions left, turns). The build-input change since f063e9ff (out-of-combat, default-off value chooser) does
  not touch act4replay.
- `make_variants.py` with N = 4,253: the first 1,000 lines of every v<k>.jsonl are byte-identical to §731's.
- This round's `run_unit.sh` on line 0 (global base 1000): rc=0, 16 valid rows with `budget=learned`, all checks
  pass, 3,536 s wall with another unit running beside it (218 CPU-s per fight; an expensive base, §731 averaged 44).
  (A first try ran two units in one output directory, where they share `in/`, and failed with rc=96; workers give
  each unit its own directory.)
- `analyze.py` on that unit: 1 valid base, rc {0: 1}, 0 bad rows, labels.csv with global base 1000, labels_all.csv
  16,016 rows.
