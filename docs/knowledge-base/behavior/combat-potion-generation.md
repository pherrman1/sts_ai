# Combat potion-generation support contract

Last verified: 2026-09-14 against the main simulator and frozen corpus.

## Purpose

Certify visible inputs for consumption-only RAW combat potion transitions.
Each slot must retain its pre-combat identity or become empty through consumption
in an active slot. Creation, swaps and substitution are forbidden. This is a
support correction for frozen inference; it does not qualify gameplay performance
or the accuracy of off-color card simulation.

## Current implementation

Python `potion_consumption_only` and `nativeComposedSupportReasons` retain
Ironclad eligibility and exclude explicit **Alchemize** and **Entropic Brew**.
Off-color alone does not reject. No other combat potion-generation route was
found. All independent exclusions remain: Writhing Mass, Ritual Dagger, gold
mutation gates, Smoke Bomb, active unqualified Lizard Tail, unsupported relic
carriers, HP envelope and legality, and inherited RNG contracts.

STS1 prohibits random temporary generation of healing cards, including Alchemize.
The [developer patch notes](https://store.steampowered.com/news/posts/?appids=646570&enddate=1540508225&feed=steam_community_announcements)
record this rule. Explicit Alchemize can still be copied or replayed; its visible
presence is excluded irrespective of inventory capacity or Sozu.

## Important data flow

| Route | Executed source and potion consequence |
| --- | --- |
| Entropic Brew | `BattleContext::drinkPotion` generates `potionCapacity` results through `returnRandomPotion`, inserting through `obtainPotion` when allowed. Excluded. |
| Explicit Alchemize | STS1 potion generator; no execution case exists in this simulator's `BattleContext::useCard`. Excluded despite this implementation gap. |
| Discovery, attack/skill/power potions | `Actions::DiscoveryAction` → `generateDiscoveryCards` → `CombatCardPool` / `CombatTypeCardPool`. Alchemize absent. |
| Chrysalis, Metamorphosis | `PutRandomCardsInDrawPile` uses `CombatTypeCardPool`. Alchemize absent. |
| Dead Branch | `BattleContext::triggerAndMoveToExhaustPile` uses `getTrulyRandomCardInCombat` → `CombatCardPool`. Alchemize absent. |
| Nilry's Codex | `Actions::CodexAction` uses `generateDiscoveryCards` with Ironclad and invalid type → `CombatCardPool`. Alchemize absent. |
| Infernal Blade, Enchiridion | Typed combat pools, attack and power respectively; Alchemize absent. |
| Jack of All Trades, Transmutation, Toolbox, colorless potion | Combat colorless pool excludes Alchemize. Existing gold-mutation exclusions remain independently. |
| Distraction, Creative AI, Magnetism, Hello World, Foreign Influence | Off-color execution is incomplete or absent; Creative AI/Magnetism generation is commented out in `Player::applyStartOfTurnPostDrawPowers`. STS1 random generation cannot introduce Alchemize; no simulator potion write exists here. |
| Copy/replay effects | Operate on existing cards; explicit Alchemize already rejects the input. |
| White Beast Statue, ordinary rewards, shops and events | `GameContext` reward/acquisition routes occur outside the RAW combat boundary. They are not combat potion-generation routes. |
| Fairy in a Bottle and ordinary potion use/discard | Consume existing potion slots; no new identity introduced. |

The complete combat inventory-write search finds `BattleContext::obtainPotion`
(first empty slot; capacity and Sozu guards) and `discardPotion` (empty slot).
The only executed caller of combat `obtainPotion` is Entropic Brew. Initialization
copies inventory, and `exitBattle` copies it back before reward construction.
All four class arguments and all typed/colorless combat pools are tested for
absence of Alchemize. These pools currently use Ironclad contents even for other
class arguments; class simulation correctness is outside this correction.

## Invariants and assumptions

Support uses visible pre-state only. Corpus outcomes are validation evidence,
never eligibility inputs. The source audit supports the predicate; observed
absence of violations alone is not its justification. Inventory identity is
checked on every supported corpus row, including terminal outcomes. Existing
RNG, copy-through and victorious relic trajectory checks are retained.

The [frozen census evidence](../../experiments/evidence/potion_generation_support_2026-09-14.md)
accounts for all 510,030 rows: support 322,644 → 413,799, original TEST
32,164 → 41,454, zero supported potion-identity violations. Remaining fallback
96,231 retains the original independent exclusions. Distribution qualification
has not been extended to recovered rows.

## Native Brew development boundary

`Game::returnRandomPotion` in combat-limited Ironclad mode draws rarity at
65% common /25% uncommon /10% rare, then returns uniformly within that rarity
from the native pool after excluding Fruit Juice. The initial pool candidate is
discarded in limited mode. Bounded rejection must replay native raw RNG steps,
not advance a counter generically. Brew generates `potionCapacity` results on
every use even if the inventory is full or Sozu prevents insertion; insertion
searches only the active capacity slots. Generated Brew can be consumed again,
and generated Smoke Bomb can cause escape.

The explicit-origin development helper `tools/combat_transition_brew.py`
reproduces all 3,208 frozen pre-Brew rows and 3,106 generation rounds, including
112 recursive-consumption cases. This generator audit does not qualify a learned
consumption trajectory or change live support. Independent hypothetical planner
RNG generation and exact replay from preserved historical potion RNG are distinct
contracts. Their origin policy remains a material open question in the near-full
support continuation; neither is silently substituted. See the
[bound replay and origin comparison](../../experiments/evidence/near_full_combat_support_2026-09-14/brew-native-generation-v2.json).

## Relevant code

- `tools/combat_transition_frozen_composition.py::potion_consumption_only`
- `apps/one_combat/combat_transition_native_contract.cpp::nativeComposedSupportReasons`
- `include/constants/CardPools.h::CombatCardPool`, `CombatTypeCardPool`, `CombatColorlessCardPool`
- `src/game/Game.cpp::generateDiscoveryCards`
- `src/combat/BattleContext.cpp::obtainPotion`, `drinkPotion`, `triggerAndMoveToExhaustPile`
- `src/combat/Actions.cpp::CodexAction`, `PutRandomCardsInDrawPile`
- `tools/combat_transition_potion_support_audit.py`

## Known limitations

The predicates must be re-audited if combat card pools, potion inventory writes,
or temporary generation semantics change. Explicit Alchemize and several
other off-color cards remain incompletely simulated. This correction does not
train models, change splits or data, tune sampling, or establish win rate.
