# G12 / Heart 24k: §775's G16 + mb4 at 12,000 simulations with the Heart at 24,000 (G12H24) against §775's G16 + mb4 (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen with the PREREG in the run commit 495d4d66
(before any unit had run), output `results/result.json`. Descriptive breakdown: `breakdown.py` (not pre-registered),
output `results/breakdown.json`. Prelaunch review: K, PASS.

## Run

- Run commit 495d4d66 (code ba705ab4, binary 97aec5b5 from the share's binary cache), 40 workers × 4 lanes, queue. The
  first game started at 22:48 CET on 2026-11-13 and the last ended at 00:04 CET on 2026-11-14. The 1,056 games sum to
  104.1 lane-hours (PREREG: about 110-125). The median game took 4.2 min and the longest 39.7 min (G12H24-111378648).
  No game came near the 8 h timeout.
- 1,057 claims: every unit ran once, except 111378921, whose first attempt lost its heartbeat when worker 18 dropped
  out. The watchdog released it after 6 min, and worker 5 ran it again (`.a2`). Claims snapshot: `results/claims.txt`
  (`claims/` removed after it). 40/40 worker DONE files.
- `verify_campaign.py`: 1,056 of 1,056 units OK, 0 missing, 0 bad, 0 duplicates, 0 tars for unknown units, all on run
  495d4d66.
- `analyze.py` (NEW_ROOT = this campaign's extracted units, REF_ROOT = §775's D, G16 and G32 units, CLAIMS_LIST = this
  campaign's snapshot): 0 bad games, 0 env mismatches, 0 combat aborts, 0 dropped seeds.

## Sentinel and control reuse

32 of 32 sentinel G16 games are identical to §775's: **REUSE_VALID**. §775's 1,024 G16 games are the control. The
sentinel's CPU per run is 3.3% higher than §775's on the same games (machine speed).

## Primary

| | G16 + mb4 (§775) | G12H24 |
|---|---|---|
| simulations, acts 1-3 | 16,000 | 12,000 |
| Shield and Spear | 16,000 | 12,000 |
| the Heart | 40,000 | 24,000 |
| Heart kill | 41.21% | **38.96%** |
| reach Act 4 (floor ≥ 52) | 49.22% | 48.73% |
| mean final floor | 41.58 | 41.16 |
| CPU per run | 512 s | 352 s (**0.69×**) |

G12H24 − G16 = **−2.25 pp [−5.08, +0.59]** (95% seed bootstrap, 10,000 resamples, seed 20261113). On 97 seeds only
G12H24 kills the Heart and on 120 only G16 does. The one-sided 95% bounds are [−4.69, +0.10]. The nonregression SPRT
reached CAP at 1,024 seeds (LLR −1.09). The lower bound is not above −3 pp and the upper bound is not below 0, so the
verdict is **INCONCLUSIVE**. The gainer SPRT accepted H0 at 640 seeds (NOT_SHOWN).

Cost (co-primary, 95% CIs):

- CPU per run, G12H24 / G16: **0.688× [0.655, 0.722]**, or 0.666× after correcting for machine speed with the
  sentinel.
- Gumbel simulations per run: 0.725× [0.704, 0.746] (roots 0.99×).
- CPU per run, quantiles (median, p90, p99, max): G12H24 253 / 805 / 1,276 / 2,383 s; G16 378 / 1,163 / 1,955 /
  3,036 s.

## Secondary (95%, not gates)

| contrast | Heart (pp) | Act-4 reach (pp) | only first / only second | CPU ratio |
|---|---|---|---|---|
| G12H24 − D (§775's A20 default) | +7.32 [+4.30, +10.35] | +7.62 [+4.49, +10.64] | 165 / 90 | 1.39× |
| G12H24 − G16, the budget curve's 512 seeds (111378256-111378767) | −4.30 [−8.20, −0.39] | −1.56 [−5.66, +2.34] | 43 / 65 | 0.68× |
| G12H24 − G16, the other 512 seeds (`breakdown.py`) | −0.20 [−4.11, +3.72] | | | |

**On the budget curve's 512 seeds**, G12H24 sits between 8,000 and 16,000. These are different games on the same seeds,
not paired with this campaign:

| arm | Heart kill | CPU per run |
|---|---|---|
| G8S (§781) | 34.38% | 315 s |
| G12H24 | 36.13% | 345 s |
| G16 + mb4 (§775) | 40.43% | 509 s |
| G32 (§775) | 39.26% | 864 s |

**Act-4 conversion** (Heart kills per arrival, arrival = final floor ≥ 52):

| | Act-4 arrivals | Heart kills | kills per arrival |
|---|---|---|---|
| G16 | 504 | 422 | 83.7% |
| G12H24 | 499 | 399 | 80.0% |

On the 393 seeds where both arms reach Act 4, the rates are 84.5% for G16 and 84.2% for G12H24. The difference is
−0.3 pp [−4.1, +3.6].

## Where G12H24 loses (descriptive, not pre-registered)

`breakdown.py`: deaths by section of the final floor, hazard = deaths among runs reaching the section, G12H24 − G16
with a 95% seed bootstrap (4,000 resamples), as Test 3's breakdown.

| section | G12H24 | G16 | G12H24 − G16 (pp) |
|---|---|---|---|
| act 1, floors 1-15 | 103 / 1,024 | 96 / 1,024 | +0.7 [−1.0, +2.3] |
| act-1 boss (16) | 85 / 921 | 89 / 928 | −0.4 [−2.1, +1.4] |
| act 2, floors 17-32 | 138 / 836 | 129 / 839 | +1.1 [−1.3, +3.6] |
| act-2 boss (33) | 65 / 698 | 63 / 710 | +0.4 [−2.0, +2.9] |
| act 3, floors 34-49 | 60 / 633 | 60 / 647 | +0.2 [−2.5, +3.0] |
| act-3 boss 1 (50) | 35 / 573 | 43 / 587 | −1.2 [−3.8, +1.3] |
| act-3 boss 2 (51) | 39 / 538 | 40 / 544 | −0.1 [−3.0, +2.8] |
| act 4 (52-56) | 100 / 499 | 82 / 504 | +3.8 [−0.2, +7.7] |

The Act-4 runs that did not kill the Heart, by final floor:

| final floor | G12H24 | G16 | Inference from the floor (the logs carry no key status; no run died on floors 53-54, runs ending on 52 kept HP, e.g. G12H24-111378516 with 42; 55 and 56 match the smoke's per-root budget trace) |
|---|---|---|---|
| 52 | 8 | 7 | run ended after Act 3 without all three keys |
| 55 | 5 | 2 | Shield and Spear |
| 56 | 87 | 73 | the Heart |

Heart kills grouped by which arm reached Act 4:

| seeds | number | G16 kills | G12H24 kills |
|---|---|---|---|
| both reach Act 4 | 393 | 332 (84.5%) | 331 (84.2%) |
| only G16 reaches it | 111 | 90 (81%) | — |
| only G12H24 reaches it | 106 | — | 68 (64%) |

Acts 1-3 lose about as often in both arms: Act-4 reach differs by −0.49 pp [−3.32, +2.25]. The Heart-kill gap sits in
Act 4, but not on the seeds where both arms arrive. There, G12H24 kills the Heart as often as G16. The gap comes from the
seeds that only one arm brings to Act 4: G12H24 converts 64% of those and G16 81% (different seeds, unpaired).

## Reading (Inference)

- G12H24 costs 0.69× G16's CPU and plays 2.25 pp below it. The interval reaches −5.1 pp, so the test cannot show that
  G12H24 is at most 3 pp worse. It does not show that it is worse either.
- No conversion loss is visible on the 393 seeds where both arms reach Act 4: 84.2% against 84.5%, −0.3 pp [−4.1, +3.6].
  This is not an isolated Heart contrast. The seeds are selected by an outcome, the arrival states differ (12,000 against
  16,000 simulations from the first root), Shield and Spear differ too (12,000 against 16,000), and the interval does not
  exclude a loss of a few pp. The Heart's share of the CPU saving is small (the simulations ratio is 0.725, against 0.75
  for 12,000/16,000 alone).
- The 12,000 simulations in acts 1-3 are not visibly worse: Act-4 reach differs by −0.49 pp [−3.32, +2.25] (each
  section's interval spans about ±2-3 pp and contains 0). G12H24's extra Act-4 arrivals convert worse (64% against 81%). That fits weaker arrival
  states (HP, deck), but these are different seeds in each group. The breakdown cannot tell whether the arrival state
  or the 24,000-simulation Heart on harder states is the cause.
- On the budget curve's 512 seeds, G12H24 is consistent with the CPU curve between G8S and G16. Linear in CPU between
  them predicts 35.3% at 345 s, and G12H24 has 36.1% (±4 pp on 512 seeds; G8S's games are not paired with these), so
  there is no sign of a saving beyond the curve. On the other 512 seeds
  the two arms are nearly equal (−0.20 pp). The difference between the halves (4.1 pp) is within what chance gives at
  this size (about 1.5 standard errors).
- §785's caveat applies here too. Every whole-run arm compared with these 1,024 G16 games came out 2.3-4.7 pp below
  them (§777, §780, §783, §785, and now −2.25 pp). This result alone cannot tell whether G16's draw on these seeds is
  favourable.

## Decision

**INCONCLUSIVE** (Heart kill −2.25 pp [−5.08, +0.59] at 0.69× CPU). No default change (PREREG: none in any case).
G16 + mb4 stays the teacher candidate. G12H24 is not taken as a cheaper teacher. Following the PREREG, the follow-ups
are Philipp's call:

- 16,000 in acts 1-3 with the Heart at 24,000. This saves little CPU; no conversion loss was visible where both arms
  arrive, but that was not an isolated Heart contrast.
- 12,000 with the Heart at 40,000. This would separate the Heart from the acts-1-3 budget.
- More seeds for G12H24 against G16. This would narrow the interval.

`STS_SILVER_ACT4_HEART_BUDGET` stays a research option (default 40,000).

Seeds: §775's 111378256-111379279 reused (no new seeds). Cost: 104.1 lane-hours.
