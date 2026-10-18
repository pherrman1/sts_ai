# Gen-7 GPU training data (never merge)

Gen-7 Silver MLP prior: the gen-6 window plus A20 Act-4 self-play roots (Shield & Spear, Heart).
Plan: `docs/experiments/evidence/silver_gen7_act4_20261017/PLAN.md` on branch `claude/silver-gen7-act4`
(draft PR #621, frozen RUN_COMMIT f29515bf). Training steps: `gen7/PLAN-train.md`.

Reassemble: `cat pack-g7.npz.gz.part* | gunzip > pack-g7.npz` and check `sha256sum -c SHA256SUMS`.

- `pack-g7.npz` = the gen-6 pack (sha 7efd43f0, its 2,531,313 roots unchanged and first, in the same
  order) + 371,487 multi-action Act-4 roots as source `g7a4`. Built by `gen7/merge_g7.py`.
- Act-4 roots: `r_seed` holds the source run's seed (`perturbation.sourceSeed`), so `Data.fold = r_seed % 5`
  keeps Shield & Spear, Heart and both copies of one source run in one fold. The generator seed is in
  `r_state_seed` (-1 for gen-6 roots). No trainer change is needed.
- `arch_dev.py`, `convert.py`, `silver_az_mlp.py` and `results/` (g6_t512, g6_D, g6_E, g6_Eenc) are unchanged
  from the gen-6 branch. The gen-6 pack parts were removed; they stay in this branch's history (c6a1f24f).
- `gen7/gate_g7.py`: the pre-registered offline gate (g6_E vs gen 7, each with its own scales).

Gen-6 README (history): the gen-6 pack, `arch_dev.py` = net-arch thread's arch.py (share sha 3e736bba) +
`--device`, env `STS_TOOLS`, `ARCH_RUNS`; CPU smoke gives byte-identical results to the original.
`silver_az_mlp.py` = tools/ after #535 (3e28818).
