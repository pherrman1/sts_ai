# Per-encounter budget, whole runs (H4, A4P against E0's GP16): result (2026-11-12)

This is the run of [PREREG.md](PREREG.md), frozen in run commit 0658e598 with code 4c4e42eb and binary e60e2614 (#1037,
review K PASS). It was launched about 03:55 CET on 40 workers; the last tar arrived about 06:33 CET.

- `verify_campaign.py`: 2,080/2,080 OK, 0 missing, 0 bad, 2 duplicate tars, run 0658e598 (`results/verify.txt`).
  The claims snapshot is `results/claims.txt`.
- Tail stall:
  - From about 04:40 CET, 15 A4P claims of W14, W24, W26 and W36 lost their heartbeat. Those containers had reset, or their share writes failed.
  - After the 90-minute lease the units were re-run as attempt a2.
  - Six a1 attempts ended with `rc=upload`, and their units were re-run.
  - No game result was lost or counted twice.
- `python3 -I analyze.py UNITS REF_UNITS results/result.json results/claims.txt`, where REF_UNITS is E0's extracted tars
  (`greedy_playouts_g16_20261111`, §790): 0 bad games, 0 env mismatches, 0 combat aborts, 0 dropped seeds.
- Cost: 118.7 lane-h of game CPU (H4 33.2, A4P 84.4, sentinel 1.1; plan 110-160).

## Sentinel

32 of 32 GP16 games were identical to E0's, so the verdict is **REUSE_VALID** and E0's 1,024 GP16 games are the control. The same games
took 0.99× E0's CPU here.

## Primary (alpha 0.025 per arm)

| | GP16 (E0, §790) | H4 | A4P |
|---|---|---|---|
| Heart kill | 35.74% | 36.13% | 37.30% |
| Act-4 reach (final floor ≥ 52) | 46.29% | 43.85% | 46.29% |
| Mean final floor | 40.75 | 40.27 | 40.75 |
| CPU s per run (mean) | 143.3 | 116.8 | 296.7 |
| CPU s per run median / p90 / p99 / max | 132 / 300 / 431 / 587 | 88 / 248 / 423 / 3,865 | 142 / 729 / 1,311 / 3,565 |
| Losses by final floor ≤ 17 / ≤ 34 / ≤ 51 / ≥ 52 | 201 / 209 / 140 / 108 | 198 / 217 / 160 / 79 | 201 / 209 / 140 / 92 |

- **H4 − GP16: +0.39 pp, 95% CI [−2.54, +3.22]** (= the one-sided 97.5% bounds).
  - 112 seeds kill only with H4, 108 only with GP16.
  - The nonregression SPRT reached CAP at 1,024 (LLR +0.81). The lower bound is above −3 pp, so the verdict is **NOT_WORSE_3PP**.
  - Act-4 reach −2.44 pp [−5.27, +0.49]; final floor −0.48 [−1.38, +0.42]. The gainer SPRT reached CAP (LLR −0.58).
  - **Cost: 0.815× CPU [0.764, 0.883]** (0.824× machine-corrected) and 0.678× the Gumbel simulations.
  - The maximum (3,865 s, seed 111379055) is a normal game, not an abort: a floor-41 loss with 11.6M simulations, about 330 µs per simulation, so one slow fight.
- **A4P − GP16: +1.56 pp [+0.10, +3.12]**.
  - 39 seeds kill only with A4P, 23 only with GP16.
  - The gainer SPRT reached CAP (LLR +1.91). The one-sided 97.5% lower bound is above 0, so the verdict is **PASS**.
  - The nonregression SPRT accepts H1 (NOT_WORSE) at 832.
  - **Cost: 2.07× CPU [2.00, 2.15]** (2.09× machine-corrected), at equal simulations (1.004×).

## Secondary

- **Act 1-3 are identical in A4P and GP16.** Act-4 reach, the floor of every Act 1-3 loss, and the losses by floor are equal, with an act-4 reach CI of [0, 0]. That is expected: A4P differs from GP16 only from the first Act-4 decision on.
  - So A4P − GP16 is an Act-4 conversion test. Among the 474 Act-4 runs, GP16 converts 77.2% and A4P 80.6% (+16 Heart kills).
  - A4P's extra CPU (+153 s per run on average) is about 330 s per Act-4 run, in line with §781's 350-415 s for Act 4 strong.
- **A4P − H4: +1.17 pp [−1.66, +4.00]**, CPU 2.54×.
- **A4P − G16 (§775's G16 + mb4 games, same seeds, sentinel of E0): −3.91 pp [−6.35, −1.46]**, at 0.58× the CPU
  (297 vs 512 s). G16's lead over GP16 (5.47 pp) splits about 1.6 pp to Act-4 prior playouts and about 3.9 pp to
  Act 1-3 prior playouts. The Act 1-3 share works through reach (G16 49.22% vs 46.29%) and the HP and deck carried into Act 4.
- **H4's losses move from Act 4 to Act 3** (79 vs 108 at floor ≥ 52, 160 vs 140 at 35-51). Act-4 reach drops by 2.4 pp, and
  the Act-4 conversion rises (H4 82.4% of 449 Act-4 runs vs GP16 77.2% of 474). A plausible reading (inference) is that weaker
  runs now die before Act 4.

## Interpretation (Inference)

- **Hallway fights take less of the CPU than step 0's map suggested.** H4 cut 32% of the simulations but only 18.5% of
  the CPU, because hallway simulations are the cheap ones. The Heart rate held, so fewer hallway simulations are free to
  this precision. They are worth about 27 s per run.
- **Act-4 prior playouts buy about 1.6 pp for about 150 s per run.** That is a real gain, but at the PPO budget it is
  expensive. Most of the prior-playout value sits in Act 1-3 bosses (about 3.9 pp), where E0 took it out.
- **Distance to the goal.** H4 + A4P combined would be about 37% at about 270 s (not run). That is still far from 40% at about 140 s.
  The cheaper candidates now are:
  - the proven-win stop, which cuts Act-4 CPU without losing wins;
  - prior playouts in Act 1-3 bosses only at a lower budget (the larger value share);
  - Act-4 budgets on top of A4P (Track 2).

## Decision

By the pre-registered rule, H4 is NOT_WORSE_3PP and A4P is PASS. There is no default change; both flags stay unset by default.

- Hallway sims 4,000 joins the cheap-combat stack. Per the PREREG, a lower hallway budget (2,000) and elite budgets come next.
- Act-4-only prior playouts join the stack at their CPU. A combined arm (H4 + A4P) and Act-4 budgets on top are next. Philipp's go for compute covers per-encounter budgets.
- Review notes from #1037:
  - R2: no unit test for the two flags. Covered at run time by run_unit's banner and err checks.
  - R3: `STS_SILVER_PRIOR_PLAYOUT_ACTS=1,2,3,4` behaves as unset but still prints the "only in acts" line. Both are documented here and stay as follow-ups.
