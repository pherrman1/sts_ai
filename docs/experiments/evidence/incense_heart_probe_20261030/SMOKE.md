# Smokes (2026-10-30, author container, binary b6c03fc8…)
- `act4replay` learned budget, states 0-3 of `heart_states.tar`, counters 0 and 5, one copy, OMP 4 (local run of the
  same settings; planner seeds differ from the campaign's because the state index is part of the planner seed key):
  CPU per fight 3.5 / 4.5 / 106 / 107 s (c0) and 3.7 / 5.2 / 47 / 76 s (c5). State 2 (75/75 HP): c0 won in 14 turns,
  c5 lost in 5. Flat 40k with the 32k reuse cap took 24-780 s on the same states.
- `run_unit.sh` for unit 3 (OMP 1): rc=0, 27 s wall, 6 rows `budget=learned`, all checks pass; counter 3 survives to
  turn 4, the others die on turn 2 (55/80 HP, no potions).
- `analyze.py` on that unit: runs, 1 valid state.
