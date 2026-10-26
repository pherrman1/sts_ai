# Expert-run replay fidelity (2026-10-26)

Question: can logged expert runs (seed + out-of-combat decisions) be replayed in the
native engine, so that expert decisions can later be combined with Silver combat
and ablated by decision type? This note measures only fidelity: how often the
engine reproduces what the expert's log says the game offered. No gameplay batch
was run: battles are skipped, and no Silver search or policy is involved.

## Data

- Source: the public run archive of the streamer Baalorlord
  (`https://baalorlord.tv/profile/0/runs`, raw JSON per run at `/runs/<id>/raw`).
  All 676 Ironclad runs were downloaded on 2026-10-26 (all A20, 425 wins).
  The files are third-party data and are not committed. A copy lives in the
  project share at `expert-replay/baalorlord_ironclad_raw/` with the probe outputs.
- Fields used: `seed_played`, `path_taken`, `path_per_floor`, `damage_taken`,
  `card_choices`, `relics_obtained`, `boss_relics`, `event_choices`,
  `campfire_choices`, `items_purchased`/`item_purchase_floors`, `items_purged`,
  `potions_obtained`, `potions_floor_spawned`, `neow_bonus`/`neow_cost`, HP/gold
  per floor, and (newer runs, Run History Plus mod) `neow_bonus_log`,
  `neow_bonuses_skipped_log`, `shop_contents`, key logs.

## Tools

- `apps/expert_seed_probe.cpp` (`expert-seed-probe <seed>...`): prints the
  decision-independent skeleton of a seed (Neow options; per act 1-3 the map,
  normal and elite encounter lists and boss).
- `apps/expert_replay_probe.cpp` (`expert-replay-probe <run.json>...`): replays a
  run's logged out-of-combat decisions with `skipBattles`, syncing HP, max HP and
  gold to the log at every floor, and compares card reward offers (base card
  names; upgrade flags separately), `?` room outcomes, event names, reward and
  chest relics, boss relic offers, potion drop floors, and shop shelves (logged
  shelves must be a subset of the engine's shop) against the log.

## Stage 1: seed only (676 runs)

| runs | map path valid | normal encounters | elites | bosses |
|---|---|---|---|---|
| 348 vanilla-RNG runs (builds 2020-12-13 to 2022-12-18) | all except Winged Boots jumps | 100% | 100% | 100% |
| 327 runs with the RNG Fix mod (2022-12-18) | as above | 18-20% (chance level) | | |

The RNG Fix workshop mod (id 2181005326) re-derives each RNG category's seed
from the map seed; its derivation is not public. Its runs are unusable. The
ActiveMods list only exists in recent files, so 227 runs without a mod list are
also RNG Fix runs by this test; runs split cleanly (1.0 vs < 0.8 encounter
match), and one run had no fights to test.

## Stage 2: decision replay (348 vanilla runs)

Numbers below include a local, uncommitted engine patch (see Calling Bell
below): `createCardReward(Room::EVENT)` in the `CALLING_BELL` acquisition case.

| check | match |
|---|---|
| card reward offers (base names) | 7,132 / 7,643 (93.3%) |
| upgrade flags within matched offers | 7,065 / 7,132 (99.1%) |
| `?` room outcomes | 2,486 / 2,488 (99.9%) |
| event names | 1,717 / 1,783 (96.3%, includes spelling-only misses such as SensoryStone) |
| reward / chest relics (floors with a logged relic) | 3,004 / 3,249 (92.5%) |
| boss relic offers | 486 / 541 (89.8%) |
| potion drop floors | 3,413 / 3,607 (94.6%) |
| shop shelves (cards / relics / potions) | 94.4% / 93.3% / 94.0% |
| Neow pick available | 329 / 329 full blessings; 19 mini blessings |

Runs whose card offers stay exact through the end of an act, among runs that
reached it:

| act | runs | card offers exact | every checked category exact |
|---|---|---|---|
| 1 | 303 | 281 (93%) | 256 (84%) |
| 2 | 255 | 200 (78%) | 123 (48%) |
| 3 | 243 | 156 (64%) | 51 (21%) |

258 of 348 runs reproduce every logged card offer of acts 1-3.

### Known divergence sources

- **Calling Bell at Neow:** without the patch, 251 runs are exact and card offers
  diverge from floor 1 after a Neow Calling Bell. With an extra discarded
  card-reward roll at acquisition the first acts match (7 more runs exact). This
  is consistent with Java's `CombatRewardScreen.setupItemReward` creating a card
  `RewardItem` when the relic opens the reward screen, as the engine already
  models for Neow's potions. **Open question:** whether the boss-chest Calling
  Bell does the same; not verified against the game code.
- **Prismatic Shard:** the engine disables it (`disablePrismaticShard`); 21 runs
  diverge after buying it.
- **Mini Neow blessing:** 19 runs started after a short previous run and got
  the fixed two-option blessing; the probe applies it directly.
- **Egg relics:** offers in the log show eggs' preview upgrades; 1% of matched
  offers differ only in upgrade flags.
- **Old logs:** 47 runs (builds before Run History Plus) do not log Neow
  sub-choices (cards removed, transformed, upgraded); the probe guesses.
- **Unlogged decisions:** Bottled card choices, Astrolabe picks and Match and
  Keep positions are not logged; Winged Boots jumps are not reconstructed (18
  runs stop early).
- Boss relic, elite relic and shop mismatches after act 1 are not yet
  attributed; candidates are relic pool eligibility rules (for example Black
  Blood without Burning Blood) and earlier relic RNG consumers.

## Interpretation

Vanilla expert seeds replay well: the engine reproduces the offered choices
for most runs through act 1 and for most of act 2. A combined expert-decision
plus Silver-combat experiment is feasible on these 348 seeds with a fallback
to the bot policy at the first divergence, an illegal logged action, or the
expert's death floor.

Knowledge impact: this evidence note only; no default or engine change.
