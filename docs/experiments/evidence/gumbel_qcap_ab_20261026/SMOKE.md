# Smoke (2026-10-26, author)

Code `9a37d780` (main after #869), v3 binary sha256 `7bb54d7e…` (this manifest), campaign files as committed,
`run_unit.sh` run directly (not through worker.sh) on seeds 111383990–111383991, 2 units in parallel on 4 CPUs.

- All 4 games rc 0; `analyze.py` reads both seeds as valid (footers complete, integrity passed).
- Banners: A shows `screens_a20_default=map_full_budget` and no Gumbel keys; B shows `full_root_sims=2048`,
  `gumbel_root=16:1.000000`, `gumbel_qcap=1.000000`.
- B policy rows (seed 111383991): every searched root is a map root with `selectionRule` `gumbel_sh`, `fullBudget`
  true, `requestedSimulations` 2048, `root.gumbelQCap` 1.0.
- Wall per game: A 1436 / 792 s, B 310 / 1301 s (games end on different floors; not a CPU comparison). One unit
  ≈ 30–35 min. Estimate for 512 units on 16 × 4 lanes: ≈ 4–5 h, ≈ 270 core-h.
- Outcomes are not reported (smoke seeds).
