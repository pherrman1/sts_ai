# Gen-7 training (written 2026-10-18 ~02:20Z, before any training)

Data: 16/16 worker tars verified (tar sha, binary 09a611b1, every unit rc=0, rows/states/producer shas, prior
ca9bd7f2, 40k sims, seeds inside their unit). 219 units, 10,934 fights, 371,487 multi-action roots from 2,913
source runs. Featurizer = the run binary (09a611b1, rebuilt from f29515bf); on gen-6 `w01` it reproduces all
48,955 of that worker's roots in the gen-6 pack byte for byte.

Window: orig + x5 + g3..g6 (the gen-6 pack) + g7a4. Folds `r_seed % 5`, Act-4 roots by source run.

Recipe = gen-6 E, same args except the pack and names (`results/g6_t512/train.json`, `results/g6_E/train.json`):

```
export STS_TOOLS=$PWD ARCH_RUNS=$PWD/runs
python3 arch_dev.py g7_t512 --pack pack-g7.npz --h1 512 --h2 256 --epochs 40 --patience 8 --lr 5e-4 \
  --dropout 0.35 --sched halve --test --device cuda --dump-logp
python3 arch_dev.py g7_E --pack pack-g7.npz --enc-emb 16 --mon-emb 16 --epochs 25 --patience 25 --lr 1e-3 \
  --dropout 0.15 --sched cosine --teacher runs/g7_t512/logp.npy --alpha 0.5 --test --device cuda
python3 gen7/gate_g7.py --pack pack-g7.npz --device cuda --ref results/g6_E/model.pt \
  --new runs/g7_E/model.pt --out gen7/gate.json
```

Gate (PLAN.md, fixed before any data): gen 7 fold-4 orig CE <= g6_E's + 0.005, and gen 7 fold-4 g7a4 CE < g6_E's.
Pass: export to native v2 (`docs/experiments/evidence/silver_prior_arch_20261014/scripts/export_native.py`, parity
< 3e-6) for an online check. The online check and any default change are Philipp's call. Result: ledger §517.

Notes: `arch_dev.py` clips the monster incoming-damage embedding index at 127, as in gen 6; 0.4% of Act-4 slot-0
values (Heart multi-hits) are above it. The g6_E encounter and monster rows for the Act-4 ids were never trained.
