# Gumbel learned stop, whole-run gate: G16STOP against §775's G16 + mb4 (pre-registration)

Step 3 of the learned stop for the Gumbel root (step 1: `STS_SILVER_GUMBEL_STOP_TRACE`, #1023; step 2: the data run
[../gumbel_stop_data_20261110/RESULT.md](../gumbel_stop_data_20261110/RESULT.md), 1,024 G16 runs on fresh seeds).

**Authorization.** Philipp, 2026-11-10 in the learned-stop thread: "Oke go training, dann go auf 40 worker". The
gate reuses §775's seeds (no new seeds) and runs on 40 workers (his cap; the coordinator starts them).

## Question

Does the learned stop keep the A20 Heart kill rate of §775's teacher G16 + mb4 (41.21%) while it spends less
search? A cost test: the hoped result is "not worse at lower cost", not a gain.

## The stop (offline, `tools/gumbel_learned_stop.py`)

Sequential halving can stop only at a phase boundary (k 16 with 16 candidates: before the first phase or after 25, 50
or 75% of the budget). At each boundary before the last a gradient-boosted classifier (300 trees, 23 features: the
boundary and phase counts, spent share, legal actions, inherited visits, act, room, turn, score gap and its
normalised form, Q gap, leader visit share, the two priors and their gap, whether the leader stayed the same and for
how many boundaries, and three of the UCB stop's features) predicts the risk that the leader is not the full-budget
pick. Stop when the risk is below T and play the leader.

- Data: the step-2 traces, 574,741 searched roots of 1,024 runs, label `leader_is_final`.
- 4-fold cross-validation by run, out of fold (whole-root replay of the policy on the trace, CPU from the traced
  `cpu_seconds`):

| T | stopped roots | disagreement with the 16k pick | sims saved | CPU saved (root search) |
|---|---|---|---|---|
| 0.02 | 26.5% | 0.12% | 17.6% | 8.1% |
| 0.05 | 36.2% | 0.54% | 24.8% | 13.9% |
| **0.08** | **41.2%** | **1.05%** | **29.0%** | **18.6%** |
| 0.12 | 46.0% | 1.81% | 32.9% | 23.3% |
| 0.20 | 53.9% | 3.73% | 38.9% | 30.6% |

  For comparison: stopping every root at its last boundary disagrees on 23.7% of the roots and saves 39.6% CPU.
- T = 0.08 is the operating point, chosen before this gate (about the UCB stop's 0.7% disagreement, ADR-0051). The
  final model is trained on all 1,024 runs: `ggbt-10bc2f281224`, default threshold 0.08
  (`python3 tools/gumbel_learned_stop.py train TRACES --threshold 0.08 --out-dir DIR` on the extracted step-2
  traces regenerates `src/sim/search/NativeSilverGumbelStopModel.cpp`; the CV table is `results/offline_cv.json`).
- CPU saved is below sims saved because the early boundaries hold most stops and the per-root fixed cost stays.
- Offline caveat: an early stop leaves a smaller tree for the next decision's reuse, and a different pick changes the
  rest of the game. Only this gate measures the effect on play and on cost.

## Arms (`run_unit.sh`)

All arms are §775's G16 + mb4 (`gumbel_wholerun_20261108/run_unit.sh`): net-0420 (sha 8c0bd16c) as the whole
out-of-combat policy (temperature 0, no OOC MCTS), every fight with the Gumbel root (k 16) at a flat 16,000
simulations plus max backup (min 4 visits), Act 4 at the larger of that and Act 4 strong's budget (Shield and Spear
10k, Heart 40k) with its prior playouts; `one_combat bestbench 16000 1 20 SEED`.

| arm | differs from §775's G16 | where its games come from |
|---|---|---|
| G16 | nothing | §775 (code 5665d5ae, binary 0eabb014); 32 sentinel seeds rerun here |
| G16STOP | `STS_SILVER_GUMBEL_LEARNED_STOP=1` (model ggbt-10bc2f281224 at T = 0.08) in every whole-run Gumbel root, Act 4 included | this campaign |

## Seeds and units

§775's seeds 111378256-111379279 (1,024) in ascending order; smokes on 111379280-111379289 (not analysed).
`units.txt`: first the 32 sentinel units `SEED G16` for 111378256-111378287 (lines 1-32), then 1,024 units
`SEED G16STOP`. One game per unit.

## Sentinel and control reuse (ADR-0064 §742)

The 32 sentinel games replay §775's G16 games with this binary (flag off). A game's fingerprint: rc, abort flag, the
whole .log except the BEST line's timing fields, and the .err lines `[heart1_ppo] seed=` and `[silver] whole-run
Gumbel roots= sims=`. **32 of 32 identical = REUSE_VALID**: §775's 1,024 G16 games are the control. Anything else =
REUSE_INVALID: no verdict (CONTROL_INVALID); a G16 rerun on all seeds (about 146 lane-hours) needs Philipp's go.

## Primary (analyze.py, frozen with this file)

d = Heart kill G16STOP − G16 per seed. A seed counts if both games finished rc 0 with all log checks and an env
matching the arm (a combat abort is a counted loss); dropped seeds are listed, never imputed; more than 20 =
INCOMPLETE. Universe: seeds whose G16STOP unit was claimed (unit directory or claims snapshot).

Gate `tools/sprt_gate.py` **nonregression** (H0 −1.5 pp, H1 0), alpha 0.05, beta 0.05, look 64, cap = analysed seeds
(≤ 1,024), seeds gap-free in ascending order. NOT_WORSE = **NOT_WORSE**; WORSE = **WORSE**. At CAP the one-sided 95%
seed bootstrap bounds of mean d decide (10,000 resamples, seed 20261110): **NOT_WORSE_3PP** if the lower bound
> −3 pp, **WORSE** if the upper bound < 0, else **INCONCLUSIVE**. The 95% CI is always reported.

**Cost (co-primary, reported with 95% seed bootstrap CIs):** Gumbel simulations per run and CPU seconds per run,
G16STOP / G16. The CPU ratio against §775's games mixes machines, so it is also reported corrected by the sentinel's
machine speed (this campaign's G16 CPU over §775's on the 32 sentinel seeds). Stops per root and the unspent share
of the Gumbel budget from the exit line `[silver] whole-run Gumbel learned stops=`.

**Power (inference).** Paired games share the seed's maps and early fights until the first different pick; §780's
G16CAP − G16 had 200 discordant seeds of 1,024 (95% CI ±2.7 pp). With a similar discordance the SPRT (margin
1.5 pp) will probably reach CAP and the fixed-sample rule with its 3 pp margin decides. A true loss of 1 pp is not
resolvable at this size.

**Stopping.** Every seed runs; "crossed at" is reported.

## Secondary (not gates)

The primary's sprt_gate gainer (+2 pp); G16STOP − D (§775's games) with 95% CI; per arm Heart kill, act-4 reach
(final floor ≥ 52), mean floor, CPU sec per run, games over 1 h.

## Decision

No default change on this result. NOT_WORSE or NOT_WORSE_3PP with a CPU saving: G16STOP becomes the cheaper teacher
candidate (AZ data generation), and the threshold curve (T = 0.12 / 0.2) is the next question for Philipp. WORSE:
the stop stays off, and the offline disagreement is not a safe proxy. INCONCLUSIVE: report, Philipp decides.

## Cost and schedule

§775's G16 averaged 512 CPU s per run (146 lane-hours for 1,024); with the offline 18.6% root saving about 120-130
lane-hours plus 5 for the sentinel; 40 workers × 4 lanes, queue schedule, about 1-1.5 h. Share: about 1,100 new
files (tars, claims), about 50 MB.

## Smoke (local, this binary)

See `results/smoke.txt`: flag off replays §775's G16 games; flag on runs a smoke seed, prints the model banner and
the stops line, and a traced run's `gstop_risk` matches the Python model on the traced features.
