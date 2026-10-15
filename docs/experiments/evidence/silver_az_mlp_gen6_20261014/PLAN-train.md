# Gen-6 training plan (written 2026-10-14 ~11:45Z, before any gen-6 data arrived)

Window (PLAN §2.4, last 4 self-play gens): bootstrap (orig + x5, plain 10k), g3, g4 (10k), g5 (20k), g6 (40k + gen-5
prior); g2 leaves the window. `pack --drop-no-fight g3 g4 g5 g6` with the #535 packer (byte-identical output).
Folds seed % 5. 128/64. Warm start from `../../gen5/model/model-gen5.pt`; AdamW lr 5e-4, wd 1e-2, batch 1,024, seed 0.
- A: `--epochs 2`, dropout 0.15.
- B: `--epochs 40 --patience 8 --lr-decay`, dropout 0.35 (gen-4 recipe, comparability arm).
- C: as B with dropout 0.15 (gen-5 recipe).
Selection: lowest fold-3 validation CE among A, B, C; B and C always reported.
Offline gate: continue only if gen 6's orig fold-4 CE improves on gen 5's 1.1954. Monitors as gen 5.

Amendment (2026-10-14 ~13:50Z, still before any gen-6 data arrived): add arm D from the net-arch thread
(`/mnt/project-files/silver-prior-arch/RESULT.md`), current native format, no encounter embedding (format change is
Philipp's call):
- D: 128/64, dropout 0.15, cosine lr 1e-3, 25 epochs, from scratch, distilled (target 0.5 visit shares + 0.5 softmax
  of a 512/256 teacher, dropout 0.35, LR halving, trained on the same gen-6 window train folds), via
  `silver-prior-arch/scripts/arch.py`. Export to `combat_policy_mlp_v1` with parity < 1e-5 like the others.
Selection unchanged (lowest fold-3 val CE among A-D; B always reported as comparability arm). Gate unchanged.
