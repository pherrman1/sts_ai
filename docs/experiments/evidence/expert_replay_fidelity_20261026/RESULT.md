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

Numbers below are with `STS_CALLING_BELL_CARD_RNG_FIX` on (the default since
this change; see Calling Bell below) and with the log's `SensoryStone` spelling mapped (first version of
this note: event names 96.3%, card offers 7,132 / 7,643). With the fix at `0`, card offers matched
7,098 / 7,643 (92.9%) and 251 runs were fully exact.

| check | match |
|---|---|
| card reward offers (base names) | 7,138 / 7,645 (93.4%) |
| upgrade flags within matched offers | 7,071 / 7,138 (99.1%) |
| `?` room outcomes | 2,487 / 2,489 (99.9%) |
| event names | 1,772 / 1,784 (99.3%) |
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

- **Calling Bell (fixed, `STS_CALLING_BELL_CARD_RNG_FIX`):** without the fix,
  card offers diverge from floor 1 after a Neow Calling Bell (3 runs: 7 of 26
  offers match; with it 20 of 26, two runs fully exact) and after an act-2
  boss-chest Calling Bell (5 runs become fully exact). No run gets worse. An
  act-1 boss-chest Bell is masked by the act-start `cardRng` counter reset.
  This is consistent with the game opening the combat reward screen (which
  rolls a card `RewardItem`) before clearing it for the relics, as the engine
  already models for Neow's potions. **Open question:** not verified against
  the game's bytecode.
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

## Replay mode (Silver combat)

`one_combat expertreplay 1 RUN.json OUT.json` (`apps/one_combat/expert_replay.cpp`) plays one A20 full run on the
expert's seed through the production driver `runFullRunOOC` and first offers each real out-of-combat step to a
replayer of the log. The replayer plays the logged path, card/potion/relic/key rewards and chests, campfires, shop
purchases and removals, boss relics, events and Neow while the engine's offer equals the log and the logged action
is legal, with no HP or gold syncing. At the first decision that is not (offer differs, room or event differs,
illegal or unaffordable action, log ends, Winged Boots path, Neow mini blessing, Act 4) it stops for the rest of the
run and the production chain plays on. Unlogged picks (Bottled cards, Astrolabe, Match and Keep, old Neow
sub-choices) go to the production chain without stopping. `STS_EXPERT_REPLAY_TYPES` selects the decision types
(`all`, `none`, or a list of `path,reward,campfire,shop,bossrelic,event`); `none` is the bot alone on the same seed.
[`run_unit.sh`](../expert_replay_ab_20261027/run_unit.sh) runs both arms per seed with today's A20 default stack. Smoke: [SMOKE.md](SMOKE.md).

## Interpretation

Vanilla expert seeds replay well: the engine reproduces the offered choices
for most runs through act 1 and for most of act 2. A combined expert-decision
plus Silver-combat experiment is feasible on these 348 seeds with a fallback
to the bot policy at the first divergence, an illegal logged action, or the
expert's death floor.

Knowledge impact: this evidence note and its smoke; `STS_EXPERT_REPLAY_TYPES` and `STS_CALLING_BELL_CARD_RNG_FIX` (default on) documented in `docs/knowledge-base/operations/environment-variables.md`.
