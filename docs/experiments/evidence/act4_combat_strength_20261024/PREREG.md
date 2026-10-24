# Act-4 combat strength: is Silver weak in Shield and Spear and the Heart, or are the decks? (PREREG, 2026-10-24)

**Question (Philipp, 2026-10-24 09:00Z):** "bei beiden act4 fights gilt: wir müssen erst testen ob wir überhaupt bessere
combats machen könnten, oder ob wir einfach ein schlechtes deck gebaut haben. Maybe mal 128 s&s und Heart kämpfe nehmen
und mit je 10k und 40k sims spielen, mit Prior. Und mit dem teuren prior rollout. Maybe auch einmal ohne Prior [...]
Du kannst bis zu 32 Workern nutzen."

**Why now.** Under today's default (CTM guard arm C, §676) 38% of Heart fights are lost, and Heart death rises steeply
with entry HP (26% at >= 70 HP, 62% at 40-59, 71% below 40; entry HP is confounded with deck quality). Shield and
Spear costs 20.8 HP on average right before the Heart, with no heal between. Exact solves (§623, §654) found Silver
near-optimal on first fights and last turns, but no study has asked whether *more Silver search* wins more Act-4
fights from the decks we actually reach.

## Design

- **States.** 128 Shield and Spear and 128 Heart entry states, drawn at random (Python `random.Random(20261024)`,
  without replacement) from the 227 / 217 valid Act-4 fights of the guard's arm C (§676, run `4056cef9`; units
  `/mnt/project-files/ctm-calibration-ab/units`, rows `*.ctm.jsonl.gz`, `transition.pre`). `make_states.py` builds
  them; `states/shield_and_spear_128.jsonl` sha256 `ddeba306...`, `states/the_heart_128.jsonl` sha256 `5f4f856d...`.
  The lines carry the recorded deck, relics with their counters (`relicData`, e.g. an unused Lizard Tail, Pen Nib),
  bottled cards (`bottleIdxs`), potions, HP and max HP, and the real outcome (`observedWon`, `observedPostHp`).
  Recorded: Shield and Spear 123/128 won, Heart 75/128 won (58.6%).
- **Tool.** `one_combat act4replay` (flat exact-budget native Silver). This PR fixes three reconstruction errors that
  every earlier act4replay study shared (§528-§530, §642): "Strike"/"Defend" became the Defect variants
  (STRIKE_BLUE/DEFEND_BLUE; Silver's rollout tables and expert rules key on the *_RED ids); every relic counter was
  reset to 0, so an unused Lizard Tail counted as spent; bottled cards were not bottled. Card misc stays 0 (all 0 in
  these states). The fight's own RNG streams are not the recorded ones (fresh battle seeds below).
- **Arms** (all: `STS_SILVER_LEARNED_STOP=0`, exact root budgets, reuse cap allocated, g7f_E rollout root table,
  `STS_ACTIVE_POWER_FEATURES=1`, engine fixes on; `run_unit.sh` has the full environment):
  - `P`: g7f_E root prior weight 400 + tree prior K 8, greedy root-table playouts (production in elite rooms).
  - `PP`: `P` + prior playouts (`STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=1`, `STS_SILVER_PRIOR_PLAYOUT_ELITE=1`): the
    "expensive prior rollout"; production in boss rooms (ADR-0050, ADR-0056).
  - `N`: no root/tree prior; greedy root-table playouts (the rollout card table stays g7f_E).
  - Each arm at flat **10,000 and 40,000** simulations. Production plays the learned Silver stop, which averages
    below 10,000 (§516), so 10k is at least production strength.
- **Copies and seeds.** 8 copies per state; copy r of state k uses battle seed 111395000 + 8k + r (Shield and Spear,
  111395000-111396023) or 111397000 + 8k + r (Heart, 111397000-111398023), and the same planner seed, in every arm
  and budget: all six cells are paired per (state, copy). Smokes used 111396990-111396995. 128 x 8 x 6 = 6,144
  fights per encounter.
- **Campaign.** 768 units (encounter x state x arm), each runs both budgets x 8 copies single-threaded. 32 cloud
  workers x 4 lanes, queue schedule (Philipp: up to 32 workers). Estimated ~140 CPU-hours (smoke: Heart PP 40k
  2.5-5 min per fight, everything else seconds to a minute), about 1.5-2 h wall.

## Analysis (`analyze.py`)

Per state, the mean over its 8 copies; 95% bootstrap over the 128 states (10,000 resamples, seed 20261024).
Shield and Spear HP lost = entry HP - HP after the fight (a death loses all entry HP).

- **Primary, Heart:** win rate `PP@40k - PP@10k` (strongest configuration vs the production-like one).
- **Primary, Shield and Spear:** HP lost `P@10k - PP@40k` (HP saved by the strongest configuration vs production).
- **Decision rule:**
  - `COMBAT_HEADROOM` if the Heart contrast has CI lower bound > 0 and mean >= +3 pp, **or** the Shield and Spear
    contrast has CI lower bound > 0 and mean >= 3 HP. Next step: whether production can afford that strength (CPU-
    matched budget reallocation to Act 4, a stronger playout or prior), proposed separately.
  - `SATURATED` if the Heart CI upper bound < +3 pp **and** the Shield and Spear CI upper bound < 3 HP: more Silver
    search does not win these fights; the losses sit in the decks (drafting, pathing, upgrades) or beyond Silver's
    search family. Act-4 combat search work pauses.
  - Otherwise `INCONCLUSIVE`.
- **Secondary (descriptive, no decision):** every other cell against the reference (Heart `PP@10k`, Shield and Spear
  `P@10k`); 40k - 10k within each arm; prior vs no prior (`P - N`) at each budget; prior playouts vs greedy
  (`PP - P`); CPU per fight per cell; the Heart win rate by entry HP band per cell; the distribution of each Heart
  state's win fraction over all 48 fights (0 = a lost deck under every Silver tried, 1 = always won); fidelity of the
  replay (reference cell vs the recorded real fight on the same states).
- **Caveat.** A `SATURATED` result says that more or different *Silver* search does not help, not that the play is
  optimal. Heart states are conditional on having won Shield and Spear in real play.

## Not changed

No default, model or live behaviour. The act4replay fix changes only this research mode.
