# Rollout prior on G16 targets, stage 1: result (2026-11-15)

**Verdict (offline, roots only): candidates found.** A g7f_E-shaped MLP trained on G16 + mb4 visit shares picks root
actions with much lower regret than g7f_E in every playout encounter (playout rooms 1.884 vs 2.449 max-backed Q,
−0.565). Completed-Q targets and auxiliary heads do not beat plain visit shares. Two candidates go to stage 2 (V and
its boss fine-tune X-B), which needs Philipp's go. Root regret does not show that playouts improve.

[PREREG](PREREG.md) · data: T1 freeze (702 units, sha256 3089cacf…), pack sha256 79761e82… (3,120,098 multi-edge
roots, 19,583,292 edges) · code: branch claude/project-thread-6o0swp, training at 9586078 · V and CQP on 4 cloud CPU
threads (85 s per epoch), the rest on the PC RTX 3060 Ti (~16 s per epoch, 19:47-20:42 CET, [pc_grid.sh](pc_grid.sh)) ·
numbers: [results/summary.json](results/summary.json), one `*.train.json` per run.

## Checks

- Feature parity: on 50,000 packed roots, g7f_E's softmax recomputed from the packed features matches the recorded
  root prior to 3.8e-7, with 0 argmax mismatches ([results/parity.json](results/parity.json)). The states are those
  g7f_E saw in play.
- Export parity for V and X-B: checkpoint vs artifact 7.2e-7 on 20,000 validation roots; artifact vs native
  `silverpolicymlpcheck` 8.3e-7 / 1.1e-6 on 2,874 roots, with 0 argmax mismatches ([results/parity_V.json](results/parity_V.json),
  [results/parity_X-B.json](results/parity_X-B.json)).
- Validation: 310,371 roots, 90,486 of them in playout rooms. The gate holdout (split 0) was not read.

## Results (validation, final checkpoint; q_regret in Silver score units, lower is better)

| run | target | playout backed | playout mean | playout top-1 | all backed | all mean |
|---|---|---|---|---|---|---|
| R0 g7f_E | (recorded prior) | 2.449 | 1.992 | 39.0 % | 1.952 | 1.619 |
| **V** | visits | **1.884** | 1.673 | 41.6 % | **1.364** | 1.269 |
| CQP | cq:paper, backed | 2.081 | 1.869 | 42.8 % | 1.505 | 1.396 |
| CQ30 | cq:30, backed | 1.995 | 1.712 | 42.5 % | 1.453 | 1.280 |
| CQ10 | cq:10, backed | 1.988 | 1.665 | 41.9 % | 1.474 | 1.265 |
| CQ30m | cq:30, mean | 2.150 | 1.715 | 40.9 % | 1.585 | 1.281 |
| X-Q | V + Q head | 1.889 | 1.678 | 41.5 % | 1.362 | 1.271 |
| X-SH | V + short-horizon head | 1.965 | 1.743 | 40.7 % | 1.464 | 1.357 |
| X-QSH | V + both | 1.965 | 1.750 | 40.7 % | 1.441 | 1.341 |
| S1 | V, seed 1 | 1.893 | 1.678 | 41.6 % | 1.367 | 1.272 |
| X-B | V + 3 epochs on playout rows | **1.876** | 1.669 | 41.6 % | 1.373 | 1.278 |

Per playout encounter, V against g7f_E (backed): Hexaghost 0.83 / 1.11, Slime Boss 1.82 / 2.31, Guardian 1.53 / 2.10,
Champ 1.53 / 2.06, Automaton 1.92 / 2.47, Collector 2.09 / 2.81, Awakened One 2.54 / 3.37, Donu and Deca 1.52 / 2.16,
Time Eater 1.74 / 2.30, Shield and Spear 2.25 / 2.88, Heart 2.05 / 2.42. V is lower in all 11.

## Decisions (PREREG rules)

- **Target:** V (visits). Every cq target is worse by 0.10-0.27 under backed Q. CQ10's mean regret on playout rows
  (1.665) is 0.008 below V's, but its backed regret is 0.10 worse, so the rule picks V.
- **Seed spread:** V vs S1 is 0.009, about T1's spread. The rule's 0.01 threshold is about one spread.
- **Aux heads:** none kept. The Q head ties (+0.005). The short-horizon / fight-end head is worse by 0.08 backed and
  0.07 mean, alone and combined.
- **Candidates:** V (−0.565 vs R0) and X-B (better than its parent V by 0.008; that is within one seed spread, so it is
  a near-duplicate of V and not a clearly different net).
- **NO_ROOT_HEADROOM does not apply.** Stage 2 is next and needs Philipp's go.

## CPU per call

The native kernel skips inactive ReLU units. On the same 2,874 roots (17,026 edges), V and X-B average 22.3 active h1
units of 128 (g7f_E 20.3) and 18.0 active h2 units of 64 (g7f_E 22.1). Timed with `silverpolicymlpcheck`, the best of
5 runs on the cloud machine gives g7f_E 7.97 µs per root, V 8.42 and X-B 8.10. Single runs vary by up to 60 %, so read
this as "roughly equal, at most ~5 % more". Stage 2 measures CPU per search directly.

## Reading (Inference)

- G16's choices hold structure g7f_E does not capture, and an MLP of the same size learns much of it. V comes
  close to the T1 transformer on roots (all-rows backed regret 1.364 here; T1 reported 1.286 on its own validation
  rows, which also count single-edge rows, so the two are not directly comparable).
- Plain visit shares beat completed-Q targets for this net. Under sequential halving, the visit shares mark the
  finalists, which is what an argmax needs. The completed-Q softmax sharpens toward a noisy Q winner among them, and
  the sharper the target, the worse the result (CQP < CQ30 < CQ10 < V).
- Training-only aux heads on a 128-wide trunk cost capacity rather than adding signal at this data size. This matches
  §771 (a value loss hurts the policy in a shared trunk).

## Next: stage 2 (proposal; needs Philipp's typed go with worker count)

§798's harness on §797's 256 games (seeds 111980000-111980255, sentinel), arms `asplayed:4000` (g7f_E), `st:4000`
(V, `STS_AZGEN_ROLLOUT_STUDENT`), `ste:4000` (X-B, `STS_AZGEN_ROLLOUT_STUDENT_ENC` mapping all 11 playout encounters,
so it needs no C++ change) and `st:16000` (V, against §797's P1 16k). Primary: Δ loss at 4k against asplayed, with a
run-clustered bootstrap. Caveats: the student arms use `nativeSilverPolicyPriorWith` (no argmax hook, no #1065 pick
cache), so their CPU is overstated against asplayed and the comparison is at equal simulations. The reference tree
uses g7f_E playouts, so it favours g7f_E. Estimate 70-100 lane-hours.
