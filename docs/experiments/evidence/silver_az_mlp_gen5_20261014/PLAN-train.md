# Gen-5 training plan (written 2026-10-14 ~10:10Z, before any gen-5 training)

Window (PLAN §2.4, 4 self-play gens): bootstrap (orig + x5, plain 10k), g2, g3, g4 (10k) and g5 (20k + gen-4 prior);
`pack --drop-no-fight g2 g3 g4 g5`. Folds seed % 5. 128/64 only (same native cost as gen 4).
Warm start from `../../gen4/model/model-gen4.pt` (keeps input scales); AdamW lr 5e-4, wd 1e-2, batch 1,024, seed 0.
- A (PLAN recipe): `--epochs 2`, dropout 0.35.
- B (gen-4 recipe, the gen-4-comparable arm): `--epochs 40 --patience 8 --lr-decay`, dropout 0.35.
- C: as B with dropout 0.15 (architecture thread, gen-4 pack: 1.2609 vs 1.2713 at 0.35, scratch).
Selection: lowest fold-3 validation CE (all sources) among A, B, C; B is always reported.
Offline gate (Philipp 2026-10-14): continue raising the teacher only if gen 5's orig fold-4 CE improves on
gen 4's 1.2103. Monitors as gen 4 (orig CE/top-1, per-source CE incl. g5, TV vs gen 4, parity, us/root).
Distillation from 512/256 (architecture thread) is not part of this gen.
