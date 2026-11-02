# Smokes (2026-10-31, author container, binary bebb3547…, code f063e9f)
- First design (600 bases, k = 1 placebo on the same seed, 2 replicates): the first 4 bases × 16 variants as one file
  per variant (`act4replay 4 v<k>.jsonl … 111384000 10000 1`, OMP 4, learned budget as §723). All 64 fights valid,
  no errors. Placebo == control on won, HP left, potions, turns for all 4 bases (determinism). CPU per Heart fight
  mean 83 s, max 308 s.
- One state change usually changes the whole fight: e.g. base 1 (64/75 HP, won with 4 HP) won with 22 HP after −8 HP;
  base 0 won with 16 HP instead of 25 after a potion was added. So a second replicate of the same variant mostly adds
  noise information, not signal; the design switched to 1,000 bases, one replicate, and k = 1 as a reseeded control.
- `make_variants.py` at 1,000 bases: 4,822 records, 4,253 distinct states; operator mix ≈ uniform among applicable.
- `run_unit.sh` for unit 1 at the final design (OMP 1, variants.tar ac30cf81): rc=0, 303 s wall, 16 valid rows with
  `budget=learned`, all checks pass. (The control lost here and won in the first smoke: the planner seed includes the
  line index of the state in its file, 1 there and 0 here.)
- `analyze.py` on that unit: 1 valid base, rc {0: 1}, 0 bad rows, labels.csv written; with one base the sign checks are
  meaningless (one hp_down variant won where the control lost, so labels_usable=false), as expected.
