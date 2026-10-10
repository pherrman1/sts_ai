# A20 Silver card strength with the next act, full scale (plan, 2026-10-10)

Written and committed before the run. It follows §420, where Silver strength
against the current act's enemies scored +0.64 floors [−0.43, +1.73] over the
teacher on 200 states (verdict SCALE) and skipped cards 25% of the time
against the teacher's 6% on those states. A deck that only has to survive the
rest of this act can afford to skip; the next act's enemies are what the card
is usually for. Philipp's instruction (2026-10-10 07:42Z): "Merge, then add
next act and scale".

## Question

Does Silver combat strength, measured against the rest of the current act
plus the next act, pick A20 card rewards better than the teacher on floor
reached, over all 970 scored states?

## Data

- **States:** the 970 states scored in §416 (TRAIN and VALIDATION sources of
  the §402 corpus, seeds 59100000..59101199; TEST stays closed): 590 in act 1,
  249 in act 2, 131 in act 3. The per-worker seed lists are in
  `silver_next_act_seeds/wNN.txt` (16 lists, round-robin over the sorted
  seeds).
- **Replay and trajectory check:** as in §416 and §420, same corpus and
  matching rule. INVALID above 5% mismatches.

## Strength score

Everything is as in PLAN-SILVER-STRENGTH.md (one teacher Silver fight per
option and encounter at ASC 20, paired redraw of the combat RNG, utility
`won · (0.75 + 0.25 · HP / max HP)`, unsupported encounters dropped for all
options), with the next act's pools added (`cardstrengthprobe` argument
`NEXT_ACT=1`):

| Current act | Added pools | Fight act |
|-------------|-------------|-----------|
| 1 or 2 | next act's weak and strong lists (simulator weights), its three elites (1/3 each), its three bosses (1/3 each) | current act + 1 |
| 3 (ASC ≥ 20) | the two act-3 bosses other than the revealed one (1/2 each), the second boss fight | 3 |

The fights start from the post-pick state with its current HP and deck; no
rests, upgrades or later cards are simulated.

**Counts:** current-act counts are unchanged from PLAN-STRENGTH.md. Next-act
counts are fixed, not read from the map (the map is not generated yet):

- acts 1 and 2: next weak 2, next strong 3, next elite 2, next boss 1;
- act 3: next boss (second boss) 1.

The score is the count-weighted mean over all pools:

`S = Σ_pool n_pool · U_pool / Σ_pool n_pool`

Tie rule and pick as before (ties go to the teacher's pick).

## Metric and decision rule

- **Metric:** selection gain in floors over the teacher's pick, 95%
  source-clustered bootstrap CI (2,000 reps), from
  `tools/a20_card_strength.py` on all finished parts.
- **Rule (primary, 970 states):**
  - `PASS` if the CI lower bound > 0. Then a learned Silver-strength card leaf
    is worth a proposal.
  - `NOT_SHOWN` otherwise.
  - `INVALID` if the trajectory check fails.
- **Diagnostics, not part of the rule:**
  - the same Silver fights scored on the current act only
    (`--current-act-only`), which is the §420 score at full scale;
  - CTM strength (§416) on the same states;
  - skip rate of the score and of the teacher; agreement; median spread;
  - gain by act and by split; CPU per state.

## Cost and provenance

- **Mechanism smoke (not scored, run before freezing):** seed 59100001 (act 2):
  170 fights, 110 s; seed 59100000 (act 3): 68 fights, 56 s, second-boss pool
  Awakened One and Time Eater. No unsupported encounters. In the act-2 state
  the skip option scored 0.29 against the next act's strong pool, against
  0.58–0.78 for the cards. Seed 59100005 (act 1): 148 fights, 89 s wall, 77 CPU-s inside fights.
- **Cost:** about 60–110 CPU-s per state, so about 25–30 CPU hours in total;
  about 25 minutes per worker on 16 workers × 4 lanes.
- **Execution:** 16 cloud workers, each self-building the frozen commit
  (Release) and running
  `run_strength.sh BINARY FROZEN OUT 59100000 1200 4 silver_next_act_seeds/wNN.txt 1 1`
  through the seed guard, into its own new folder
  `/mnt/project-files/card-strength-probe/silver-next-act-<FROZEN>/wNN/`.
  Workers keep a background watcher alive for the whole run. No new seeds.
- **Code:** `cardstrengthprobe` gains the optional `NEXT_ACT` argument (default
  0, which reproduces the §420 behaviour); the mode stays off the production
  path. `a20_card_strength.py` gains the next-act counts and
  `--current-act-only`.
