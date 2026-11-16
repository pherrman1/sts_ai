# Offline tests for the playout role (issue #1053, ledger §TBD-a)

Copied from the author's run directory (`/mnt/project-files/rollout-prior-next/calib/`); paths inside the scripts
point at the author's scratch directory and are kept as run.

- `calib.py`, `calib1.json`: argmax Q-regret of g7f_E, V and X-B against the factory's 2k-simulation Gumbel labels on
  batch 1's validation split (`tools/rollout_prior/train.py::split_of == 1`), per role (root, tree, playout).
- `pv_rows.py`: selects batch 1's validation boss / Act-4 root rows (with the score of the fight G16 played) and tree
  rows; `run_pv.sh`: `one_combat playoutvaluebench OUT PLAYOUTS ARMS` on them (64 playouts per root, 32 per tree row);
  `pv_analyze.py` → `pv_result.json`: MSE / bias / Brier / correlation of each arm's mean playout value against the
  played score (`*_ref`) and against the label search's backed-up Q (`*_qb`), with seed-bootstrap CIs of the
  differences to g7f_E.
