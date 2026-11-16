# Offline tests for the playout role (issue #1053, ledger §814)

Copied from the author's run directory (`/mnt/project-files/rollout-prior-next/calib/`); paths inside the scripts
point at the author's scratch directory and are kept as run.

- `calib.py`, `calib1.json`: argmax Q-regret of g7f_E, V and X-B against the factory's 2k-simulation Gumbel labels on
  batch 1's validation split (`tools/rollout_prior/train.py::split_of == 1`), per role (root, tree, playout).
- `pv_rows.py`: selects batch 1's validation boss / Act-4 root rows (with the score of the fight G16 played) and tree
  rows; `run_pv.sh`: `one_combat playoutvaluebench OUT PLAYOUTS ARMS` on them (64 playouts per root, 32 per tree row);
  `pv_analyze.py` → `pv_result.json`: MSE / bias / Brier / correlation of each arm's mean playout value against the
  played score (`*_ref`) and against the label search's backed-up Q (`*_qb`), with seed-bootstrap CIs of the
  differences to g7f_E.

Reproduction (review N1). Inputs: batch 1's validation-split raw unit tars, kept whole on the share in
`/mnt/project-files/prior-factory/units/` (the 197 tars with `split_of(seed) == 1`); `pv_rows.py` extracts the root and
tree rows from them. The row files and the per-row outputs (`pv_root0/1.jsonl`, `pv_extra.jsonl`, about 160 MB) stay
in the author's scratch directory and are not committed. Binary: `one_combat` release build of the working tree that was
committed as d4c7fe9b (built at 08:36 CET, before that commit at 08:51 CET; the playoutvaluebench code is unchanged
in it), environment as in `run_pv.sh`. Calibration (`calib.py`) read the merged batch-1 validation pack
`factory1_val.npz` (`tools/rollout_prior/pack_factory.py merge` of batch 1, `--splits 1`).

Reading (review N2): part of V's and X-B's lower MSE is lower bias (the played score is above every arm's mean playout
value; bias −19.9 g7f_E, −17.2 V, −17.0 X-B); `pv_result.json` lists `bias_ref` and `corr_ref` next to the MSE.
