# G1: CRIT_PRE's PPO net vs heart1: result, 2026-11-03

Pre-registration: [PREREG.md](PREREG.md) (K PASS after deltas R1-R3; RUN_COMMIT 01ccb389). Analysis: `analyze.py` as
frozen, on the 4,096 games of the 2,048 units (`games.csv`, `result.json`).

**Verdict: INCONCLUSIVE.** CRIT_PRE's net-0060 kills the Heart 0.78 pp more often than heart1 (18.12% vs 17.33%), with
a 95% CI of [−1.12, +2.64]. The sequential gate (gainer, d1 = +2 pp) crossed neither bound by the cap (LLR −0.46), and
the fixed-sample CI includes 0 with a positive point estimate. The PREREG's power note expected this outcome for an
effect of ~0.7 pp.

## Data
- 2,048 units (seeds 111520000-111522047) on 8 cloud workers, 20:48-22:28 CET. `verify_campaign.py`: 2,048 OK,
  0 missing, 0 bad, 0 duplicates, 8/8 DONE.json, one run commit (01ccb389).
- Every game rc 0, no combat aborts, no dropped seed. Binary ca8db597 (main 520d4e4b), nets 4288d095 (GH) and
  1575c27e (GC), PPO mode at temperature 0, combat B (Silver 1,000 with prior).

## Primary
| | heart1 (GH) | CRIT_PRE (GC) | D = GC − GH | 95% CI |
|---|---|---|---|---|
| Heart kill | 17.33% | 18.12% | +0.78 pp | [−1.12, +2.64] |

Sequential gate (`tools/sprt_gate.py`, gainer, look 64, cap 2,048): CAP, LLR −0.46 at 2,048 pairs → fixed-sample
reading → INCONCLUSIVE (CI includes 0, D > 0).

## Secondary (paired, 95% seed bootstrap)
- **Act 3 cleared** (final floor ≥ 52): −0.63 pp [−2.88, +1.61].
- **Mean final floor:** −1.61 [−2.37, −0.85]. CRIT_PRE ends lower on average.
- **Deaths by act:**

  | Arm | Act 1 | Act 2 | Act 3 | Floor ≥ 51 |
  |---|---|---|---|---|
  | GH | 348 | 565 | 302 | 833 |
  | GC | 441 | 553 | 271 | 783 |

  Act 1 is floor < 17, Act 2 is 17-33, Act 3 is 34-50.
- **CPU per game:** 26.0 s (GH) and 24.7 s (GC).

## Reading (Inference)
- CRIT_PRE's net is not shown better than heart1 at the gate's 2 pp scale. The point estimate (+0.78 pp) matches the
  screen's in-sample D (+0.74 pp vs the control). That is consistent with a small gain, and also with none.
- The policy changed in a way the Heart rate alone hides. CRIT_PRE dies in Act 1 about 27% more often (441 vs 348) and
  reaches the last act less often, yet converts more of its late runs into Heart kills. Both nets are greedy, so this is
  a systematic change of style, not noise from sampling. The lower mean floor is the clearest paired difference in G1.
- heart1 in PPO mode at temperature 0 (the net also makes the key choices) plays at 17.3% on this engine. G0's 16.1% was
  policyStep with the key rules on the older binary, so the two are not directly comparable.

## Decision
- CRIT_PRE's net is **not adopted**, and the S1 pilot does not start from it. As pre-registered, the next PPO step is
  decided with Philipp.
- The plan's G1 rule ("one more 60-iteration block if point > 0, CI includes 0 and the in-sample A20 curve rises")
  does not apply: CRIT_PRE's in-sample curve is flat (block rates 7.7-9.0% with no trend, §751). Inference.
- No default change.

Seeds 111520000-111522047 and 111529990-111529991 USED. Cost: 4,096 games ≈ 29 core-h.
