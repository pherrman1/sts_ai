# LONG_B: long PPO run on combat B with a pre-trained critic, result, 2026-11-05

Pre-registration: [PREREG.md](PREREG.md), with the 2026-11-05 amendment (engine speedup during the pause, rebin,
evaluation binary). Evaluation: [eval/](eval/), `analyze.py` as frozen (K PASS of the freeze at 3ad6c943), on the
8,224 games of 2,048 units (`eval/games.csv`, `eval/result.json`).

**Verdict: GO.** LONG_B's final net-0220 kills the Heart in 24.02% of G1's 2,048 paired A20 seeds, heart1 in 17.33%:
D = +6.69 pp [+4.54, +8.79]. The sequential gate (gainer, d1 = +2 pp, look 64) accepted H1 at 576 pairs (LLR 3.14).
This is the first PPO net that beats heart1.

## Run
- 220 updates × 520 sampled A20 games (114,400 games), heart1 start (net-0000 4288d095), combat B (flat Silver 1,000,
  g7f_E root and tree prior), 40 cloud actor parts, learner on Philipp's PC (RTX 3060 Ti), pipeline 1.
- Updates 0-19 were value-only with Monte Carlo targets (`--warmup-lam 1.0`); updates 20-219 were PPO with §748's base
  recipe.
- Wall time: 2026-11-04 23:53 CET to 2026-11-05 18:28 CET. There were two pauses for Philipp's GPU: 11:21-13:19 CET at
  update 157, and 15:52-17:53 CET at update 208. Resumes used the same serve command.
- During the first pause the engine change bc33e470 was made (behaviour-preserving, K PASS). It takes the
  equivalent-copy search from O(cards²) state copies to an incremental hash check. A 1,467 s stalemate game now takes 48 s.
  - Parity: the hang replay is byte-identical apart from wall time, and the 32 G1 sentinel seeds are identical.
  - From update 157 on, the actors ran binary 78849fcf (`LONG_B/rebin` in the store). All 40 workers ran setup at
    23738b84, and none restarted its actor. So every part after the resume was played by the old d485e8eb actor process
    with the new binary file, and those parts carry no `one_combat_sha256` meta.
- With the batched git transfer (d5132ccc), the learner took 76-88 s per update instead of ~177 s. After that the
  actors set the pace, at ~3 min per iteration.
- Stalls before the fix: five single long games of 17-35 min (parts p18 it35, p37 it83, p17 it107, p25 it134, p23
  it153). Each finished on its own, so no game was lost. There were none after the fix.

## In-sample (descriptive, temperature 1, a different seed block per update)
- Heart rate went from 14.97% in the warm-up (heart1's policy, 10,400 games) to 19.69% over the last 20 updates.
- Trend: +0.31 pp per 10 updates. Entropy 0.215 → 0.297. approx-KL per update ~0.01.
- Act 2 reached fell from 83.7% to ~79-80.6%, more than the 2.4 pp replica gap in 18 of 23 blocks. Act-1 deaths rose
  from 16.3% to ~20%, and Act-3 deaths fell from 24.9% to ~20%.
- Diagnostics on the last iteration (PR #984's scripts, PC data):
  - Critic EV vs the Monte Carlo outcome by act: Act 1 0.50, Act 2 0.75, Act 3 0.65, Act 4 0.27. AUC by act: 0.63 /
    0.76 / 0.81 / 0.76. First decision AUC 0.51.
  - Advantages: ICC 0.34, effective sample ~1,510 decisions per update.
  - KL(net-0020 ∥ net-0220) = 0.43, argmax agreement 83%. Most of the KL mass is in rewards (49%) and shop (24%).

## Primary (eval, paired, T 0, policy alone)
| | heart1 (GH, G1) | net-0220 | D | 95% CI |
|---|---|---|---|---|
| Heart kill | 17.33% | 24.02% | +6.69 pp | [+4.54, +8.79] |

- Sentinel: GH replayed on seeds 111520000-111520031, 32/32 equal to G1 (Heart kill, floor, decisions=). The binary is
  78849fcf.
- `verify_campaign.py`: 2,048 OK, 0 missing or bad, 2 duplicates (111521464, 111521505; the first tar was used), 40/40
  DONE.json, one run commit (3ad6c943).
- Every game rc 0, no combat aborts, no dropped seed.

## Secondary (descriptive, paired vs GH, 95% seed bootstrap)
| Net | Heart | D Heart | D Act 3 cleared (floor ≥ 52) | D mean floor | CPU s/game |
|---|---|---|---|---|---|
| net-0070 | 18.75% | +1.42 [−0.54, +3.32] | +0.34 [−2.00, +2.64] | −1.12 [−1.88, −0.36] | 26.1 |
| net-0120 | 20.95% | +3.61 [+1.51, +5.66] | +1.12 [−1.22, +3.47] | −1.35 [−2.15, −0.55] | 26.7 |
| net-0170 | 22.80% | +5.47 [+3.42, +7.52] | +3.56 [+1.12, +6.05] | −0.70 [−1.49, +0.10] | 28.0 |
| net-0220 | 24.02% | +6.69 [+4.54, +8.79] | +3.22 [+0.73, +5.66] | −1.18 [−2.01, −0.38] | 27.0 |

Deaths by act, with Act 1 = floor < 17, Act 2 = 17-33, Act 3 = 34-50:

| Arm | Died in Act 1 | Died in Act 2 | Died in Act 3 | Reached floor 51 | Heart kills | Kill share of runs reaching 51 |
|---|---|---|---|---|---|---|
| GH | 348 | 565 | 302 | 833 | 355 | 42.6% |
| net-0070 | 407 | 560 | 270 | 811 | 384 | 47.3% |
| net-0120 | 418 | 569 | 241 | 820 | 429 | 52.3% |
| net-0170 | 417 | 528 | 253 | 850 | 467 | 54.9% |
| net-0220 | 410 | 572 | 232 | 834 | 492 | 59.0% |

Act-1 deaths net-0220 vs GH, paired: +3.0 pp. Discordant pairs 233 vs 171, McNemar p ≈ 0.002.

## Reading (Inference)
- The in-sample gain transfers to greedy play on fresh paired seeds, and it is larger there (+6.7 pp vs +4.7 pp
  in-sample). Unlike CRIT_PRE (§752), the gain does not fade at T 0.
- The gain grows steadily across the checkpoints (+1.4, +3.6, +5.5, +6.7 pp at 50/100/150/200 PPO updates), with no
  sign of a plateau at 200 updates. More updates of the same recipe are the obvious next lever.
- Where it comes from:
  - The share of runs reaching floor 51 that kill the Heart rises from 42.6% to 59.0%.
  - Act-3 deaths fall from 302 to 232.
  - The cost is more Act-1 deaths (348 → 410), the same pattern as CRIT_PRE and the in-sample drift alarm.
  - The reward 1{Heart} prices an Act-1 death the same as a later one, so this trade is consistent with the objective.
- Earlier runs had shorter horizons: screens of 30-60 updates × 512 games and K15 combat. That they never reached this
  suggests the horizon and the stronger combat mattered more than any single recipe knob. This is not tested here.

## Decision
- Per the PREREG, net-0220 (sha256 408b2982…) becomes the S1 start and the next PPO baseline.
- Its use as a production prior needs a separate production A/B and Philipp's call. No default change.
- The next PPO iteration is planned in the review thread "PPO next iteration" with Philipp.

Seeds: LONG_B 111540000-111654399 USED (training, sampled). The evaluation reused G1's 111520000-111522047 (paired, no
new seeds). Cost: ~114,400 training games ≈ 800 core-h, and the evaluation's 8,224 games ≈ 62 core-h.
