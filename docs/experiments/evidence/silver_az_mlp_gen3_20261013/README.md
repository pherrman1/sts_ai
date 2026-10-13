# Silver AZ MLP prior, generation 3 (self-play data and offline training)

Generation 3 of `/mnt/project-files/silver-az-mlp/PLAN.md`, same recipe as
generation 2 ([packet](../silver_az_mlp_gen2_20261013/README.md)) with the
generation-2 MLP as in-tree prior. Its fight-level milestone evaluation is §460
([packet](../silver_az_mlp_gen3_eval_20261013/README.md)).

## Self-play data (frozen: `FROZEN.md`, `BRIEF-worker.md`, `worker.sh`, `env.sh`)
- Main `37b7d33e` (#520), binary sha256 9098ee11…b0f7 (`BINARY_SHA256`, same file
  as gen 2), prior gen 2 (7eef7ce1…a471), 2k flat exact Silver, tree prior K = 8,
  weight 400, root bonus off. Teacher id `silver-az-2000-k8-rb0-7eef7ce1`.
- 8 cloud workers (N = 8, Philipp's choice). 1,024 A0 runs: natural seeds
  88000000-88000511, perturbed 88001000-88001511. 256/256 units rc 0; every
  manifest's producer, binary and prior hash checked; 0 invalid rows.
- 395,198 roots. No native Silver stall this generation (`--drop-no-fight` dropped
  nothing from g3).

## Training (`PLAN-train.md`, written before training)
Window (PLAN §2.4): bootstrap corpus (orig + x5, plain 10k labels), gen-2 and
gen-3 self-play; 1,724,771 roots after packing. Folds seed % 5 (train 0-2,
validation 3, test 4). Warm start from `model-gen2.pt` (input scales kept), wd
1e-2, dropout 0.35.

| run | recipe | best epoch | validation CE (fold 3, all) |
|---|---|---|---|
| A | PLAN: 2 passes | 1 | 1.2904 |
| **B** | 40 epochs, patience 8, LR halving | 8 | **1.2869** |

B is generation 3 by the pre-declared rule (lower validation CE).

## Monitors (fold 4, gen 3 = run B; gen 2 in brackets)
1. Orig corpus (32,309 roots, plain 10k teacher): CE 1.2192 [1.2196], top-1
   56.8% [56.7%]. No drift.
2. Per source: g3 held-out (74,708 roots) CE 1.3313 [1.3375]; g2 (77,227) 1.3365
   [1.3413]; x5 (158,085) 1.2420 [1.2447].
3. Mean total variation gen 3 vs gen 2 over all fold-4 roots (342,329): 0.036
   (gen 2 vs gen 1: 0.055).
4. Native parity (`silverpolicymlpcheck`, 3,525 orig + 809 g3 roots): max |logit
   diff| 1.2e-6, pass. About 6-7 µs per root.

Model: `/mnt/project-files/silver-az-mlp/gen3/model/combat_policy_mlp_gen3.txt`
sha256 f57b7fdd…5315 (`MODEL_SHA256SUMS`; `model-gen3.pt`, run-A checkpoint).
Training: PyTorch 2.14.1 CPU, 4 threads (run B 531 s).

## Reproduce
As gen 2, with `g2=GEN2_DIR g3=GEN3_DIR`, `--drop-no-fight g2 g3` and
`--init model-gen2.pt`.

Seeds used: 88000000-88000511 and 88001000-88001511 (self-play); smokes
74053000-74053001, 74053010-74053011.
