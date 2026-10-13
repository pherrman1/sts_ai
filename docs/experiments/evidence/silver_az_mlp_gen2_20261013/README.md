# Silver AZ MLP prior, generation 2 (self-play data and offline training)

Generation 2 of `/mnt/project-files/silver-az-mlp/PLAN.md`: self-play with the
generation-1 MLP as in-tree prior (`one_combat silverazgen`, this branch), then
warm-started training on the window. No online evaluation (PLAN milestones are
after generations 1, 3 and 6). No ledger entry: offline training only.

## Self-play data (frozen: `FROZEN.md`, `BRIEF-worker.md`, `worker.sh`, `env.sh`)
- Commit `63ae65d7`, binary sha256 9098ee11…b0f7, prior gen 1 (a5f4505a…64d2),
  2k flat exact Silver, tree prior K = 8, weight 400, root bonus off.
- 4 cloud workers (N = 4). 1,024 A0 runs: natural seeds 86000000-86000511,
  perturbed 86001000-86001511. 256/256 units rc 0; every manifest's row sha
  matches its file; one producer, prior and environment.
- 416,061 roots (394,522 with two or more actions after the drop below),
  22,171 fights, 0 invalid fights. Perturbed seed 86001271 aborted at floor 18
  with the known native Silver "stall: exceeded 1000 decisions"; its stalled
  fight left 1,000 roots without a fight row, dropped in packing
  (`pack --drop-no-fight g2`).
- Smoke cost (idle core): natural run ~16 s / ~540 roots, perturbed ~36 s /
  ~460 roots.

## Training (`PLAN-train.md`, written before training)
Window: bootstrap corpus (orig 165,134 + x5 789,227 roots, plain 10k labels)
plus gen 2 (394,522). Folds seed % 5 (train 0-2, validation 3, test 4).
Warm start from `model-gen1.pt` keeping its input scales (`--init` now reuses
the checkpoint's scales); gen-1 regularization (wd 1e-2, dropout 0.35).
The warm-started model reproduces gen 1 on orig fold 4 (CE 1.2204, top-1 56.1%).

| run | recipe | best epoch | validation CE (fold 3, all) |
|---|---|---|---|
| A | PLAN: 2 passes | 1 | 1.2743 |
| **B** | 40 epochs, patience 8, LR halving | 10 | **1.2707** |

B is generation 2 by the pre-declared rule (lower validation CE).

## Monitors (fold 4, gen 2 = run B; gen 1 in brackets)
1. Orig corpus (32,309 roots, plain 10k teacher): CE 1.2196 [1.2204], top-1
   56.7% [56.1%]. No drift (flag would be a CE rise > 0.02). Run A: 1.2243 / 56.3%.
2. Gen-2 held-out seeds (77,227 roots, 2k + prior teacher): CE 1.3413 [1.3579],
   top-1 56.2% [55.4%]. x5 corpus: 1.2447 [1.2490].
3. Mean total variation gen 2 vs gen 1 over all fold-4 roots (267,621): 0.055.
4. Native parity (`silverpolicymlpcheck` vs the float64 reference, two feature
   files, 1,923 + 3,525 roots): max |logit diff| 1.8e-6, pass. Cost 7.9-8.4 µs
   per root, same as gen 1 (8.1 µs on the same file).

The offline gain over gen 1 is small (orig fold-4 CE −0.0008, gen-2 teacher CE
−0.017). **Inference:** most of the fit to the new teacher is already there in
gen 1; whether iteration adds play strength is the generation-3 milestone's
question (PLAN §7).

Model: `/mnt/project-files/silver-az-mlp/gen2/model/combat_policy_mlp_gen2.txt`
sha256 7eef7ce1…a471 (`model-gen2.pt`, run A checkpoint, train reports, `SHA256SUMS`).
Training: PyTorch 2.14.1 CPU, 4 threads, ~30 s per epoch.

## Reproduce
```
python3 tools/silver_az_mlp.py featurize build/linux-gcc-release/one_combat FEAT orig=$A/corpus-450376c8 x5=$A/corpus5x-450376c8 g2=GEN2_DIR
python3 tools/silver_az_mlp.py pack FEAT pack.npz orig=$A/corpus-450376c8 x5=$A/corpus5x-450376c8 g2=GEN2_DIR --drop-no-fight g2
python3 tools/silver_az_mlp.py train pack.npz OUT --init model-gen1.pt --epochs 40 --patience 8 --lr-decay
python3 tools/silver_az_mlp.py export OUT/model.pt combat_policy_mlp_gen2.txt names.json
```
Seeds used: 86000000-86000511 and 86001000-86001511 (self-play); smokes
74046000-74046001, 74046010-74046011, 74046020-74046021, 74046040-74046041.
