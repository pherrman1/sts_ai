# LONG_C: LONG_B continued for 200 more updates, result, 2026-11-07

Pre-registration: [PREREG.md](PREREG.md), including the "Deviation" section (combat turn cap 100 for the actors from
iteration 272 on). Evaluation: [eval/](eval/), `analyze.py` as frozen and reviewed (J PASS at 8007aa58), run on the
8,224 games of 2,048 units (`eval/games.csv`, `eval/result.json`).

**Verdict: INCONCLUSIVE.** LONG_C's final net-0420 kills the Heart in 25.49% of G1's 2,048 paired A20 seeds. LONG_B's
net-0220 kills it in 24.02%. D = +1.46 pp [−0.73, +3.66]. The sequential gate (gainer, d1 = +2 pp, look 64) ran to
the cap without accepting either hypothesis (LLR 0.73 at 2,048), and the fixed-sample bootstrap interval includes 0.

## Run
- Updates 220-419, all PPO with LONG_B's recipe, 520 sampled A20 games per update (104,000 games). Start: LONG_B's
  learner state after update 220 (`--continue`), pipeline 1, 40 cloud actor parts, learner on Philipp's PC.
- Wall time: 2026-11-06 00:49 CET to 2026-11-07 00:29 CET, including a pause from 10:42 to 16:11 CET at update 270.
- **Deviation (PREREG "Deviation"):** iterations 220-271 were played with binary 78849fcf (turn guard 500), iterations
  272-419 with 63508ecc (turn cap 100). The boundary is iteration 272, i.e. update 273 (J's D1 of the cap-100 delta
  review). Parts carry `one_combat_sha256`; all 40 parts of iteration 272 have 63508ecc.
- `screen.manifest` describes the actor binary from iteration 272 on (code_commit e387fbd4, 63508ecc). Build it from
  8219ab8b or e387fbd4, not from the branch head: the cap commits were reverted on the branch before the evaluation
  (J M1), so the head's build inputs equal bc33e470 again.
- **Correction to the PREREG ("What does not continue exactly"):** the torch RNG reseed at serve start does not change
  update 221's minibatches. The update draws no torch random numbers. Minibatches come from
  `random.Random(seed·1000003 + iteration)`, and the decision subsample from `random.Random(f"{seed}:{iteration}:{game
  seed}")`, both functions of the iteration only. The only difference from an uninterrupted LONG_B is GPU
  floating-point non-determinism (J prelaunch review, D1).
- **Stalls after the cap:** cap 100 bounds turns, not decisions per turn. Two games still hit the 1,000-decision stall
  guard and ended as combat aborts, counted as losses under LONG_B's rules:
  - iteration 361, part 37, seed 111728207, ~34 min on the worker;
  - iteration 411, part 32, ~35 min.
  Each delayed one update and resolved itself. No part exceeded the one-stall limit. Before the cap, single
  420-500-turn stalemate fights had stalled updates for up to 40 min (analysis: ledger §759).

## In-sample (descriptive, temperature 1, a different seed block per update)
- Heart rate stayed flat at ~19.8% over the run (LONG_B's last 20 updates: 19.69%). Neither pause rule fired.
- Act 2 reached fell from 80.3% to 75.7% in the last block, just above the 75.0% pause line.
- Mean floor fell from 37.6 to 36.5 from about update 260 on. That is mostly more Act-1 deaths (20% → 22%), with fewer
  deaths in Acts 3 and 4.

## Primary (eval, paired, T 0, policy alone, binary 78849fcf, turn guard 500)
| | L220 (net-0220, reused) | net-0420 | D | 95% CI |
|---|---|---|---|---|
| Heart kill | 24.02% | 25.49% | +1.46 pp | [−0.73, +3.66] |

- Sentinel: L220 replayed on seeds 111520000-111520031, 32/32 equal to LONG_B's evaluation (Heart kill, floor,
  `decisions=`). So LONG_B's L220 games are the control.
- `verify_campaign.py`: 2,048 OK, 0 missing or bad, 3 duplicates (111521670, 111521890, 111521988; the first tar was
  used), one run commit (8007aa58). Worker 26's container died at 23:22 UTC with 4 units claimed; workers 13, 22 and
  2 re-ran them after the lease.
- Every game rc 0, no combat aborts, no dropped seed.

## Secondary (descriptive, paired, 95% seed bootstrap)
| Net | Heart | D vs L220 | D vs heart1 (GH, G1) | D Act 3 cleared vs L220 | D mean floor vs L220 | CPU s/game |
|---|---|---|---|---|---|---|
| net-0270 | 23.63% | −0.39 [−2.54, +1.71] | +6.30 [+4.15, +8.45] | −0.68 [−2.98, +1.56] | −0.85 [−1.58, −0.13] | 19.9 |
| net-0320 | 23.93% | −0.10 [−2.25, +2.10] | +6.59 [+4.44, +8.79] | −0.44 [−2.78, +1.86] | −0.88 [−1.68, −0.10] | 19.6 |
| net-0370 | 25.88% | +1.86 [−0.34, +4.05] | +8.54 [+6.35, +10.69] | +0.88 [−1.51, +3.27] | +0.32 [−0.48, +1.14] | 20.3 |
| net-0420 | 25.49% | +1.46 [−0.73, +3.66] | +8.15 [+5.91, +10.40] | +0.39 [−2.00, +2.73] | −0.59 [−1.40, +0.22] | 20.6 |

Deaths by act, with Act 1 = floor < 17, Act 2 = 17-33, Act 3 = 34-50:

| Arm | Died in Act 1 | Died in Act 2 | Died in Act 3 | Reached floor 51 | Heart kills | Kill share of runs reaching 51 |
|---|---|---|---|---|---|---|
| net-0220 | 410 | 572 | 232 | 834 | 492 | 59.0% |
| net-0270 | 462 | 567 | 206 | 813 | 484 | 59.5% |
| net-0320 | 450 | 586 | 205 | 807 | 490 | 60.7% |
| net-0370 | 424 | 523 | 224 | 877 | 530 | 60.4% |
| net-0420 | 464 | 553 | 185 | 846 | 522 | 61.7% |

Act-1 deaths net-0420 vs net-0220, paired: +2.6 pp. Discordant pairs 243 vs 189, McNemar p ≈ 0.011.

## Reading (Inference)
- LONG_B's steady rise (+1.4/+3.6/+5.5/+6.7 pp over heart1 at 50/100/150/200 PPO updates) does not continue at the
  same rate. 200 more updates add at most ~2 pp, and the checkpoints are not monotone (0270 and 0320 at L220's level,
  0370 and 0420 about +1.5-1.9 pp). In-sample the Heart rate was flat the whole run.
- The trade LONG_B showed goes on: the kill share of runs reaching floor 51 keeps rising (59.0% → 61.7%) and Act-3
  deaths keep falling (232 → 185), while Act-1 deaths rise again (410 → 464). With the reward 1{Heart} an early death
  costs as much as a late one, so the policy keeps buying late conversion with early risk.
- The cap-100 deviation cannot explain the flat curve: it touched about 1 in 8,000 games, and the evaluation ran
  with the old turn guard.
- More updates of the same recipe are not the next lever. The candidates are a better critic or potential-based
  shaping (critic/PBRS thread), not an act-clear reward or lower-ascension mixing.

## Decision
- No GO: net-0220 stays the PPO baseline. net-0420 (sha256 8c0bd16c…) and net-0370 (8faba759…) are kept on the share
  (`/mnt/project-files/ppo-long-c/nets/`) as candidates for a later confirmation.
- No default change. The next step is decided with Philipp.

## Cost
- Training actors: 104,000 games, ~20-27 s each, ≈ 600-780 core-h on 40 workers.
- Evaluation: 8,224 games × ~20 s ≈ 46 core-h on 26 workers (the other 14 ran the MAX_BACKUP gate).
- Seeds: 111654400-111758399 USED (training). The evaluation reused G1's 111520000-111522047.
