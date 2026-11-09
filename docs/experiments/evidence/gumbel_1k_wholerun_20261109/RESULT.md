# Gumbel 1k in whole runs: G16 + mb4 at 1,000 simulations against combat B (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen (325c62b3, committed before any unit had
finished), output `results/result.json`. Prelaunch review: J, PASS (run in parallel with the launch, as the PREREG
says).

## Run

- Run commit dc08a78e (code 13bb97ec, binary b5090b16 from the share's binary cache), 40 workers × 4 lanes, queue. The
  first game started at 23:48 CET, the last ended at 23:54 CET on 2026-11-09. Game wall time sums to 5.4 lane-h; the
  longest game took 111 s (G1-111378363).
- `verify_campaign.py`: 512 of 512 units OK, 0 missing, 0 bad, 0 duplicates, all on run dc08a78e. Every unit was
  claimed once (claims snapshot `claims.txt` on the share; `claims/` removed after it).
- `analyze.py`: 512 paired seeds, 0 drops, 0 combat aborts.

## Primary

| | B1 (combat B) | G1 (Gumbel 1k) |
|---|---|---|
| Heart kill | 21.88% | **22.27%** |
| reach Act 4 (floor ≥ 52) | 33.59% | 29.69% |
| mean final floor | 36.11 | 35.30 |
| CPU per run | 19.1 s | 18.2 s (0.95×) |

G1 − B1 = **+0.39 pp [−3.52, +4.10]** (95% seed bootstrap, 10,000 resamples), 49 seeds only G1 kills, 47 only B1 →
**NO_DIFFERENCE_SHOWN**.

## Secondary

- Against §775's arms on the same 512 seeds (§775's games, binary 0eabb014):

  | contrast | Heart (pp) | Act-4 reach (pp) | CPU ratio |
  |---|---|---|---|
  | B1 − D | −8.98 [−12.89, −5.08] | −7.62 [−11.91, −3.32] | 0.077× |
  | G1 − D | −8.59 [−12.30, −4.88] | −11.52 [−15.43, −7.62] | 0.074× |
  | B1 − G16 + mb4 | −18.55 [−22.85, −14.26] | −15.04 [−19.14, −10.94] | 0.038× |
  | G1 − G16 + mb4 | −18.16 [−22.27, −14.26] | −18.95 [−23.05, −14.84] | 0.036× |

  D 30.86%, G16 + mb4 40.43% on these seeds. G16 + mb4 costs 509 s per run, 26.6× B1's 19.1 s (J's prelaunch note
  N2, about 50×, came from the first, shorter seeds).
- G1 − B1 Act-4 reach −3.91 pp [−8.01, +0.20], final floor −0.80 [−2.33, +0.72]. Heart kills per Act-4 arrival: B1
  65.1%, G1 75.0% (descriptive; the Act-4 subsets differ).
- G1 searched 479 roots and 442,257 simulations per run (about 924 per root, with tree reuse). No combat stalls in
  either arm.
- B1's 21.88% is below §760's 25.49% for net-0420 under combat B. Those were other seeds (111520000-111522047) on
  binary 78849fcf; the difference, −3.6 pp, is within about two standard errors of two independent 512- and
  2,048-seed rates.

## Reading (Inference)

At combat B's budget the Gumbel root (k 16, max backup 4) neither helps nor costs: its Heart rate is B1's within
±4 pp. §775's +9.57 pp of G16 + mb4 over D, and its +18.6 pp over B1 here, come from the 16× larger budget and Act 4
strong's budgets, not from the Gumbel root at equal budget. Both 1,000-simulation arms are about 9 pp below the A20
default combat D, which uses 10,000 simulations with the learned stop at 13× B1's CPU.

## Decision

**NO_DIFFERENCE_SHOWN.** No default change. The Gumbel root at 1,000 simulations is not a candidate for the PPO
actors' combat. Seeds: §775's first 512 (111378256-111378767) reused, no new seeds. Cost: 5.4 lane-hours.
