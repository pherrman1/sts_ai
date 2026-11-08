# Leaf plan stage 4: offline fit on the stage-2 pilot pairs

Exploratory offline analysis of the §763 pilot (`../fight_end_pairs_pilot_20261107/`); no games were played. `PLAN.md`
was written before the fit on all units, `RESULT.md` has the numbers, the deviations and Philipp's decision (no gate).

Pipeline (inputs: the pilot's unit tars in `/mnt/project-files/fight-end-pairs-pilot/units/` and net-0420):

1. `extract_embed.py SNAP_DIR net-0420.bin PREFIX`: per-copy meta (`PREFIX.meta.jsonl`) and the frozen net-0420
   trunk embedding and value per copy (`PREFIX.npz`). Needs torch (CPU wheel) and `tools/heart1/ppo_model.py`.
   Run here in three snapshots (437, 443 and 1,058 units), 400,173 copies in all.
2. `src_weights.py OUT.json DIR [DIR..]`: inclusion weights w = eligible / sampled per (unit, source seed).
3. `leaf_prices.py PREFIX[,PREFIX..] SRCW.json lp1938.json`: leaves L, P1, P4, V0 and C, cross-fitted, skill against
   zero and against C on the non-HP pairs, act × family means, P1 / P4 weights; also writes `lp1938.oof.npz`.
4. `TE_WEIGHTS=SRCW.json train_eval.py PREFIX[,PREFIX..] te1938w.result.json`: state-dependent heads (V0, H0, H1,
   H1w, H2, G), within-cell slopes, per-family skill, levels; also writes the `.oof.npz` predictions. Written for the
   interim training (its "PLAN.md" is `/mnt/project-files/leaf-plan/pilot-interim-training/PLAN.md`), unchanged here.
5. `compare_heads.py lp1938.oof.npz te1938w.result.oof.npz heads1938.json`: the heads on `leaf_prices.py`'s metric.

The embeddings and `.oof.npz` files (about 0.7 GB) are not kept. `extract_embed.py`'s path to `tools/heart1` is
repository-relative here; the run used the same file at `/home/user/sts_ai/tools/heart1`.
