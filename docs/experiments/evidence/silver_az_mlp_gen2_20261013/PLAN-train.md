# Gen-2 training plan (written 2026-10-13 ~17:42Z, before any gen-2 training run)

Window (PLAN §2.4, generations 1-2): bootstrap corpus (orig 165,134 + x5 789,227 roots, plain flat 10k
labels) + gen-2 self-play (g2, 394,522 multi-action roots; 1,000 roots of the stalled fight of seed
86001271 dropped with `pack --drop-no-fight g2`). Folds seed % 5: train 0-2, validation 3, test 4.
Warm start from /mnt/project-files/silver-az-mlp/gen1/model-gen1.pt (keeps its input scales);
gen-1 regularization (AdamW lr 5e-4, wd 1e-2, dropout 0.35, batch 1,024 roots).

Two runs, seed 0:
- A (PLAN recipe): 2 passes (`--epochs 2`), best epoch by validation CE.
- B (gen-1 lesson, more patience + LR decay): `--epochs 40 --patience 8 --lr-decay`.
Selection: the run with the lower fold-3 validation CE (all sources) becomes gen 2. Fold 4 is only
read for the monitors after selection.

Monitors (PLAN §2.5): 1 fold-4 CE/top-1 on orig (gen 1 1.2204 / 56.1%; drift flag if CE worsens by
> 0.02, i.e. "drop > 2 points"); 2 fold-4 CE on g2 (gen 2 vs gen 1); 3 mean TV gen 2 vs gen 1 on all
fold-4 roots; 4 native parity (max |logit diff| < 1e-3) and µs per root.
