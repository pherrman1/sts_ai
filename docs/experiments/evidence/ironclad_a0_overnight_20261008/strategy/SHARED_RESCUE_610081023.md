# Seed610081023: two different preparation chains share one discovery rescue

This outcome-informed worked case finds **different first interventions**. FullHp changes a late campfire from REST to Shovel DIG, eventually adding Toxic Egg and Anchor. RemoveLow changes an early Cleric removal from Reaper to Strike and produces a substantially different deck and resource trajectory. The shared final win is not evidence that the gains add, that one decision uniquely caused either win, or that a combination should be run.

Only completed discovery source610081023 was numerically inspected. The machine packet contains hashed inputs, complete compact chronology, first-divergence public states, relevant gate records and combat summaries. No partial development, GEN2, confirmation or new game was opened/run.

## Custody and common reference

Wave3 uses source `b229f3ff2443b0decaacaa762d2a0c429f7e9d47`, binary `a8516aaae94c3ed91d5671ba5477c704ff1a42e53ce83061e1dddb846081d23a`. Wave4 removal uses source `d35b42b1d5dc9819ec0f157027c68912bb82b8b7`, binary `1dcc79169e60cc58865218cd66644dd2db61a9e9ceaafdf39c1b8a7b6600a8f5`. Each matched pair differs only in its declared candidate flag, apart from diagnostic output paths. Both share public8, optionalRecall1, original models and learned stopping.

The named Fprod trajectory is identical between these producers: all194 OOC/battle trace rows,425 combat profile rows excluding process diagnostic `combat_id`, strategic records and endpoints excluding elapsed seconds. Receipt completion, every recorded output hash, manifest/source/binary identity and current frozen model hashes were checked. This extends the parent overlap report's endpoint equality to this source's full available trajectory.

| Arm | Observed final encounter | Result | Final HP |
|---|---|---|---:|
| Fprod | Awakened One, floor50 | Loss | 0/72 |
| FullHp | Awakened One, floor50 | Win | 23/72 |
| RemoveLow | Awakened One, floor50 | Win | 16/72 |

All three traverse the same sequence of27 encounter identities. Their recorded searches have zero errors, descent aborts, engine-stop, nonterminal or turn-limit endpoints. These checks establish usable records, not causal quality.

## FullHp: late Dig choices, not a Smith upgrade rescue

The first185 OOC/battle trace rows match. At Act3 floor47, decision index160, both public roots show72/72HP,139 gold, the same41-card ordered deck, Shovel, Eternal Feather, two potions and no Dream Catcher. The baseline trace is `wave3/Fprod_5.trace.jsonl:795`; the candidate is `wave3/FullHp_5.trace.jsonl:796`. Only the post-state differs: baseline returns to MAP; candidate opens REWARDS.

The strategic records make the action identity explicit:

| Gate record | Available bits/actions | Q values | Selected action | Margin/ownership |
|---|---|---|---|---|
| Fprod strategic line239 | 0 REST;1 SMITH;5 DIG | 19.6332;15.5906;16.7352 | REST | 2.897907; V4 owned |
| FullHp strategic line240 | 1 SMITH;5 DIG | 15.5906;16.7352 | DIG | 1.144670; V4 owned |

The filter removes only REST, preserving the existing scores of SMITH and DIG. DIG is therefore the remaining qualified V4 action; random fallback does not own this changed action. `GameContext::chooseCampfireOption` maps bit5 to a random relic reward, and the next observed row acquires Toxic Egg (`FullHp_5.trace.jsonl:797`). Baseline REST heals nothing at72/72 and has no Dream Catcher reward.

The candidate also Digs at floor49 (`FullHp_5.trace.jsonl:804`, strategic line242), with DIG-versus-SMITH margin1.033460, then takes Anchor at line805. Baseline again takes V4-owned REST at full HP (`Fprod_5.trace.jsonl:801`, strategic line241, margin2.562386). Thus this is two late opportunities, not an isolated one-action experiment.

At the final boss, the serialized public pre-state differs **only by Toxic Egg and Anchor**. Both arms have the identical42-card ordered deck,72/72HP,150 gold and Liquid Bronze plus Fairy Potion. The floor48 reward is Iron Wave in both arms; it is an attack, so Toxic Egg's skill-upgrade acquisition mechanic has no observed card upgrade to explain here. The complete383 pre-boss combat profile rows, including floor48, also match after excluding `combat_id`.

Source establishes a concrete preparation benefit from Anchor: `BattleContext` adds10 starting block. It does not establish that Anchor alone caused the win. Both relic additions, their acquisition RNG/pool changes, and the fixed controller's subsequent search response belong to the observed treatment trajectory. At the first boss root the chosen action is still identical, while completed simulations differ4000 versus2000 under the common learned-stop controller. There is no retained exact counterfactual snapshot or one-relic ablation. FullHp finishes with Fairy Potion retained; that inventory fact is not a diagnosis of a missed potion line in Fprod.

Earlier FullHp REST eligibility already differed at floors6/8/12: each became a singleton SMITH owned by V4 where Fprod's gate declined to a fallback that also Smithed. Their actual public transitions and intervening combat records remain identical. Consequently floor47 is the first **executed public-state divergence**, not the first changed candidate list or owner.

## RemoveLow: Cleric removes a Strike instead of Reaper

The first21 trace rows and36 combat profile roots match. At Act1 floor5, both arms encounter The Cleric at72/72HP and160 gold. The identical V4 event gate declines: best-second margin0.001404 is below1 (`wave4_removal/*_5.strategic.jsonl:185`). The common event fallback chooses Purify, pays50 and opens REMOVE (`*_5.trace.jsonl:630`). This event choice is unchanged; source routes The Cleric through the generic random event fallback after V4 declines.

At the next identical public root, both have110 gold and14 cards, including Reaper acquired at floor3. `Fprod_5.trace.jsonl:631` removes Reaper; `RemoveLow_5.trace.jsonl:631` removes one Strike. The selector is in an EVENT room, so the dispatcher reaches Scum's `cardSelectPolicy`; the native shop removal owner does not apply. There is no separate V4 REMOVE gate. Source weights make the local mechanism unambiguous: Reaper30, Flame Barrier18, Cleave8, Anger6, Bash1 and basic Strikes/Defends0. The legacy negative-weight ascending order chooses Reaper; the enabled positive-weight ascending order chooses a basic-card tie, observed as Strike. The trace does not distinguish which identical Strike instance was removed.

The retained Reaper is upgraded at floor6 (`RemoveLow_5.trace.jsonl:634`); the REST and UPGRADE gates both decline, with margins0.192192 and0.903015, and the unchanged fallback chooses the upgrade. Fprod instead upgrades Flame Barrier. At floor10 both shop gates initially decline, but changed decks produce different native plans: Fprod buys Wild Strike then removes Defend; RemoveLow removes Defend first, then its subsequent V4-owned shop action buys Disarm. The latter shop REMOVE uses the unchanged native owner, not the new low-weight fallback rule. Floor5 is the only non-shop REMOVE exposure in the candidate's recorded run; later removals are shops.

Preparation continues to diverge. At floor22 Fprod's card gate takes Perfected Strike; RemoveLow's gate declines and fallback takes Feel No Pain. RemoveLow upgrades Feel No Pain at floor27 while Fprod rests from49 to70HP. RemoveLow retains the early Reaper+ and also takes the later Reaper reward that Fprod obtains at floor23. Its eventual42-card deck includes Disarm and Feel No Pain+, but it also has different attacks, draw cards and upgrades, one fewer recorded curse, no Potion Belt and only Fairy Potion before the boss.

This is not a monotonic HP advantage. RemoveLow exits the first Book of Stabbing and Slavers at72HP versus Fprod51/49, but exits Hexaghost28 versus35, Automaton14 versus26, and Giant Head26 versus53. Potion use/inventory differs, and battle-exit HP includes healing effects. The records do not isolate how much was due to Reaper, changed draw order, purchase choices, potion use or later search decisions. At floors47 and49, RemoveLow still takes V4-owned full-health REST. Its rescue therefore does not require fixing those late rest choices in the observed trajectory.

## Supported conclusion and limits

The evidence connects each opt-in rule to an actual changed decision at an identical serialized public root. FullHp creates two late relic rewards while preserving the observed deck and earlier combat trajectory; RemoveLow preserves an early Reaper and starts a long preparation divergence. Both independently win this selected source, through different observed chains. Neither path tests their combination or measures either decision's conditional win probability.

Public traces omit full RNG state, relic counters, bottle/misc metadata and complete combat hands/block. “Identical public root” means exact equality of the available serialized fields and offer, not a full simulator snapshot. Strategic scores are model outputs, not calibrated true win chances. No missing combat snapshot or unique winning alternative is reconstructed.

Reproducible evidence: `SHARED_RESCUE_610081023.json`, SHA256 `9772962fdecda7fdf7b8d4a3df11a90b6bd62abda13aa1e022a4a76f555b0821`; `build_shared_rescue_case.py::build()` rechecks custody and returns the packet using only the named completed discovery source. The CLI refuses to overwrite the existing packet. Fixed fresh development and final confirmation retain their separate evidential roles.
