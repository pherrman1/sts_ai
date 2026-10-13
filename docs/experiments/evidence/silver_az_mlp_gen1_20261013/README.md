# Silver AZ MLP prior, generation 1 (offline training and smokes)

Implementation evidence for items 1, 3 and 4 of
`/mnt/project-files/silver-az-mlp/PLAN.md` §5 (native `combat_policy_mlp_v1`
prior, `tools/silver_az_mlp.py`, `ctmsilvergen` armset `mlpprior`). Built on
main `4110fdbc`. No ledger entry yet: the generation-1 online check is not
authorized; seeds 85000000-85000127 and ledger §455 are reserved for it.

## Data
- §397 corpus `corpus-450376c8` (48 units, 165,134 roots with two or more
  actions) and §404 5x corpus `corpus5x-450376c8` (239 finished units,
  789,227 roots; §404 used 238 units and 785,629 roots), both from
  `/mnt/project-files/silver-synthetic-prior/ARCHIVE-silver-synthetic-prior.tar.gz.part00-03`.
- Re-featurized with this branch's `one_combat silversynthfeatures` (action
  rows now carry `tgt`), then `silver_az_mlp.py pack` (954,361 roots,
  5,751,725 edges; 1,000 roots have no fight row and no value target).
- Folds `seed % 5`: train 0-2 (572,338 roots), validation 3 (191,629), test 4.
  Monitor 1 is test fold 4 of the original corpus (32,309 roots).
- The metric reproduces the §404 v1 reference on these roots: v1 GBM
  (`gates-20261008/prior-natpert.txt`) CE 1.2299, top-1 55.31%.

## Results (fold 4 of the original corpus)
| model | CE | top-1 |
|---|---|---|
| v1 GBM (§397, 1x) | 1.230 | 55.3% |
| MLP 128/64, plan recipe (wd 1e-4, no dropout) | 1.250 | 54.0% |
| **MLP 128/64, gen 1 (wd 1e-2, dropout 0.35)** | **1.220** | **56.1%** |
| v2-6x GBM (§404) | 1.144 | 61.2% |
| encoder-6x (§404) | 1.124 | 61.7% |

- The plan recipe (AdamW lr 5e-4, wd 1e-4, batch 1,024) overfit from epoch 4
  and missed the offline kill line (1.250 > 1.230). A validation-only sweep of
  eight configurations (`sweep-validation.json`; fold 4 not evaluated) picked
  wd 1e-2 with dropout 0.35 on the first hidden layer (validation CE 1.2415 vs
  1.2679). Its retrain (`train-gen1.json`, best epoch 31) gives the gen-1 row.
  The retrain is not bit-identical to the sweep run (validation 1.2409, best
  epoch 31 vs 22): multithreaded CPU training is not deterministic.
- Gen 1 clears the offline kill line by 0.010 CE; it stays well below the 6x
  GBM v2 and encoder references.
- All folds, both corpora (190,394 fold-4 roots): CE 1.244, top-1 55.0%.
- Auxiliary value head (weight 0.1, not exported): fold-4 MSE 0.023 vs
  target variance 0.100.

## Native parity and cost (`parity-and-timing.json`)
- `one_combat silverpolicymlpcheck` vs the float64 reference of the exported
  file on two full feature files (3,525 + 3,461 roots): max |logit diff|
  1.8e-6. Pass threshold 1e-3.
- Per root, all edges, same files: MLP 8.6-9.0 µs, GBM v1 (1,997 trees,
  `predictPolicyActions`) 180-188 µs.
- In search (`smoke-cpu.json`, ctmsilvergen, 47 fights x 2 replicates, seeds
  74043001-74043002 run side by side): `mlp8_2k` 1.117x the CPU per decision of
  `plain2k` (1.145x per fight); `plain_cpu` at 2,200 sims 1.098x. The GBM
  `tree8_2k` on seed 74043000 was 1.76x. **Inference:** a CPU-matched plain
  budget for this model is about 2,250-2,300 simulations; it should be
  measured on more fights before it is frozen in the pre-registration.

## Default paths unchanged
- `ctmsilvergen` with `STS_CTMSILVER_ARMSET=treeprior452k8` on seed 74043000:
  this branch vs a build of main `4110fdbc` give identical arms, states and
  samples CSVs (175 arm rows incl. `tree8_2k` and `root2k`, 25 states, 975
  samples) apart from CPU-time columns.
- `test silver_searcher` (includes the new hand-computed MLP check): PASS.

## Reproduce
```
A=<extracted archive>/silver-synthetic-prior
python3 tools/silver_az_mlp.py featurize build/linux-gcc-release/one_combat FEAT orig=$A/corpus-450376c8 x5=$A/corpus5x-450376c8
python3 tools/silver_az_mlp.py pack FEAT pack.npz orig=$A/corpus-450376c8 x5=$A/corpus5x-450376c8
python3 tools/silver_az_mlp.py train pack.npz OUT --wd 1e-2 --dropout 0.35 --gbm-ref $A/gates-20261008/prior-natpert.txt
one_combat silversynthreplay names names.json
python3 tools/silver_az_mlp.py export OUT/model.pt combat_policy_mlp_gen1.txt names.json
```
Models: `/mnt/project-files/silver-az-mlp/gen1/` (`combat_policy_mlp_gen1.txt`
sha256 a5f4505a…64d2, `model-gen1.pt`, `model-plan-recipe.pt`, `SHA256SUMS`).
Training ran with PyTorch 2.14.1 (CPU, 4 threads), about 10 minutes.

Seeds used: 74043000 (bit identity), 74043001-74043002 (MLP smoke).
