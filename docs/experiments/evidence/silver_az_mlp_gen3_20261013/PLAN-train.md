# Gen-3 training plan (written 2026-10-13 ~20:17Z, before any gen-3 training run)

Same rule as gen 2 (`../gen2/train/PLAN-train.md`). Window (PLAN §2.4, gens 1-3): bootstrap corpus
(orig + x5, plain 10k), gen-2 self-play (g2) and gen-3 self-play (g3, prior gen 2); `pack
--drop-no-fight g2 g3`. Folds seed % 5. Warm start from `../gen2/model/model-gen2.pt` (keeps its input
scales, which are gen 1's); AdamW lr 5e-4, wd 1e-2, dropout 0.35, batch 1,024, seed 0.
- A (PLAN recipe): `--epochs 2`.
- B: `--epochs 40 --patience 8 --lr-decay`.
Selection: lower fold-3 validation CE (all sources). Fold 4 read only for monitors after selection.
Monitors: 1 orig fold-4 CE/top-1 (gen 2 1.2196 / 56.7%, gen 1 1.2204; drift flag CE rise > 0.02);
2 fold-4 CE on g3 and g2 (gen 3 vs gen 2); 3 mean TV gen 3 vs gen 2, all fold-4 roots;
4 native parity (< 1e-3) and µs per root.
