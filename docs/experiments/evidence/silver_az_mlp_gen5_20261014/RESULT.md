# Gen 5 (20k teacher, 128/64): self-play and training result (2026-10-14)

Philipp 07:40Z "gen 5 at 20k in the same net", 8 workers (card). Frozen: FROZEN.md (brief d42b67ec, f73e6ad7,
binary b4586cfc, prior gen 4 3ebeab9d, per-unit timeout 9000 s). Seeds 94000000-511 nat, 94001000-511 pert.

## Self-play
8 workers, ~07:52-10:10Z. 256/256 units rc 0, no timeouts, all tar shas match. 393,757 roots.

## Training (train/PLAN-train.md, written before training)
Window orig + x5 + g2 + g3 + g4 + g5 = 2,518,656 roots; warm start from gen 4. The repo `pack` ran out of
memory at this size (15 GB container); packed with `train/silver_az_mlp_lowmem.py`, identical format
(per-unit edge blocks instead of one array per edge).
| run | recipe | best epoch | val CE (fold 3) |
|---|---|---|---|
| A | 2 passes, dropout 0.35 | 1 | 1.2557 |
| B | gen-4 recipe (40 ep, patience 8, LR halving), dropout 0.35 | 14 | 1.2496 |
| **C** | B with dropout 0.15 (architecture thread) | 7 | **1.2439** |
C is gen 5 by the pre-declared rule.

## Offline gate and monitors (fold 4; gen 4 in brackets)
1. orig (plain 10k teacher): **C 1.1954** [1.2103], top-1 57.7% [57.2%]; B (gen-4-comparable) 1.2051. Gate
   (must improve on gen 4): PASS for both B and C.
2. Per source, C [gen 4]: g5 1.1543 [1.1763]; g4 1.1875 [1.2052]; g3 1.3278 [1.3270]; g2 1.3331 [1.3321];
   x5 1.2257 [1.2363]. B: g5 1.1676, g4 1.1995.
3. Mean TV gen 5 vs gen 4: C 0.060, B 0.041.
4. Parity pass (max |logit diff| 1.6e-6, 1,117 g5 + 3,525 orig roots); 7.6 us/root (gen 4 7.1, same run).
Model: model/combat_policy_mlp_gen5.txt sha256 5e9f975a… (model/SHA256SUMS; run-B checkpoint kept).

Per-gen change in orig fold-4 CE: 1->2 -0.0008, 2->3 -0.0004, 3->4 (10k) -0.0089, 4->5 (20k) -0.0097 B / -0.0149 C
(C includes the dropout change, so B is the teacher-only comparison).

Note (2026-10-14 11:45Z): the architecture thread later found dropout 0.15 vs 0.35 differs by about the size of
seed-to-seed noise (second seed at 0.15: 1.2673 vs first 1.2609 on the gen-4 pack). Single-seed B vs C here is
therefore not evidence that dropout helped; the teacher-only comparison is B. Gen 6 keeps both arms.
