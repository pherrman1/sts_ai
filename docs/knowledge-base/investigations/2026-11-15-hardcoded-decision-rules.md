# Hardcoded decision rules: inventory and firing rates (#1055)

Status: **open**, step 1 of [#1055](https://github.com/pherrman1/sts_ai/issues/1055) (inventory) done; step 2
(Java check), step 3 (shadow) and step 5 (paired gates) open.

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
| A1 | `ppoStep` → `takeFreeRewards(gc, false)` | takes every gold reward before the net sees the screen | 22.9 / game | **No** (gold has no downside; Ectoplasm blocks the gain either way). Step 2: confirm no gold reward carries a cost | keep (no choice) |
| A2 | `buildChoice` `discardTokens` | a potion discard token exists only when an offered potion is blocked by full slots, without Sozu (rewards; shop when affordable) | offered in 5,539 decisions, chosen 2,108 (2.4 / game) | Little: discarding elsewhere gains nothing out of combat | keep |
| A3 | `getAllActionsInState` (no potion actions) | the three potions the engine lets you drink out of combat (`isValidPotionAction`: Blood Potion, Fruit Juice, Entropic Brew) have **no drink token**; the net can only carry them into combat or discard them | 51 of the 2,108 discards threw one away (Blood Potion 41, Entropic Brew 8, Fruit Juice 2) | **Yes**: drinking dominates discarding (heal / +5 max HP / refill) | add drink tokens (net decides); step 2 checks Java `canUse` out of combat |
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
| C1 | `SilverSearcher::enumeratePotionActions` | discarding a potion is an edge only when it frees a slot for a held Entropic Brew (no Sozu) | not counted | Inference: little for Ironclad (no other in-combat potion source without Prismatic Shard / Alchemize) | step 2; count |
| C2 | same | Fairy in a Bottle is never an edge | – | no, if Java `FairyPotion.canUse` is false (step 2) | keep |
| C3 | same, `escapeForfeitsRun` (`NativeSilverBackend`) | Smoke Bomb is no edge when escape is blocked, or at the Act-3 burning elite without the Emerald Key under `STS_COLLECT_KEYS` | not counted | no under the Heart objective (escape ends any Heart attempt); a rule of the objective | keep; count |
| C4 | same | Gambler's Brew with an empty hand is no edge | not counted | no (it would only use up the potion) | keep |
| C5 | `cardsEquivalentForSearch`, duplicate potions | equal cards / potions share one edge | – | no when the equivalence is exact (id, upgrade, cost, cost for turn, free-once, retain, special data) | keep |
| C6 | `runNativeSilverCombat` loop guard | forced End Turn after 50 consecutive no-progress decisions (`STS_SILVER_LOOP_GUARD`) | **0** in 1,056 gate games | no (a stall guard) | keep |
| C7 | same; `BattleContext` | abort after 1,000 decisions; `STS_COMBAT_TURN_CAP=100` | not counted here | no (stall guards) | keep |
| C8 | `searchGumbelRoot`, `skipSingletons` | a root with one legal action is not searched | – | no | keep |
| C9 | `Expert::getPlayOrdering`, `bestAction` | enumeration order; ties of root visits go to the first edge | – | only in exact ties | keep |

Hand-made parts of the combat search that are not decision rules but shape every combat decision (out of scope
here, owned by the combat value-net and Gumbel threads): the leaf score (HP, potions, max HP, gold, escape penalty,
win bonus), the playout policy (greedy with the block rule, the learned g7f_E card table), the prior-share stop
(H = 0.9, ADR-0066) and the hand-set Act-4 budgets.

### D. Choice-set questions for step 2 (Java, javap on the PC)

1. A3: Java `canUse` out of combat for Blood Potion, Fruit Juice, Entropic Brew (and that no other potion is usable
   on the map).
2. A1: no gold reward with a cost.
3. C2: `FairyPotion.canUse`; C3: `SmokeBomb.canUse` (boss room, back attack / Surrounded); C4: Gambler's Brew with
   an empty hand.
4. Rest site (`getAllRestActions`): Peace Pipe and Shovel are offered without checking for a removable card / a
   dig; Recall only with keys enabled.
5. Card-select screens have no cancel (shop removal, events); Java lets the player back out of the shop removal.
6. Chest relic versus Sapphire, Black Star second relic, Ectoplasm, Sozu (potions still offered), Cursed Key,
   Bottled relics' card choice, Calling Bell / Cauldron / Orrery reward screens.

## Next checks

1. Step 2 above (needs PC access for javap).
2. A3: drink tokens for the three out-of-combat potions (new zero-initialised tokens; the net decides). Only after
   step 2 confirms the Java rule; a behaviour change, so a paired A20 gate (typed go).
3. Step 3 for the combat rules C1/C3/C4: count how often the pruned edge would have been legal (logging only).
4. B rows: hand the relic-left cases (section A) to #1056.

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
