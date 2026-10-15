# A20 Silver combat-strength card pilot (plan, 2026-10-09)

Written and committed before the pilot run. It follows §416, where CTM combat
strength tied the teacher's card picks (+0.14 floors [−0.24, +0.54]). The CTM
is broken at ASC 20 and barely separated the options (median utility spread
0.008). Philipp asked to measure strength with Silver instead (2026-10-09
21:38Z: "Yes let's do it with silver").

## Question

When each option's strength is measured with real teacher Silver fights at
A20, does it pick card rewards better than the teacher on floor reached? Is
it better than CTM strength on the same states?

## Data

- **States:** 200 of the 970 §416 scored states, chosen by the lowest
  sha256(`a20-card-silver-pilot-v1:{seed}`). The list is in
  `silver_pilot_seeds.txt`. It contains TRAIN and VALIDATION sources only; TEST
  stays closed.
- **Replay and trajectory check:** as in §416, with the same corpus and the
  same matching rule. INVALID above 5% mismatches.

## Strength score

Everything is as in PLAN-STRENGTH.md (pools, simulator weights, node counts,
weighted average, tie rule, unsupported handling), except the per-encounter
utility:

- **Fights:** one teacher Silver fight per option and encounter (`SILVER_REPS=1`).
  - It starts from the post-pick state at the run's own ascension (20), with
    the corpus teacher's budget and learned stop (`vwinRunBossArm`).
  - The room is MONSTER, ELITE or BOSS to match the pool.
- **Paired randomness:** the fight's combat RNG streams are redrawn with
  sha256(`card-strength-silver-v1:{seed}:{decision}:{encounter}:{r}`). The
  same draw is used for every option of a state, so option differences are
  paired.
- **Utility:** `u = won · (0.75 + 0.25 · terminal HP / max HP)`.
- **Invalid fights:** an invalid or undecided fight marks that encounter
  unsupported for the state, and it is dropped for all options.

The mechanism smoke on one state (seed 59100001) gave 85 fights, all valid,
in 52 CPU-s. Skip scored 0.54 against 0.62 for the cards, a spread about 10×
the CTM's. That smoke is not scored.

## Metric and decision rule

- **Metric:** selection gain in floors over the teacher's pick, with a 95%
  source-clustered bootstrap CI (2,000 reps). Same code as §416
  (`tools/a20_card_strength.py --only-seeds silver_pilot_seeds.txt`).
- **Comparator:** CTM strength (§416 run) scored on the same 200 states with
  the same `--only-seeds` filter.
- **Pilot verdicts:**
  - `PASS` if the Silver gain CI lower bound > 0.
  - `SCALE` if not PASS, but the Silver gain is ≥ +0.30 floors and higher than
    CTM strength on the same states. The next step would then be the full 970
    states, on Philipp's go.
  - `STOP` otherwise.
  - `INVALID` if the trajectory check fails.
- **Diagnostics:**
  - agreement with the teacher;
  - skip rate;
  - median option spread;
  - gain by act;
  - CPU per state.

## Cost and provenance

- **Cost:** about 65 CPU-s per state (replay plus about 70–90 fights), so
  about 3.6 CPU hours. That is about 1 hour on this thread's 4 cores. No new
  seeds.
- **Command:** `run_strength.sh BINARY FROZEN OUT 59100000 1200 4 silver_pilot_seeds.txt 1`,
  through the seed guard.
- **Code:** `cardstrengthprobe` with `SILVER_REPS`. The mode stays default
  off; CTM mode is unchanged apart from an extra `cpuSeconds` column.
- **Deviation from the thread message:** the message said about 100 states.
  200 are used because the measured cost allows it inside about an hour, and
  the CI halves only with about 4× the states.
