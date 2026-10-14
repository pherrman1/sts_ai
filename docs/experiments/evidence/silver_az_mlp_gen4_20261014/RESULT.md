# Gen 4 (10k teacher): self-play and training result (2026-10-14)

Philipp 2026-10-13 22:04Z: bigger net first; if no gain, 10k-sim teacher on 4 workers.

## Bigger net (gen-3 window, fold-3 val CE)
gen 3 (128/64 warm) 1.2869; 128/64 scratch 1.2878; 256/128 1.2864; 512/256 1.2838 but 28.5 vs
6.4 us per root natively (4.5x). Judged not worth it -> 10k teacher.

## Self-play (FROZEN.md, brief 9616c3b4, main f73e6ad7, binary b4586cfc)
10k flat exact, gen-3 prior K=8 w=400, root bonus off; seeds 91000000-511 nat, 91001000-511 pert.
4 workers, 22:38Z-02:50Z. 255/256 units rc 0; 400,128 roots. Unit natural-91000228 (seeds
91000228-231) lost: seed 91000228 hung at fight 24 / floor 50 in an endless
`SilverSearcher::rolloutToEnd` (draw/shuffle loop; not covered by the #522 decision loop guard);
killed after 1h40m, not rerun. Backtrace: `w03-hang-91000228.txt`. Repro:
`one_combat silverazgen 4 10000 0 OUT 91000228 natural 8 0` at f73e6ad7 with the gen-3 prior.

## Training (train/PLAN-train.md, written before data)
Window orig + x5 + g2 + g3 + g4 = 2,124,899 roots. Warm start from gen 3.
| run | recipe | best epoch | val CE |
|---|---|---|---|
| A | 2 passes | 2 | 1.2730 |
| **B** | 40 ep, patience 8, LR halving | 12 | **1.2678** |
Descriptive: 512/256 from scratch, same pack: val CE 1.2616 (epoch 16), top-1 56.9%.

## Monitors (fold 4, gen 4 = B; gen 3 in brackets)
1. orig (plain 10k teacher): CE 1.2103 [1.2192], top-1 57.2% [56.8%]. Largest per-gen gain so far
   (gen 1->2 -0.0008, 2->3 -0.0004, 3->4 -0.0089).
2. g4 held-out 1.2052 [1.2148]; g3 1.3270 [1.3313]; g2 1.3321 [1.3365]; x5 1.2363 [1.2420].
3. Mean TV gen 4 vs gen 3: 0.041 (3 vs 2: 0.036).
4. Parity pass (max |logit diff| 1.3e-6, 1,985 g4 + 3,525 orig roots); 6.6-9.6 us per root.
Model: model/combat_policy_mlp_gen4.txt sha256 3ebeab9d… (model/SHA256SUMS).

## Net-size sweep on the gen-4 window (from scratch, 40 ep / patience 8 / LR halving; fold-3 val CE)
| net | val CE | top-1 | native us/root (orig file, idle, min of 3) |
|---|---|---|---|
| 32/16 | 1.3123 | 53.3% | 3.4 |
| 64/32 | 1.2891 | 55.0% | 4.7 |
| 128/64 | 1.2718 | 56.1% | 8.8 |
| 128/64 gen 4 (warm start) | 1.2678 | 56.2% | 8.8 |
| 512/256 | 1.2616 | 56.9% | 29.8 |
