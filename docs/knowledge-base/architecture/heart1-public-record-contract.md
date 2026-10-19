# heart1/student_sel public record: field inventory and training-to-live contract

Last verified: 2026-10-18 against main `b5dd5557` (issue #506 steps 1-2).

This page covers the one input that is both the A20 OOC prior in simulation and
live (student_sel, ADR-0042/ADR-0047) and the planned AZ-loop training record:
`heart1::Record` built by `heart1::buildChoice` and serialized by
`recordToJson` (schema `heart1-public-record-v2` in captures), plus the
battle-start and Match and Keep leaf extensions of `buildPublicLeafRecord`
(`apps/one_combat/heart1_policy.cpp`). Other models' inputs are out of scope.

Status: **not live-parity qualified.** Captures keep
`recordPublicParityQualified:false` (`heart_outcome_capture.cpp`). Simulator
private-state invariance is tested (below); live-vs-simulator record parity
(#506 step 3) is open, and one mismatch is already known.

## Information rule

A record field may come from the visible screen, the visible run state, or
history reconstructible from public observations. It must not come from the
seed, RNG streams, the realized encounter queue, the unrevealed second boss,
hidden reward/pity counters, event/relic/card pools, or hidden rolls stored on
a screen (chest contents, Dead Adventurer reward order). Both simulator and
live paths build the record with the same `buildChoice` on a `GameContext`;
live, that context is the projection from `live_ooc_state.cpp`, which imports
no seed, RNG or queue (`g.seed = 0`, constructor priors for hidden counters).
So parity reduces to: the live projection must give every field below the same
value the simulator would hold in the same public situation.

## Field inventory

Classes: **O** directly observed on screen or in the run HUD; **R**
reconstructible from public history; **P** private (must not appear).

| Record key | Simulator source | Class | Live source | Status |
|---|---|---|---|---|
| `obs.fixed_observation[0..1]` HP, max HP (cap 200) | `curHp`, `maxHp` | O | `publicState.hp/maxHp` | qualified by construction |
| `[2]` gold (cap 1800) | `gold` | O | `publicState.gold` | qualified by construction |
| `[3]` floor | `floorNum` | O | `publicState.floor` | qualified by construction |
| `[4]` act boss | `boss` (first boss only) | O | `publicState.boss` | qualified; `secondBoss` is excluded (tested) |
| `[5]` cards to select | `info.toSelectCount` | O | screen capture | open (step 3) |
| `[6]` ascension, `[7..9]` keys | `ascension`, `redKey/greenKey/blueKey` | O | `publicState` | qualified by construction |
| `obs.deck.cards/upgrades` | `deck.cards[].id`, `getUpgraded()` | O | `publicState.deck` | qualified by construction; Searing Blow's upgrade count is `misc` on both sides (`Card::getUpgraded`, Java `timesUpgraded`) |
| `obs.deck.misc` (student extension) | `card.misc` (Ritual Dagger, Genetic Algorithm, Searing Blow) | O | `deck[].misc` | open (step 3) |
| `obs.act` (student extension) | `act` | O | `publicState.act` | qualified by construction |
| `obs.relics.relics` | relic ids in acquisition order | O | `publicState.relics[].id` | open: order must match acquisition order |
| `obs.relics.relic_counters` | `RelicInstance::data` | O / R | `LiveOocCapture.nativeRelicData` | **known mismatch**, see below |
| `obs.potions` | `potions[0..capacity)` | O | `publicState.potions` | qualified by construction |
| `obs.map.xs/ys/roomTypes/pathXs` | `map` nodes generated at act start | O | `publicState.map.nodes` (105 nodes) | qualified: `?` nodes stay `EVENT`, rooms are never rewritten after generation (`Map.cpp`) |
| `obs.map.burningEliteX/Y` | `map->burningElite*` | O | `map.burningEliteX/Y` | open: check when Java exposes it |
| `obs.mapX/mapY` | `curMapNodeX/Y` | O | `map.x/y` (boss sentinel `-1,15`) | qualified by construction |
| `cards_offered.*` | reward card groups, shop cards, `toSelectCards` | O | screen capture | open (step 3) |
| `relics_offered` | reward relics, shop relics, `info.bossRelics` | O | screen capture | open (step 3) |
| `potions_offered` | reward potions, shop potions | O | screen capture | open (step 3) |
| `fixed_actions` (+`gold/card/relic/info`) | event option mapping, Neow bonus/drawback, rest options, skip/remove/key/chest | O | event/screen capture | open (step 3); event payloads are option-text values (Face Trader HP, We Meet Again gold/card, N'loth relics, Golden Idol/Winding Halls HP, Falling card, World of Goop gold loss, Neow drawback) |
| `paths_offered` | legal map moves (`mapMoveCost`, includes Wing Boots jumps) | O | map + Wing Boots `liveCounter` | open: depends on Wing Boots charges, which the record itself does not encode (#638) |
| `screen_state`, `select_screen_type` | `screenState`, `info.selectScreenType` | O | screen capture | open (step 3) |
| `leaf.publicBattleEncounter` | `info.encounter` at the battle-start boundary | O | `publicEnemy` / room | qualified for the encounter just entered; never a queue entry |
| `leaf.matchAttempts`, `leaf.matchSlots` | Match and Keep board, unseen cards masked | O | event capture | qualified in simulator (masking tested); live open |

Fields deliberately absent (private or omitted): seed, all 14 RNG streams,
`monsterList`/`eliteMonsterList`, `secondBoss`, `potionChance`,
`cardRarityFactor`, room chances, event/shrine/relic/colorless pools, chest
`tier`/`haveGold` before opening, Dead Adventurer `info.rewards`, shop prices,
remove cost, Wing Boots charges, card/potion pity history. Shop prices, remove
cost and Wing Boots charges are public but omitted; omission is the same in
training and live. Neither path invents a value for them.

## Known live/simulator mismatch: relic counters of counterless relics

student_sel (`student_sel.bin` sha256 `cf6bf7fb…`) has the student extension
inputs (`x_act`, `x_deck_misc`, `x_relic_counter`), so each relic's counter
enters the network as a number clamped to [-1, 999]
(`heart1_policy.cpp`, `relicCounter_`). In the simulator a relic without a
counter (Burning Blood, Bag of Marbles, …) holds `data = 0`
(`GameContext::obtainRelic`). Live, `nativeRelicData` copies Java's counter for
nonpositive values, and Java's default counter is -1: the real captures
`tests/fixtures/live_act1_boss_card_reward.json` and
`tests/fixtures/live_act3_entry.json` carry `"data": -1` for Burning Blood,
Meat on the Bone, Singing Bowl and others, and `live_ooc_state.cpp` imports it
unchanged. So live student_sel sees -1 where every training record saw 0.
The comment "nonpositive counters have the same V4 token encoding as native
zero" holds for V4, not for this numeric input. Measured in the #685 review
on 4,782 simulator records with at least two choices (counterless relics set
to -1, scored with `heart1score` and student_sel): the prior argmax changes in
26 records (0.54%), mean total variation 0.0045, p99 0.056, max 0.157; value
head mean |Δ| 0.0004. Real live states were not measured. The fix (map nonpositive non-persistent counters to
0 at import, matching the simulator) changes live play and belongs to step 3
with a flag.

## Simulator invariance test

`one_combat heart1recordselftest` (CTest `heart1_public_record_invariance`,
labels `core;smoke`, `apps/one_combat/heart1_record_invariance.cpp`) builds
hand-made states, drives no game seed, and checks for map, combat reward,
shop, boss relic, rest, card select, treasure, events (Face Trader, Dead
Adventurer, We Meet Again, Neow) and battle start:

- three private realizations (seed, every RNG stream, both encounter queues,
  second boss, `potionChance`, `cardRarityFactor`, room chances, event and
  relic pools, colorless pool order, chest tier/gold roll, Dead Adventurer
  reward order) give byte-identical choice and leaf records and identical
  legal choice tokens;
- each listed public change (HP, gold, a relic counter, a deck upgrade, an
  offered card/relic/potion, a map room, the burning elite, the act boss, an
  event payload, the encounter just entered, the select type) changes the
  record.

The older fixture in `priorMappingSelfTest` (rest room, battle start, Match and
Keep masking) remains. Passing these tests shows the encoder ignores private
simulator state; it does not show that live capture fills the public fields
with simulator semantics.

## Remaining evidence (step 3)

Diff `recordToJson` field by field between the live projection and the
simulator on the same real game states (coordinated with the combat parity
canary on Philipp's PC), covering every screen above, the relic-counter
mapping (all `PERSISTENT_RELIC_COUNTERS`, Lizard Tail, Maw Bank, Matryoshka,
N'loth's mask, the counterless default), relic order and the burning elite. Live history gaps (pity counters, #636; Centennial Puzzle
and Necronomicon state) are not record inputs and need no handling here unless
a later record version adds them.
