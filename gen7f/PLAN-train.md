# Gen-7f training: gen 7 retrained on active power features (written 2026-10-18 ~14:30Z, before any training)

Why: Philipp's rule (11:44Z) says to pack and train g7_E and every later combat net with the
`STS_ACTIVE_POWER_FEATURES` value it is deployed with (default 1 since #659). g7_E was trained on legacy features.
Philipp chose "Retrain, then swap" (card, 13:44Z) for making gen 7 the default rollout root table model.

Data: `pack-g7f.npz` (sha bdaf4f68). Same corpora and window as `pack-g7.npz`, all re-featurized with
`one_combat` built from main e032c04b (sha 3315a7c1), env `STS_ACTIVE_POWER_FEATURES=1 STS_SILVER_ROLLOUT_ROOT_TABLE=0`.
Corpora: orig/x5 from the `silver-synthetic-prior` archive, g3-g6 share tars, the 16 verified gen-7 Act-4 tars. Then
`silver_az_mlp.py pack` (window `--drop-no-fight g3 g4 g5 g6`; Act-4 separately) and `gen7/merge_g7.py`.
Log: `gen7f/pack-g7f.log`.
- 2,899,992 roots (gen 7: 2,902,800). The current engine enumerates different root actions for 2,808 recorded roots
  (`rootEdgeMismatch`, about one root in each of 2,769 fights, spread over encounters), so the featurizer drops
  those roots. The Act-4 part keeps all 371,487 roots.
- On the 2,462,496 window roots in fights with unchanged root counts, every label array (seed, fight, value, edge
  count, visits, targets, action features) is identical to pack-g7. The state features differ for 295,054 roots
  (12.0%).
- Control (gen-6 w01, 48,955 roots): with `STS_ACTIVE_POWER_FEATURES=0`, the new binary reproduces the pack-g7 state
  features exactly. With `=1`, 6,766 roots (13.8%) differ. So the active-power flag is the only feature change.

Recipe: gen 7's recipe, with only the pack and names changed.

```
export STS_TOOLS=$PWD ARCH_RUNS=$PWD/runs
python3 arch_dev.py g7f_t512 --pack pack-g7f.npz --h1 512 --h2 256 --epochs 40 --patience 8 --lr 5e-4 \
  --dropout 0.35 --sched halve --test --device cuda --dump-logp
python3 arch_dev.py g7f_E --pack pack-g7f.npz --enc-emb 16 --mon-emb 16 --epochs 25 --patience 25 --lr 1e-3 \
  --dropout 0.15 --sched cosine --teacher runs/g7f_t512/logp.npy --alpha 0.5 --test --device cuda
python3 gen7f/gate_g7f.py --ref-pack pack-g7.npz --ref runs/g7_E/model.pt --new-pack pack-g7f.npz \
  --new runs/g7f_E/model.pt --device cuda --out gen7f/gate.json
```

`pack-g7.npz` parts are in this branch's history (commit 1d69e625). Reassemble them if the training folder lacks them.

Sanity gate (fixed now): g7f_E's fold-4 CE on its own pack is at most g7_E's fold-4 CE on its pack + 0.005, for both
orig and g7a4. Pass: export to native v2 with `gen7/export/` (pack-g7f, a run of `silverpolicymlpcheck` from main
>= e032c04b with `STS_ACTIVE_POWER_FEATURES=1`, parity < 3e-6) as `gen7f/combat_policy_mlp_g7f_E.txt`. The next steps
are a fight-level check of g7f_E as the rollout root table model vs g6_E, then a default-switch PR (`=` the g6_E path
restores). Ledger: §517.
