# Rollout prior, playout role: candidate V as G16 + mb4's prior-playout policy only (GP) against §775's G16 + mb4 (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen with the PREREG in the run commit e6650f1f
(before any unit had run), output `results/result.json` and `results/pairs_GP.csv`. Descriptive breakdown:
`breakdown.py` (not pre-registered; §808's with the arm renamed and the bootstrap seed 20261116), output
`results/breakdown.json`. Prelaunch review: K, technically PASS (`/mnt/project-files/reviews/rollout-prior-playout-prelaunch.md`;
A1 typed go obtained 11:18 CET; W1 below).

## Run

- Run commit e6650f1f (code 432bfae4 = §775's ba705ab4 plus the research option `STS_SILVER_PLAYOUT_POLICY`, binary
  85a6cf3e, rebuilt bit-identically by the reviewer), 32 workers × 4 lanes, queue, right after prior-factory batch 2.
  The first game started at 15:05 CET on 2026-11-16 and the last ended at 17:36 CET. The 1,056 games sum to 168.2
  lane-hours. The longest game took 2.2 h (GP-111378297, finished, rc 0).
- 1,056 claims, each unit claimed once (no `.a2`). Claims snapshot: `results/claims.txt`.
- `verify_campaign.py`: 1,056 of 1,056 units OK, 0 missing, 0 bad, 0 duplicates, 0 tars for unknown units, all on
  run e6650f1f. Worker DONE files 19/32 at the snapshot (workers still idling on their armed waits) (`results/verify.txt`).
- `analyze.py` (NEW_ROOT = this campaign's units, REF_ROOT = §775's D, G16 and G32 units, CLAIMS_LIST = the snapshot):
  0 bad games, 0 env mismatches, 0 combat aborts, 0 dropped seeds.
- Review W1: the PREREG's sentinel paragraph was copied from §808 and names §799's binary and "two prior-path env
  keys". This run's sentinel is its own (binary 85a6cf3e) and `analyze.py` checks three env keys; the analysis code is
  the reviewed one, only that sentence is wrong.

## Sentinel and control reuse

32 of 32 sentinel G16 games are identical to §775's: **REUSE_VALID**. §775's 1,024 G16 games are the control. The
sentinel's CPU per run is 2.9% higher than §775's on the same games (machine speed).

## Primary

| | G16 + mb4 (§775) | GP |
|---|---|---|
| prior playouts (boss rooms, Shield and Spear) | g7f_E | V (`students/rp_V.txt`) |
| root prior, tree prior, rollout root table | g7f_E | g7f_E |
| Heart kill | 41.21% | **43.55%** |
| reach Act 4 (floor ≥ 52) | 49.22% | 50.98% |
| mean final floor | 41.58 | 42.05 |
| CPU per run | 512 s | 578 s (1.13×) |

GP − G16 = **+2.34 pp [−0.10, +4.79]** (95% seed bootstrap, 10,000 resamples). On 95 seeds only GP kills the Heart and
on 71 only G16 does. The one-sided 95% bounds are [+0.29, +4.39]. Both SPRTs reached CAP at 1,024 seeds
(nonregression LLR +2.94, just short of +2.944; gainer LLR +1.70). At CAP the PREREG decides by the one-sided bounds:
the lower bound is above 0, so the verdict is **GAIN** ("GAIN if the gainer accepts H1 (or, at CAP, the lower
one-sided 95% bound of mean d is above 0)"). `analyze.py` prints the nonregression label NOT_WORSE_3PP and the gainer
CAP; the combined rule is the PREREG's. The two-sided 95% CI touches 0: the gain is real at the pre-registered
one-sided level, small, and borderline.

Cost (co-primary, 95% CIs):

- CPU per run, GP / G16: **1.128× [1.078, 1.183]**, or 1.096× after correcting for machine speed with the sentinel.
- Gumbel simulations per run: 1.027× [1.004, 1.050] (roots 1.02×): GP's games are a little longer because they live
  longer; V's playouts cost about what g7f_E's do per step, so most of the CPU ratio is game path.
- CPU per run, quantiles (median, p90, p99, max): GP 462 / 1,261 / 2,124 / 7,822 s; G16 378 / 1,163 / 1,955 / 3,036 s.

## Secondary (95%, not gates)

| contrast | Heart (pp) | Act-4 reach (pp) | only first / only second | CPU ratio |
|---|---|---|---|---|
| GP − D (§775's A20 default) | +11.91 [+8.79, +14.84] | +9.86 [+6.64, +12.99] | 195 / 73 | 2.29× |
| GP − G16, the budget curve's 512 seeds (111378256-111378767) | +3.52 [−0.20, +7.23] | +2.54 [−0.98, +6.05] | 54 / 36 | 1.18× |
| GP − G16, the other 512 seeds (`breakdown.py`) | +1.17 [−2.15, +4.49] | | | |

**Act-4 conversion** (Heart kills per arrival, arrival = final floor ≥ 52):

| | Act-4 arrivals | Heart kills | kills per arrival |
|---|---|---|---|
| G16 | 504 | 422 | 83.7% |
| GP | 522 | 446 | 85.4% |

On the 437 seeds where both arms reach Act 4, the rates are 86.3% for G16 and 88.3% for GP. The difference is
+2.1 pp [−1.4, +5.5].

## Where GP gains (descriptive, not pre-registered)

`breakdown.py`: deaths by section of the final floor, hazard = deaths among runs reaching the section, GP − G16 with a
95% seed bootstrap (4,000 resamples).

| section | GP | G16 | GP − G16 (pp) |
|---|---|---|---|
| act 1, floors 1-15 | 96 / 1,024 | 96 / 1,024 | +0.0 (identical games) |
| act-1 boss (16) | 80 / 928 | 89 / 928 | −1.0 [−2.4, +0.4] |
| act 2, floors 17-32 | 132 / 848 | 129 / 839 | +0.2 [−1.8, +2.2] |
| act-2 boss (33) | 62 / 716 | 63 / 710 | −0.2 [−2.5, +2.2] |
| act 3, floors 34-49 | 54 / 654 | 60 / 647 | −1.0 [−3.3, +1.2] |
| act-3 boss 1 (50) | 40 / 600 | 43 / 587 | −0.7 [−3.0, +1.6] |
| act-3 boss 2 (51) | 38 / 560 | 40 / 544 | −0.6 [−3.3, +2.0] |
| act 4 (52-56) | 76 / 522 | 82 / 504 | −1.7 [−5.5, +2.2] |

Act 1's hallway is identical by construction: prior playouts run only in boss rooms and at Shield and Spear, so both
arms play the same games until the first boss. GP's gain is spread over the bosses and Act 4, the rooms where V
plays the playouts; no single section is significant. Act-4 runs that did not kill the Heart, by final floor: 52 (no
three keys) GP 6 / G16 7; 55 (Shield and Spear) 3 / 2; 56 (the Heart) 67 / 73.

## Reading

- §808 (V in all four roles) lost −3.42 pp, mainly in Act 2's hallway, where only the root and tree prior act. This
  gate puts V in the one role that touches no hallway and gains +2.34 pp: V is a better playout policy and a worse
  root/tree prior than g7f_E.
- §807's offline harness (V as playout policy, scored against a g7f_E-playout reference tree) said V was worse; that
  reference was biased toward g7f_E. The offline playout value-error test of 2026-11-16 (`one_combat
  playoutvaluebench`, 30,118 held-out factory boss / Act-4 roots × 64 playouts, reference = the played fight's score)
  said V's playout values are closer to the outcome (MSE 1,019 vs 1,217, −16%) and predicted this direction. The
  argmax Q-regret metric (V better in every role) did not separate roles. One calibration point: the value-error test
  ranks playout policies the way the game does here.
- Next (not decided here): a confirmation block on fresh seeds before a default proposal; better playout policies
  trained on the factory's playout-room states (5.44 M states from batches 1-2), ranked by the value-error test.
