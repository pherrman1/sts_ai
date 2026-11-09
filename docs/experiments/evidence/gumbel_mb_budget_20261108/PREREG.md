# Max backup at 32k and 64k simulations under the Gumbel root (pre-registration)

Status: frozen with the run commit (see `campaign.manifest`). Follow-up to §772 (Gumbel budget check,
[../gumbel_budget_20261108](../gumbel_budget_20261108/RESULT.md)). Philipp, 2026-11-08 at 20:24 CET: "eigentlich
würde ich geren mit 32k bzw 64k messen, wie lange würde das dauern auf 40 workern ?". At 21:09 CET, after the
estimate and the proposal to split the long Awakened One and Time Eater fights by copy, he wrote: "ja verteile diese
units. dann go mit 40 workern sobald die frei sind vom anderen thread." That message is the go for 40 cloud workers.

## Question

§772 found two gains over §770's Gumbel root at 16,000 simulations (g16):
- More simulations: 32k −0.24 HP per elite or boss fight [−0.46, −0.02] and 64k −0.37 [−0.57, −0.16] (97.5%).
- Max backup with min 4 visits at 16k (g16mb): −0.29 [−0.49, −0.09] (95%), at about g16's CPU.

The combination was not run. Two questions:
- (A) Does max backup still help at 32k and 64k?
- (B) Does more budget still help on top of max backup?

The answer decides which arm the combat net's teacher should be.

## Design

- **States and copy seeds:** exactly §770's and §772's. The 1,878 act-1-3 elite and boss fights of §711's 329
  Baalorlord runs, 4 copies per fight. No new seeds.
- **Binary c28d71b7:** code 5a233efd = main 539da756 plus one change, `STS_EXPERT_FIGHTS_ARM_COPIES`. It limits a
  process to the listed arm-fight floors and copies. The combat search code (src/, include/) equals §770's and
  §772's. Inputs are the same: student_sel cf6bf7fb, expert_runs.tar 895eac8f, preset x86-64-v3 and the
  environment. `run_unit.sh` is §772's, changed only in the arms and the optional selection.
- **Why splitting keeps the pairing:** a copy's seeds depend only on (seed, floor, copy). Production's main line
  continues from copy 0 (or the first winning copy), so a copy played alone equals the same copy played together with
  the others. This was checked on three act-1 units of §772's g16mb arm set, run (a) unsplit, (b) floor 14 copy 2
  only, and (c) floor 7 plus floor 16 copies 1 and 3. Every production and arm copy, the main line's continuation
  and every sync equalled §772's records, with 0 differences across 64 production and 23 arm copies.
- **New arms (research overrides of `STS_EXPERT_FIGHTS_ARMS`):**
  - `gsh16+flat32000+mb4` (g32mb) and `gsh16+flat64000+mb4` (g64mb): §772's Gumbel root (k 16, c_visit 50,
    c_scale 1) at 32k and 64k with max backup, min 4 visits.
  - The thread-local override is used, as in §772, so production and the main line keep the process setting.
- **Comparison arms are not re-run.** They come from earlier units:
  - g32 (`gsh16+flat32000`), g64 (`gsh16+flat64000`) and g16mb (`gsh16+flat16000+mb4`) from §772's units
    (`/mnt/project-files/combat-plan/gumbel-budget/units`, 1,728 tars).
  - g16 and stage-1 production from §770's units (`/mnt/project-files/combat-plan/teacher-check/units`, 329 tars).
- **Units:** one per (run, act, arm set) for the 576 (run, act) pairs and arm sets `g32mb` and `g64mb`, with
  `STS_EXPERT_FIGHTS_ARM_ROOMS=<act>E,<act>B` as in §772. `make_units.py` (committed) projects each unit's wall time
  from §772's measured unit wall and per-copy CPU, scaling the arm's CPU by 3.32/3.15 (max backup at 16k).
  - A unit projected above 1.25 h is split. Every arm-fight copy projected above 20 min of arm CPU becomes its own
    unit (`<floor>:<copy>`), and the rest of that unit's fights and copies form one unit.
  - Result: 1,187 units (585 g32mb, 602 g64mb), 76 of them single copies.
  - Projected 332 lane-hours. The longest unit, 1655315178 act 3 g64mb copy 2 of Awakened One, is 3.25 h.
  - Simulated longest-first makespan on 160 lanes is 3.25 h (median lane 2.1 h); 3.3 h on 140 lanes.
  - `units.txt` is ordered longest first; `units_projection.tsv` lists the projections.
- **Run:** 40 cloud workers × 4 lanes, started as stage 3a releases its workers; worker.sh queue, lease 45 min.
  Share `/mnt/project-files/combat-plan/gumbel-mb-budget`.

## Endpoints and analysis (fixed; `analyze.py`)

- **Definitions:** as §770/§772.
  - HP lost per copy = entry HP − exit HP, 0 on a loss; floor-51 exits are inverted for the Act-4 heal.
  - Side value = mean over the 4 copies.
  - Drops as §711 (invalid copy, no logged exit HP, two logged fights on the floor), plus `missing_side`: any of
    copies 0-3 of any side is missing, or its unit has rc != 0.
  - Copies are merged per (run, floor, copy) across units. A copy that appears in two units must be identical (it
    must be identical by determinism); conflicts are counted and reported.
  - Units whose `.done` line has rc != 0 are excluded; the RESULT reports the tally by rc.
  - CIs: run-clustered bootstrap, 10,000 resamples, seed 20261108.
- **Reproduction (gate for the pairing):** a fight reproduces if every production copy here equals §770's copy with
  the same index in won, exit HP, exit max HP, turns, decisions, simulations and potions used. If fewer than 99% of
  the compared fights reproduce, the result is **NOT_PAIRED**; the arm − production contrasts are still reported.
- **Primary A, max backup at high budget:** mean of (g32mb − g32) and of (g64mb − g64), each with a 97.5% CI
  (Bonferroni over the two).
  - Any pair with hi < 0 → **MB_HELPS_AT_HIGH_BUDGET** (naming the pair with the lowest mean).
  - Otherwise, both with lo > −0.3 → **MB_NO_GAIN_AT_HIGH_BUDGET**.
  - Otherwise → **INCONCLUSIVE**.
- **Primary B, budget on top of max backup:** mean of (g32mb − g16mb) and of (g64mb − g16mb), each with a 97.5% CI.
  - Any with hi < 0 → **MORE_SIMS_HELP_WITH_MB**.
  - Otherwise, both with lo > −0.3 → **NO_GAIN_BEYOND_16K_WITH_MB**.
  - Otherwise → **INCONCLUSIVE**.
  - A and B are separate families: each holds its own level, and they are not corrected against each other.
  - No default change on either result. Which arm becomes the teacher target is Philipp's call.
- **Secondary (95% CIs, descriptive):** g64mb − g32mb; g32mb − g16 and g64mb − g16; every arm − production; deaths
  for the four primary contrasts.
- **Co-reported:** the arm with the lowest HP lost; deaths and potions per fight; CPU ratios; simulations per
  decision; and cuts by act, room, act × room and encounter (n ≥ 20).
  - The CPU ratios of the new arms and of §772's arms are against this campaign's production copies. g16's ratio is
    against §770's production. Arms from other campaigns ran on other machines, so cross-campaign ratios mix
    machines.

## Caveats fixed in advance

- Exploratory: these states were used before (§711/§716/§718/§770/§772), and they are the combat plan's stage-3
  test set. No training data is recorded.
- The main line is production's, as in §770/§772.
- One Gumbel setting and one max-backup setting (min 4 visits) are used at every budget, not re-tuned.
- Units can be killed by container resets. A unit that fails 4 times is reported, and its fights drop as
  `missing_side`; the RESULT lists them.
- A split unit plays production's main-line copies again, so the campaign plays some production copies two or more
  times. They must agree (`conflicts.prod`).

## Smoke (2026-11-08, binary c28d71b7 as frozen; not part of the analysis)

Four units of run 1657740070, act 1, on 4 lanes: `g32mb 14:2`, `g32mb 7,14:0,14:1,14:3,16` (together they cover the
unit), `g32mb` unsplit and `g64mb` unsplit. Result: 4 of 4 rc 0, wall 24-351 s.
- The two split units' 25 production and arm copies equal the unsplit unit's copies field for field (except CPU).
- `analyze.py` on the four units against §772's and §770's units:
  - Production reproduced in 3 of 3 compared fights (12 copies).
  - 0 conflicts of any kind, including production copies and arm copies played in two units.
  - 3 fights with all sides; the rest of §770's fights are `missing_side`, as expected in a smoke.
  - Both decisions INCONCLUSIVE (no CIs on 3 fights).
- Max backup acts: 11 of 12 g32mb copies and 12 of 12 g64mb copies differ from §772's g32 and g64 copies on the same
  seeds (won, exit HP, turns, decisions or simulations).
- Simulations per decision: g32mb 28,762, g64mb 57,815 (g32 28,474, g64 57,088).
- HP numbers on 3 fights are noise and not reported.
