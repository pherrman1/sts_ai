# Combat potion-generation support contract

Last verified: 2026-09-15 against the main simulator and frozen corpus.

## Purpose

The V1 artifact certifies consumption-only RAW combat potion transitions: each active slot retains its identity or becomes empty. The qualified V2 artifact additionally models native Entropic Brew generation and learned use/discard/recursive continuation. Neither contract qualifies gameplay performance or off-color card accuracy.

## Current implementation

V1 Python `potion_consumption_only` and the legacy native domain exclude explicit Alchemize and Entropic Brew, retaining the original gold/Writhing/Ritual exclusions. V2 `nativeComposedSupportReasons` uses its qualified near-full domain: Brew, gold, Writhing and Ritual are supported except initially held Smoke, pre-existing `smokeBombUsed`, or Writhing with Ritual Dagger. Explicit Alchemize, active unqualified Lizard Tail, unsupported carriers, HP legality and inherited RNG gates remain. Off-color alone does not reject. Support depends only on visible pre-state. Generated Smoke/ESCAPE through Brew remains possible in supported states.

STS1 prohibits random temporary generation of healing cards, including Alchemize.
The [developer patch notes](https://store.steampowered.com/news/posts/?appids=646570&enddate=1540508225&feed=steam_community_announcements)
record this rule. Explicit Alchemize can still be copied or replayed; its visible
presence is excluded irrespective of inventory capacity or Sozu.

## Important data flow

| Route | Executed source and potion consequence |
| --- | --- |
| Entropic Brew | `BattleContext::drinkPotion` generates `potionCapacity` results through `returnRandomPotion`, inserting through `obtainPotion` when allowed. V1 excluded; V2 uses native hypothetical RNG generation. |
| Explicit Alchemize | STS1 potion generator; no execution case exists in this simulator's `BattleContext::useCard`. Excluded despite this implementation gap. |
| Discovery, attack/skill/power potions | `Actions::DiscoveryAction` → `generateDiscoveryCards` → `CombatCardPool` / `CombatTypeCardPool`. Alchemize absent. |
| Chrysalis, Metamorphosis | `PutRandomCardsInDrawPile` uses `CombatTypeCardPool`. Alchemize absent. |
| Dead Branch | `BattleContext::triggerAndMoveToExhaustPile` uses `getTrulyRandomCardInCombat` → `CombatCardPool`. Alchemize absent. |
| Nilry's Codex | `Actions::CodexAction` uses `generateDiscoveryCards` with Ironclad and invalid type → `CombatCardPool`. Alchemize absent. |
| Infernal Blade, Enchiridion | Typed combat pools, attack and power respectively; Alchemize absent. |
| Jack of All Trades, Transmutation, Toolbox, colorless potion | Combat colorless pool excludes Alchemize. V1 gold-mutation exclusions remain; V2 uses qualified shared gold mechanics. |
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
96,231 retains the original independent exclusions. That historical source-audit receipt predates composition qualification; V2 extends support as described below.

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
reproduces all 3,208 frozen pre-Brew rows and 3,106 generation rounds. The 112
proven recursive-consumption cases comprise 108 surviving RAW transitions
(86 TRAIN, 11 VALIDATION, 11 TEST) and four deaths. Multiple rounds alone do not
prove recursion when more than one Brew was initially held.

The accepted fair-planner contract uses a full-width planner RNG draw to seed a
fresh native hypothetical potion RNG on the first Brew use. Reuse that stream
through every recursive generation in the imagined combat and retain its
advanced state in sampled RAW `combatRng[4]`. If Brew is unused, copy the
historical potion RNG. Generating from a hypothetical stream and then restoring
the historical stream is inconsistent and forbidden. Historical RNG replay
reconstructs teacher generation-body labels only; it is never a predictor input.

The shared 64-action trajectory decoder distinguishes special-potion use from
discard: the lower 32 actions clear slots without triggering Brew or Smoke;
the upper 32 also trigger the selected special potion. Ordinary consumption
retains its original categorical interpretation. Bosses prohibit Smoke use,
while Smoke discard remains legal. Native generation and insertion supply new
identities; the shared decoder learns use, discard, retention and recursive
continuation. Teacher likelihood exactly marginalizes compatible orderings and
tracks generated Colorless/Skill/Forge effects for downstream mechanics.

The original corpus and source splits are unchanged. The final V2 cohort supports 505,935/510,030 states and 51,036/51,441 TEST states. Composition on that exact supported set passes every nonempty ≤0.1-nat slice gate; 1,633,152 draws have zero recorded hard violations. Export and Python/native probability/complete-state parity pass, and the native predicate reproduces the exact ordered cohort hashes. The tracked artifact remains explicit opt-in and MCTS remains OFF by default. These TEST results are reused development evidence, including the earlier Writhing maxHP repair. Original whole-union Smoke/relic failures and three unsuccessful bounded repairs remain preserved; no fourth repair or failed checkpoint promotion occurred. See the [final staged report](../../experiments/evidence/near_full_combat_support_2026-09-14/REPORT.md).

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
other off-color cards remain incompletely simulated. The original consumption-only correction did not train models. V2 uses separately qualified refits on unchanged splits/data; its final exclusion pass changes no weights and establishes no win rate.
