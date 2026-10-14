# Gen-4 training plan (written 2026-10-13 ~22:40Z, before any gen-4 data arrived)

Same rule as gen 3 (`../../gen3/PLAN-train.md`). Window (PLAN §2.4, 4 gens): bootstrap corpus (orig + x5,
plain 10k), g2, g3 (2k + prior teachers) and g4 (10k + gen-3 prior teacher); `pack --drop-no-fight g2 g3 g4`.
Folds seed % 5. Warm start from `../../gen3/model/model-gen3.pt` (keeps input scales); AdamW lr 5e-4,
wd 1e-2, dropout 0.35, batch 1,024, seed 0.
- A (PLAN recipe): `--epochs 2`.
- B: `--epochs 40 --patience 8 --lr-decay`.
Selection: lower fold-3 validation CE (all sources). Fold 4 read only for monitors after selection.
Descriptive only (not selectable as gen 4 without a separate CPU-matched check): 512/256 from scratch,
`--epochs 40 --patience 8 --lr-decay`, same pack.
Monitors: 1 orig fold-4 CE/top-1 (gen 3 1.2192 / 56.8%; drift flag CE rise > 0.02); 2 fold-4 CE per
source incl. g4 (gen 4 vs gen 3); 3 mean TV gen 4 vs gen 3, all fold-4 roots; 4 native parity (< 1e-3)
and µs per root.
