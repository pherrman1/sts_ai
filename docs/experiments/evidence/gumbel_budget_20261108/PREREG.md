# Gumbel budget check: 32k and 64k simulations under the Gumbel root (pre-registration)

Status: frozen with the run commit (see `campaign.manifest`). Follow-up to the combat plan's stage-1 teacher check
(§770 TEACHER_FOUND, [../teacher_check_20261108](../teacher_check_20261108/PREREG.md)). Philipp asked for it on
2026-11-08 at 13:00 CET ("Kannst du dann einen neuen thread starten der auf 40 workern tested, ob wir mit noch mehr
sims noch besser werden mit gumbal? Maybe 32k und 64k sims auf den gleichen kämpfen wie davor, oder wenn das zu lange
dauert, auch nur ein Bruchteil davon"); that message is the go for 40 cloud workers. The max-backup arm was added
at his request at 13:25 CET ("Ja Schlag das mal vor", answering whether the root can take the best line's value
instead of the mean).

## Question

§770 found gsh16+flat16000 (Gumbel-top-16 root, sequential halving, 16,000 simulations) 0.88 HP per elite or boss fight
better than production [−1.20, −0.57], with 4× budget under the Gumbel root worth −0.73 [−0.93, −0.52] (16k − 4k).
Does the gain keep growing at 32,000 and 64,000 simulations? And how much of the 16k gain is the budget alone (flat
16,000, no Gumbel root), which §770 did not measure? Separately: does max backup (decision nodes take their best
sufficiently visited child's value instead of the mean) help the Gumbel root at 16k? §762 found it NOT_SHOWN in whole
runs at about 1,000 simulations with the plain root; it was never tried under the Gumbel root or at a high budget.

## Design

- States and copy seeds: exactly §770's. The 1,878 act-1-3 elite and boss fights of §711's 329 Baalorlord runs, 4
  copies per fight (copy 0 = the game's battle seed, copies 1-3 seeded from (seed, floor, copy) as in
  `FightReplayer::playCopy`). No new seeds, no 111xxxxxx block.
- Binary 3e801097: code d430d406 = main 30b212ee plus one change, the expertfights arm token `mb<M>` (sets the existing
  thread-local `g_nativeSilverMaxBackupOverride` for that arm's searches only). The combat search code (src/,
  include/) equals §770's a51a2ed2; main's other changes since are in other one_combat modes. Same inputs
  (student_sel cf6bf7fb, expert_runs.tar 895eac8f), preset x86-64-v3 and environment; `run_unit.sh` is §770's except
  the unit split and the arms. Combat search is deterministic given state and seeds, so production reproduces §770
  exactly; this is checked, not assumed (see Reproduction).
- New arms (research overrides of `STS_EXPERT_FIGHTS_ARMS`):
  - `gsh16+flat32000`, `gsh16+flat64000`: §770's Gumbel root (k 16, c_visit 50, c_scale 1, min-max q) at 2× and 4×
    of 16k.
  - `flat16000`: flat 16,000 simulations at every root, no learned stop, plain root (the control for gsh16+flat16000
    at equal budget).
  - `gsh16+flat16000+mb4`: g16 with max backup, minimum 4 visits (as `STS_SILVER_MAX_BACKUP=4`, §759/§762). The
    process env var cannot be used: it would also switch production, the main line, and move later fights' states
    off §770's. Under the Gumbel root, sequential halving ranks root edges by `selectionValue`, which max backup
    changes, so it acts on the root choice as well as below it.
- Baseline arm `gsh16+flat16000` (`g16`) is not re-run: its per-copy results come from §770's units
  (`/mnt/project-files/combat-plan/teacher-check/units`, 329 tars). Production is re-run in every unit (it is the
  main line), which makes the reproduction check possible.
- Units: one per (run, act, arm set) for the 576 (run, act) pairs that have at least one elite or boss fight in §770's
  record, arm sets `g64` = {gsh16+flat64000}, `g32f16` = {flat16000, gsh16+flat32000} and `g16mb` =
  {gsh16+flat16000+mb4}: 1,728 units.
  `STS_EXPERT_FIGHTS_ARM_ROOMS=<act>E,<act>B`; everything else as §770 (4 arm copies, act cap 3, 12 h timeout).
  `units.txt` is ordered by the projected cost from §770's CPU (longest first), so the long units start first.
- Run: 40 cloud workers × 4 lanes, worker.sh queue, lease 45 min; share `/mnt/project-files/combat-plan/gumbel-budget`.
- Cost (projected from §770's per-copy CPU; 64k scaled by the first smoke's 15.5× instead of the linear 12.6×):
  about 450 lane-hours (gsh16+flat64000 ~220, gsh16+flat32000 plus flat16000 ~140, gsh16+flat16000+mb4 ~45,
  production three times ~43). flat16000 adds about 48 lane-hours, the max-backup set about 60. Simulated
  longest-first queue on 160 lanes: median lane 2.7 h, makespan 6.9 h because of three act-3 units with Awakened One
  / Time Eater fights.

## Endpoints and analysis (fixed; `analyze.py`)

Same definitions as §770: HP lost per copy = entry HP − exit HP (0 on a loss), floor-51 exits inverted for the Act-4
heal, side value = mean over the 4 copies; drops as §711 (invalid copy, no logged exit HP, two logged fights on the
floor) plus `missing_side` (a side's unit is missing or has rc != 0). Units whose `.done` line has rc != 0 are
excluded; the RESULT reports the tally by rc. CIs: run-clustered bootstrap, 10,000 resamples, seed 20261108.

- **Reproduction (gate for the pairing with g16):** a fight reproduces if each of production's 4 copies here equals
  §770's in won, exit HP, exit max HP, turns, decisions, simulations and potions used. If fewer than 99% of the
  compared fights reproduce, the g16 contrasts are not paired and the result is **NOT_PAIRED** (a g16 re-run would
  need its own go); the arm − production contrasts are still reported.
- **Primary, per arm a ∈ {gsh16+flat32000, gsh16+flat64000}:** mean over all fights of (a − g16) HP lost, 97.5% CI
  [lo, hi] (two arms, Bonferroni).
- **Decision rule (applied by `analyze.py`):**
  - any a with hi < 0 → **MORE_SIMS_HELP** (the arm with the lowest mean among them is the better teacher candidate;
    whether it is worth its CPU is Philipp's call).
  - otherwise, both with lo > −0.3 → **NO_GAIN_BEYOND_16K** (neither gains 0.3 HP per fight or more over 16k; 0.3 is
    about a third of 16k's gain over production).
  - otherwise → **INCONCLUSIVE**.
  No default change on this result.
- **Separate contrast, max backup:** mean of (gsh16+flat16000+mb4 − g16), 95% CI, under the same reproduction gate;
  not part of the budget decision. hi < 0 → **MAX_BACKUP_HELPS**; lo > −0.3 → **MAX_BACKUP_NO_GAIN**; otherwise
  **INCONCLUSIVE**.
- **Secondary (95% CIs, descriptive):** flat16000 − g16 (the Gumbel root at 16k budget), flat16000 − production
  (budget alone), gsh16+flat64000 − gsh16+flat32000, each new arm and g16 − production.
- **Co-reported:** deaths and potions per fight, CPU ratio (new arms against this run's production, g16 against §770's
  production) and simulations per decision, by act, room, act × room and encounter (n ≥ 20).

## Caveats fixed in advance

- Exploratory on states used before (§711/§716/§718/§770). These fights are the combat plan's stage-3 test set; no
  training data is recorded here.
- The main line is production's, so later fights follow production's earlier fights (as §770).
- One Gumbel setting (k 16, c_visit 50, c_scale 1) at every budget: at 64k each of the 16 candidates gets far more
  simulations per halving phase; k was not re-tuned for the larger budget.
- Long units can be killed by container resets (§770: one 4.9 h unit needed three attempts). A unit that fails 4
  times is reported and its fights drop as `missing_side`; the RESULT lists them, and since they are the longest boss
  fights, a drop is not ignorable for the boss cut.
- CPU is per-thread time on shared cloud machines; ratios across campaigns (g16 vs new arms) mix machines.

## Smoke 1 (2026-11-08, §770's binary 44d6d0c9, arm sets g64 and g32f16 only; not part of the analysis)

Units 1649793508 × acts 1-3 × both arm sets and 1651788114 act 2 g64: 7 of 7 rc 0, wall 98-651 s on 4 lanes.
`analyze.py` against §770's units: production reproduced in 13 of 13 compared fights (every copy identical), 0
conflicts between the two arm-set units, 9 fights with all sides (the rest of §770's fights `missing_side`, as
expected in a smoke). CPU ratio to production: flat16000 4.16, gsh16+flat32000 7.47, gsh16+flat64000 15.49 (g16 3.78
against §770's production on these fights); simulations per decision 16,000 / 27,943 / 56,072 (production 4,076). HP
numbers on 9 fights are noise and not reported. RSS per process about 0.9 GB.

## Smoke 2 (2026-11-08, binary 3e801097 as frozen; not part of the analysis)

Units 1649793508 × acts 1-3 g16mb, 1651788114 act 2 g16mb and 1649793508 act 1 g64: 5 of 5 rc 0, wall 45-338 s.
- The g64 unit's fights file equals smoke 1's (binary 44d6d0c9) in every field except CPU: production and the arm
  are unchanged by the new binary.
- `analyze.py` on smoke 1 + smoke 2 against §770's units: production reproduced in 13 of 13 fights, 0 conflicts
  between the three arm-set units, `decision` and `decision_max_backup` both INCONCLUSIVE (9 fights, no CIs).
- Max backup acts: 48 of 52 gsh16+flat16000+mb4 copies differ from §770's gsh16+flat16000 copies on the same seeds
  (exit HP, turns, decisions or simulations). CPU ratio to production 3.97 (g16 3.78); simulations per decision
  13,945 (g16 14,034).
