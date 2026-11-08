# Teacher check on Baalorlord's elite and boss states (pre-registration)

Status: frozen with the run commit (see `campaign.manifest`). Combat plan stage 1
([plan](https://claude.ai/artifact/HvTqKL592wjb21Zgb3Sho4)). Philipp asked for stages 0 and 1 in parallel on
2026-11-08 00:49 CET ("Mach Stufe 0 und 1 in parallel") and gave the go for up to 18 workers per stage at 00:57 CET
("du hast für beide phasen je 18 worker zur Verfügung, starte die wenn nötig ... Frag nicht nach Erlaubnis").

## Question

Is there a combat teacher that plays Baalorlord's A20 elite and boss states better than today's production Silver?
If yes, stage 2 trains the combat net on that teacher's targets; if no, a net can only copy Silver (speed, not
strength). Teachers already measured and not repeated: more flat budget (§716, §718), several playouts per leaf at
equal CPU (§479), exact solves at the end of fights (§623, §654). Human moves are not in Baalorlord's `.run` files.

## Design

- States: §711's 329 vanilla-RNG Baalorlord runs (`units.txt` = §711's), every act-1-3 elite and boss fight inside
  the exact-replay prefix. External run seeds of §694, no 111xxxxxx block. Exploratory like §716/§718/§765: these
  states were used before.
- Mode: `one_combat expertfights`, `run_unit.sh` = §718's except the `E=` line: arms below,
  `STS_EXPERT_FIGHTS_ARM_ROOMS=1E,1B,2E,2B,3E,3B`, `STS_EXPERT_FIGHTS_ARM_REPLICATES=4`, 12 h timeout. In every elite and
  boss fight, copies 0-3 are played by production and by each arm on the same copy seeds (copy 0 = the game's battle
  seed). Other fights and copies play only until the first win, so the main line is production's.
- Production: today's A20 combat (learned stop, exact root budgets, g7f_E root table and prior, tree prior K = 8,
  boss-only prior playouts). In the smoke it averaged 4,128 simulations per decision.
- Arms (code 1a37c74a, all research-only thread overrides, default off):
  - `rpl4`: production with 4 greedy playouts per leaf (everything else, prior playouts included, unchanged); about
    3x CPU in the smoke.
  - `flat4000`: flat 4,000 simulations per root, no learned stop: the control for the Gumbel arms.
  - `gsh16+flat4000`: Gumbel root (`SilverSearcher::searchGumbelRoot`, Danihelka et al. 2022): Gumbel-top-16 over the
    g7f_E root prior, sequential halving over the 4,000 simulations, pick by g + logit + sigma(q) with c_visit 50,
    c_scale 1 and q min-max normalized over the visited root edges. Below the root the search is production's.
  - `gsh16+flat16000`: the same at 16,000 simulations (4x).

## Endpoints and analysis (fixed; `analyze.py`)

HP lost per copy = entry HP − exit HP, exit 0 on a loss. Floor-51 exits inverted for the Act-4 heal as in §711/§718.
Side value = mean over its 4 copies. Drops as in §711 (invalid copy, no logged exit HP, two logged fights on the
floor). CIs: run-clustered bootstrap, 10,000 resamples, seed 20261108; each arm is judged on its 98.75% CI (four arms,
Bonferroni).

- **Primary, per arm:** mean over all act-1-3 elite and boss fights of (arm − production) HP lost, CI [lo, hi].
- **Decision rule (applied by hand):**
  - any arm with hi < 0 → **TEACHER_FOUND** (the arm with the lowest mean is the stage-2 teacher candidate).
  - otherwise, every arm with lo > −0.5 → **NO_BETTER_TEACHER** (no teacher gains 0.5 HP per fight or more).
  - otherwise → **INCONCLUSIVE**.
  No default change on this result. A whole-run A/B of a found teacher needs its own pre-registration.
- **Secondary (descriptive, 95% CIs):** gsh16+flat4000 − flat4000 (Gumbel root at equal budget), gsh16+flat16000 −
  gsh16+flat4000 (4x budget under the Gumbel root).
- **Co-reported:** deaths and potions per fight, CPU ratio and simulations per decision for each side, by act, by room,
  by act × room, by encounter (n ≥ 20), production − expert.

## Caveats fixed in advance

- §711's main line is production's, so later fights follow production's earlier fights (HP is set to the expert's at
  every fight, potions are the bot's own).
- Four arms on the same copy seeds are strongly correlated with production; most fights end the same way on every
  side, so the CIs are narrow but the effect may be small.
- Gumbel's sigma(q) needs bounded values; Silver's scores are not, hence the min-max normalization. This is one
  reasonable choice, not a tuned one.
- The CPU of one unit is about 10x a production-only unit.

## Smoke (2026-11-08, binary 44d6d0c9, `run_unit.sh` as frozen; not part of the analysis)

Units 1675881103 and 1648247344, both rc 0, 147 s and 1,112 s wall. `analyze.py` on them: 18 elite/boss fights, 0
dropped. HP lost per fight: production 4.89, rpl4 4.17, flat4000 6.69, gsh16+flat4000 4.85, gsh16+flat16000 4.90 (2 runs,
no CIs). CPU ratio to production 3.09 / 1.03 / 0.95 / 3.85; simulations per decision 3,954 (production), 3,986,
4,000, 3,808, 15,404. Expected campaign cost: about 329 units × 10-20 min ≈ 55-110 lane-hours.
