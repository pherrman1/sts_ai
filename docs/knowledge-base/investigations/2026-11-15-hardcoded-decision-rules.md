# Hardcoded decision rules: inventory and firing rates (#1055)

Status: **open**. [#1055](https://github.com/pherrman1/sts_ai/issues/1055) steps 1 (inventory) and 2 (Java check of
the choice sets, section D) done; step 3 (shadow) and step 5 (paired gates) open.

Last verified: 2026-11-15 against main `6126315`. The games counted were played by the PG16H24 actor binary
`dae7894a` (code `950b53fc`) and the §799 gate binary (`495d4d66`); both have the same OOC rule sites as `6126315`
(`run_driver.cpp`, `heart1_policy.cpp`, `ooc_tree_rules.cpp`, `GameAction.cpp`, `RunGoal.cpp` unchanged); since
`950b53fc` the Silver files changed only in the playout-prior speed path (#1046/#1047).

## Question

Where does a rule, a chain or an automatic step decide instead of a net or a search, how often does it fire per
run, and which of those places hide a real choice? Philipp's working view (#1055): a rule has to earn its place;
the default is that the net decides.

## Scope

Three decision stacks exist on main:

| stack | switch | who uses it today |
|---|---|---|
| **PPO** (OOC) | `STS_OOC_HEART1_PPO=1`, `STS_OOC_MCTS=0` | PPO training (PG16H24) and every recent whole-run gate (G12H24/G16 units carry `STS_OOC_HEART1_PPO=1`, `STS_OOC_HEART1=net-0420.bin`, temperature 0) |
| **old default chain** (OOC) | `STS_OOC_HEART1_PPO` unset | binary default: rule chain, student_sel (`heart1::policyStep`) and map-only OOC MCTS (ADR-0061); research arms before PPO |
| **combat** | Silver/Gumbel (`NativeSilverBackend`, `SilverSearcher`) | every stack |

Engine legality (`GameAction::getAllActionsInState`, `GameContext`) is in scope only where it removes a choice the
real game offers; whether each game rule matches Java is step 2.

## Reproduction

All counts are offline and read recorded games only; nothing is played.

- PPO actor trajectories: PG16H24 iterations 43 and 44 (store `ppo-xfer/pg16h24`, refs `PG16H24/traj-0043-p*`
  (39 parts, net-0042) and `traj-0044-p*` (28 parts, net-0043), temperature 1, 16k Gumbel combat, Heart 24k),
  871 games. The store keeps only recent iterations, so the 67 parts, their ref SHAs (`REFS.txt`) and
  `SHA256SUMS` are archived in `/mnt/project-files/hardcoded-rules-1055/pg16h24-traj-0043-0044.tar`.
  `python3 tools/heart1/ppo_decision_sources.py traj/ --out report.json` gives
  `/mnt/project-files/hardcoded-rules-1055/report-pg16h24-0043-0044.json`.
- Gate games at temperature 0: the 1,056 G12H24/G16 units of §799
  (`/mnt/project-files/gumbel-g12-heart24/units/*.tar`); each unit's `.err` carries the `[heart1_ppo]` summary line
  (decisions, single, fallbacks, auto_gold) and every Silver loop-guard firing.

## Results

**Headline.** In the PPO stack the net makes every real OOC choice: **0 chain fallbacks in 1,927 games** (871 PPO
games, 1,056 gate games). Per game: 90.1 net decisions with more than one choice, 34.3 single-choice decisions and
22.9 automatic gold pickups (gate games: 91.9 / 35.0 / 23.5). What remains are restrictions of the choice set, not
deciding rules, plus the combat pruning in section C. The old default chain is not used by any current run.

### A. PPO stack (`realOocChainStepBody` → `heart1::ppoStep`)

| id | where | what it does | fires (871 PPO games) | real choice hidden? | proposal |
|---|---|---|---|---|---|
| A1 | `ppoStep` → `takeFreeRewards(gc, false)` | takes every gold reward before the net sees the screen | 22.9 / game | **No**: Java `RewardItem.claimReward` GOLD / STOLEN_GOLD only calls `gainGold` (Ectoplasm voids the gain, D2) | keep (no choice) |
| A2 | `buildChoice` `discardTokens` | a potion discard token exists only when an offered potion is blocked by full slots, without Sozu (rewards; shop when affordable) | offered in 5,539 decisions, chosen 2,108 (2.4 / game) | Little: discarding elsewhere gains nothing out of combat | keep |
| A3 | `getAllActionsInState` (no potion actions) | the three potions the engine lets you drink out of combat (`isValidPotionAction`: Blood Potion, Fruit Juice, Entropic Brew) have **no drink token**; the net can only carry them into combat or discard them | 51 of the 2,108 discards threw one away (Blood Potion 41, Entropic Brew 8, Fruit Juice 2) | **Yes**: Java lets all three be drunk on the map, in shops, rest sites, events and reward screens (D1); drinking dominates discarding (heal / +5 max HP / refill) | **fixed**: drink token `kFaDrinkPotion` (178), default on (Philipp 2026-11-15, no gate), `STS_OOC_HEART1_PPO_DRINK=0` restores |
| A4 | `buildChoice` REWARDS | Singing Bowl token added (our engine executes it but does not enumerate it) | per Singing Bowl card reward | no (adds a choice) | keep |
| A5 | `realOocChainStepBody` | `heartKeyAction` runs only with `STS_OOC_HEART1_PPO_KEY_RULE=1` (comparison arm) | 0 (off) | – | keep off |
| A6 | `buildChoice` EVENT | Match and Keep as tokens (unseen / seen / pair) | 790 decisions | – | – |
| A7 | `eventFixedAction` | event options without a silverbot mapping get a generic token (`kFaEventOption0+i`) | **0** in 871 games | – | keep the fallback token |
| A8 | `ppoFallback` → old chain | reasons `match_and_keep`, `unmapped_event`, `unsupported_screen`, `no_choice`, `not_a_decision` | **0** in 1,927 games | – | `STS_OOC_HEART1_PPO_STRICT=1` would turn a fallback into an error |
| A9 | `ppoStep` | one-choice decisions are executed (still logged with a forward for the value) | 34.3 / game (map 23.2, rewards 8.8) | no | keep |

Net behaviour where the old rules would have decided (offline shadow of section B on the same 871 games, decision
counts; a reward screen is often several decisions):

| old rule | net in the PPO games |
|---|---|
| `treasureChestRuleAction` (open without Cursed Key) | opened 2,157 of 2,157 chests without Cursed Key and **91 of 91 with Cursed Key** (no skip ever) |
| `rewardRelicRuleAction` (take every reward relic except Philipp's reviewed list) | left 235 relics the rule would have taken (0.27 / game; act 1: 17, act 2: 43, act 3: 111, act 4: 64), led by Darkstone Periapt 36, Tiny Chest 27, The Boot 19, Omamori 16, Turnip 10; also no-downside relics such as Strawberry 5, Old Coin 3, Potion Belt 8. Left 107 relics of the reviewed list (the rule also leaves those) |
| boss relic | skipped 3 of 1,234 |
| ADR-0041 Sapphire "first chest" | decisions offering the key next to a relic: taken 137 / 1,445 (act 1), 201 / 908 (act 2), 403 / 412 (act 3): the net defers Sapphire to Act 3, as ADR-0063's policy default allows |
| ADR-0041 Ruby "first Act-3 campfire" | recalled at the first Act-3 campfire offering Recall in 200 of 470 games |

**Inference.** The relic rows are candidates for #1056 (obvious mistakes): a no-downside relic left in Acts 1-2 is
likely a net error, an Act-4 relic is worth little either way. The games where the net left such a relic have a
higher Heart rate (68% vs 25%), which only says these games are longer (more reward screens), not that leaving helps.

### B. Old default chain (`STS_OOC_HEART1_PPO` unset)

Order in `realOocChainStepBody`: `forced_boss_relic` (research) → `heart_key` → `heart1` (student_sel, without OOC
MCTS) → `chest_rule` → `relic_rule` → `tree_rule` (with OOC MCTS) → `match_and_keep` → `card_rule` (research) →
`value_chooser` (research) → `heart1_screen` (A20 map-only default: non-map screens) → `mcts` → `heart1_fallback` →
`runFullRunOocPolicyStep` (`heart_key`, `heart_key_mask`, `match_and_keep`, `chest_rule`, `relic_rule`,
`gbm_ranker`, `action_nn`, `map_route_search`, `v4_*`, `map_path_v`/`map_heuristic`, `event_v`, `free_reward`,
`card_reward_heuristic`, `shop_beam`, `shop_v_planner`, `shop_remove_v`, `rest_win`, `upgrade_select_*`, `rest_v`,
`boss_relic_v`, `neow_v`, `agent_default`).

| id | rule | decides | firing (one full A20 smoke game, seed 111375990, `ooc_map_only_search_20261024/SMOKE.md`) |
|---|---|---|---|
| B1 | `heartKeyAction` (ADR-0063: Sapphire backstop at the Act-3 treasure row, Ruby at the last campfire, Emerald mask) | keys | 4 |
| B2 | `treasureChestRuleAction` | open every chest without Cursed Key | 3 |
| B3 | `rewardRelicRuleAction` | take every reward relic outside the reviewed list (Bottled ×3, Dead Branch, Tungsten Rod, Unceasing Top, Juzu Bracelet) | 7 |
| B4 | `oocTreeRuleAction` | gold, potion pickup/swap by `potionKeepRank` (ADR-0039), leave an empty reward screen | 48 |
| B5 | `matchAndKeepPolicyStep` | Match and Keep slot by a hypothetical policy step | per Match and Keep event |

None of B runs in the PPO stack. If the old stack is kept as a comparison arm, its rules stay as they are.

### C. Combat (Silver / Gumbel; all stacks)

| id | where | what it does | firing | real choice hidden? | proposal |
|---|---|---|---|---|---|
| C1 | `SilverSearcher::enumeratePotionActions` | discarding a potion is an edge only when it frees a slot for a held Entropic Brew (no Sozu) | not counted | Inference: little for Ironclad (no other in-combat potion source without Prismatic Shard / Alchemize) | count |
| C2 | same | Fairy in a Bottle is never an edge | – | no: Java `FairyPotion.canUse` returns false (D1) | keep |
| C3 | same, `escapeForfeitsRun` (`NativeSilverBackend`) | Smoke Bomb is no edge when escape is blocked, or at the Act-3 burning elite without the Emerald Key under `STS_COLLECT_KEYS` | not counted | no under the Heart objective (escape ends any Heart attempt); a rule of the objective. The blocked case matches Java (D1) | keep; count |
| C4 | same | Gambler's Brew with an empty hand is no edge | not counted | no: Java allows it but `use` then does nothing and the potion is spent (D1), a dominated edge | keep |
| C5 | `cardsEquivalentForSearch`, duplicate potions | equal cards / potions share one edge | – | no when the equivalence is exact (id, upgrade, cost, cost for turn, free-once, retain, special data) | keep |
| C6 | `runNativeSilverCombat` loop guard | forced End Turn after 50 consecutive no-progress decisions (`STS_SILVER_LOOP_GUARD`) | **0** in 1,056 gate games | no (a stall guard) | keep |
| C7 | same; `BattleContext` | abort after 1,000 decisions; `STS_COMBAT_TURN_CAP=100` | not counted here | no (stall guards) | keep |
| C8 | `searchGumbelRoot`, `skipSingletons` | a root with one legal action is not searched | – | no | keep |
| C9 | `Expert::getPlayOrdering`, `bestAction` | enumeration order; ties of root visits go to the first edge | – | only in exact ties | keep |

Hand-made parts of the combat search that are not decision rules but shape every combat decision (out of scope
here, owned by the combat value-net and Gumbel threads): the leaf score (HP, potions, max HP, gold, escape penalty,
win bonus), the playout policy (greedy with the block rule, the learned g7f_E card table), the prior-share stop
(H = 0.9, ADR-0066) and the hand-set Act-4 budgets.

### D. Step 2: Java check of the choice sets (javap, 2026-11-15)

Pinned JAR `desktop-1.0.jar` sha256 `cfad868a…081673`, `javap -c -p -constants` (JDK 1.8.0_504) on the PC; raw
dumps (16 classes plus `AbstractPlayer`, `Shovel`, `PeacePipe`, `GridCardSelectScreen`, `AbstractChest`, `BossChest`)
and quoted bytecode in `~/Documents/sts/javap-1055/` on the PC.

| # | Java | engine / agent | verdict |
|---|---|---|---|
| D1 | `AbstractPotion.canUse`: false in We Meet Again, else only in combat on the player's turn. `FairyPotion.canUse` = false. `SmokeBomb`: default, then false if any monster has `BackAttack` or is `EnemyType.BOSS`. `GamblersBrew`: default `canUse`; with an empty hand `use` skips `GamblingChipAction` but the potion is spent. `BloodPotion`, `FruitJuice`, `EntropicBrew` override `canUse`: false only at turn end in combat or in We Meet Again, so **usable out of combat** (Blood heals, Fruit +max HP, Entropic Brew fills every slot; with Sozu nothing) | `isValidPotionAction` allows exactly these three out of combat (not in We Meet Again), but `getAllActionsInState` never offers them (A3). `smokeBombEscapeBlocked` = boss encounter or player `Surrounded` (the Spire pair's `BackAttack` counterpart, removed together on a death) | A3 is a real missing choice; C2, C4 match or prune a dominated edge; C3 matches Java, including Mind Bloom's fight (it uses the Act-1 boss encounter ids, which `isBossEncounter` lists) |
| D2 | `claimReward` GOLD / STOLEN_GOLD: `gainGold` only; Ectoplasm (in `AbstractPlayer.gainGold`) voids the gain, the reward is used up. POTION with Sozu: used up, no potion. POTION with full slots: `obtainPotion` fails, the reward stays | gold auto-taken (A1); full slots: no potion action until a discard (A2) | A1 has no hidden choice; A2 matches. Taking a potion reward with Sozu wastes nothing (Inference: same as leaving it) |
| D3 | Shovel always adds a usable Dig. Peace Pipe always adds Toke, `usable` only if a non-bottled purgeable card exists (else `useOption` does nothing). Recall only if the final act is available and no Ruby Key. Relic `canUseCampfireOption` can disable options | `getAllRestActions`: Dig always, Toke always ("assume we have card to remove"), Recall with keys enabled and no Ruby, no Rest with Coffee Dripper, no Smith with Fusion Hammer or nothing upgradeable | matches except Toke with no removable card: Java offers an unusable button, ours opens an empty REMOVE screen (edge case, practically unreachable) |
| D4 | Shop purge opens a cancellable grid; gold is taken only after a card is chosen; purge stays available after a cancel | `FA_REMOVE` commits: the next screen is the REMOVE select without cancel | a restriction, but no information is revealed between the two steps (the deck is known), so Inference: no loss |
| D5 | Cursed Key `onChestOpen(isBoss)`: a curse for non-boss chests only; the chest opens only on a click, so skipping avoids the curse | treasure screen offers open / skip; old chest rule opens only without Cursed Key | the choice exists for the net; it opened 91 of 91 Cursed Key chests (section A), a case for #1056 |

## Next checks

1. A3 done: drink tokens, default on without a gate (Philipp, 2026-11-15). Toy Ornithopter checked with javap the
   same day: `PotionPopUp` calls `potion.use`, then every relic's `onUsePotion`, and `ToyOrnithopter.onUsePotion`
   outside `COMBAT` calls `player.heal(5)` at once. The engine healed only in combat; fixed in
   `GameContext::drinkPotionAtIdx` (`STS_OOC_TOY_ORNITHOPTER_FIX`, on by default, `0` restores).
2. Step 3 for the combat rules C1/C3/C4: count how often the pruned edge would have been legal (logging only).
3. Hand the relic-left and Cursed Key chest cases (section A, D5) to #1056.

## Relevant code

- `apps/one_combat/run_driver.cpp` — `realOocChainStepBody`, `runFullRunOocPolicyStep`.
- `apps/one_combat/heart1_policy.cpp` — `ppoStep`, `ppoFallback`, `buildChoice`, `takeFreeRewards`,
  `eventFixedAction`.
- `apps/one_combat/ooc_tree_rules.cpp` — `treasureChestRuleAction`, `rewardRelicRuleAction`, `oocTreeRuleAction`.
- `src/sim/search/RunGoal.cpp` — `heartKeyAction`, `heartKeyActionAllowed`.
- `src/sim/search/GameAction.cpp` — `getAllActionsInState` and the per-screen enumerations, `isValidPotionAction`.
- `src/sim/search/SilverSearcher.cpp` — `enumerateActionsForNode`, `enumeratePotionActions`,
  `cardsEquivalentForSearch`, `bestAction`.
- `src/sim/search/NativeSilverBackend.cpp` — `runNativeSilverCombat` (context, loop guard, singleton skip).
- `tools/heart1/ppo_decision_sources.py` — the counts above.
