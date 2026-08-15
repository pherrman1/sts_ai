# Phase-12 screen-contract correction: M0/M1 retrain and gameplay gate

Date: 2026-08-15
Baseline: `0226f2587772d9ec7d779a87a48d81b46da1ccc0`
Status: exploratory evidence; no promotion claim

## Finding

`tools/convert_marg_to_trainer.py` wrote diagnostic `gateKind` into the trainer
`screen` field, while the diagnostic and native deployment use actual
`ScreenState`. Thus treasure/rest/shop were encoded as 5/6/7 rather than 6/7/8.
Temporary corrected datasets changed only `screen` and preserved all labels and
other columns.

Corrected invariants: 210,838 rows, 39,870 groups, 45,088 changed rows,
7,690 changed groups, zero MAP groups, and 1,294/3,260/3,136
TREASURE/REST/SHOP groups. The local expectation that SHOP had 1,294 groups
was incorrect: 1,294 is TREASURE.

## Training and gameplay

Corrected M0 and M1 used the original 40-epoch rung-4, non-transformer,
absolute-Q recipe, identical split, model seed 0, and eager CUDA. Both best-CE
checkpoints selected at epoch 6.

| Metric | Original M0 | Corrected M0 | Original M1 | Corrected M1 |
|---|---:|---:|---:|---:|
| `val_pol_ce` | 0.508974 | 0.597685 | 0.511809 | 0.587125 |
| `policy_top1` | 0.788284 | 0.753340 | 0.790982 | 0.761434 |
| Mean margin | 5.338612 | 2.911236 | 5.709118 | 3.182429 |
| `q_top1` | 0.245522 | 0.243392 | 0.250532 | 0.240511 |

Paired fair Searcher3 gate: seeds `900000..900063`, 1,000 sims, 64 particles,
7k VNet alpha 0.3, all strategic gates on, margin 1.0, 12 threads.

| Arm | Original | Corrected | Delta |
|---|---:|---:|---:|
| M0 win rate | 17/64 = 26.56% | 16/64 = 25.00% | -1.56pp |
| M1 win rate | 16/64 = 25.00% | 12/64 = 18.75% | -6.25pp |

Corrected native exports passed 32 parity checks each. Best-CE checkpoint hashes:

| Artifact | SHA256 |
|---|---|
| M0 `.pt` | `2dc6144656ea6bb6637e200f4b5bb7b525dd2557f03a69069062bdd53b84a141` |
| M1 `.pt` | `b7521ccaf54e542059d2b4ee1b0dda395bea25c9406533b26963e7acbbf4f8fa` |
| M0 native | `ef351d89382df4abf3e9f4c33df91e0cd3b7b6e0aece3138122b5f48a8e5b993` |
| M1 native | `d60ef64c404eac54ed89e3006a39585058f081ddb4d254dedc5f07a27f4dd415` |

Gameplay CSV hashes: M0 original `b1543f71ffd770ec324dd5095c7c0e81e797cb17272bc881acb8844a20a46d75`,
M0 corrected `23d0112d855dd8133de7f1121bfb8f3110c05b51f9de969640eddb0022650124`,
M1 original `a69016c75e3d5c56bb458696ca50c9ef9a67ecf965ccbc9a4f3f149c513d13e4`,
M1 corrected `c87cb9c90cfeaa68d59eea215792a31c546eb0b31f31f45819742bac533d1eca`.

## Interpretation and follow-up

The screen-contract defect is real and requires a permanent converter fix.
Corrected retraining did not improve the small paired gameplay gate for either
objective; M1 declined more strongly than M0. This does not establish that the
corrected contract is intrinsically harmful because the gate has only 64 seeds,
but it rules out the screen bug alone as a likely explanation for V4's advantage.
Coverage/source-controller distribution, teacher behavior, objective/group
weighting, and residual deployment-distribution differences remain open.

The permanent converter fix and regression test were proposed but are not part
of this evidence-recording commit.