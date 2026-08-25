# Isolated Silver combat port: review-boundary evidence

Status: implementation review requested; no gameplay benchmark has been run.

## Provenance and scope

- sts_ai base: `af4b985125e08f150e658c32086ea3909de41ef7`.
- Silver source: `daniel-ziegler/sts_lightspeed@84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`.
- Attribution: `THIRD_PARTY_NOTICES.md` and
  `third_party/silver_lightspeed/PORT_NOTICE.md`; copied/adapted files retain
  MIT/SPDX headers.
- Production isolated closure: combat `Actions`, `BattleContext`,
  `CardInstance`, `CardManager`, `CardQueue`, `Monster`, `MonsterGroup`,
  `MonsterMoveDamage`, `MonsterSpecific`, and `Player`; game `Card`; search
  `Action`, `BattleSearcher`, `ExpertKnowledge`, and `SimpleAgent`; plus the
  two narrowly extracted upstream helper blocks for `RelicContainer` and
  combat random-card/potion helpers.
- Deliberately excluded: upstream apps, bindings, Python/communication stack,
  full-run controller, training, and deployment code. The fixture-only native
  parity runner supplies tiny `GameContext::hasRelic`/`Deck::size` definitions
  rather than linking those full-run objects.

## Live-to-isolated protocol

`BattleStateWire` is a type-free, value-only protocol. It copies visible
player HP/max HP/block/energy, powers/status counters, relic ownership and
counters, potions, hand/limbo/stasis/piles, visible monsters, player input and
card-select state, combat counters, ascension/floor/encounter, and the small
public run context used by Silver evaluation/rollout (act and Omamori).

It contains **no** live pointer, live RNG state, hidden draw index, or
Runic-Dome materialized move. A fresh internal Silver one-RNG state is seeded
from a deterministic public root seed (`battle seed`, `floor`, decision
ordinal), never from any of sts_ai's six combat RNG streams.

The materializer constructs a private `sts_silver::BattleContext`; its only
intentional vendored-model adaptation is `CardPile::assignInformationState`, a
bulk constructor for an already sanitized `[known bottom | canonical unknown |
known top]` information set. It never observes the live pile.

### Knowledge tracker and mutation coverage

`CombatKnowledgeState` is owned outside `BattleContext` and receives only
non-mutating observer events. It is not serialized, compared as simulator
state, used by Searcher2/3, or allowed to consume RNG.

| Live operation family | Observer result |
| --- | --- |
| CardManager top placement | `KNOWN_TOP_PLACED` with selected card identity |
| CardManager bottom placement | `KNOWN_BOTTOM_PLACED` with selected card identity |
| ordinary draw/pop and explicit draw-pile removal | known fact removed, otherwise cardinality tracked |
| discard-to-draw reshuffle and ordinary shuffle | positional stacks cleared; full-order flag cleared unless legitimately observed |
| random insertion/shuffle-in | positional facts conservatively invalidated / random insertion recorded; no concrete index exported |
| Frozen Eye | full-order visibility flag permits the converter to reproduce the visible live order |
| Runic Dome monster roll | public roll inputs recorded before materialization; actual `moveHistory` is redacted |

The final broad source audit inspected `drawPile` mutations in `CardManager`,
`Actions`, `BattleContext`, `MonsterSpecific`, and card-specific code. Several
effects use the existing `CardManager` primitives and therefore share their
events. If an unexpected public pile-size transition is observed at a decision
boundary, the tracker conservatively clears positional knowledge rather than
infering order from the concrete vector. This is intentional information loss,
not an order leak.

## Action and multi-select boundary

`SemanticAction` carries visible card-instance identity (card ID, unique ID,
special data, upgrade, current/turn cost, free-to-play, retain), target,
potion slot/identity, select source/task, and final selected-card identities.
The live resolver requires exactly one matching current action and rejects
missing/ambiguous matches; no Silver hand index crosses the boundary.

For `EXHAUST_MANY` and `GAMBLE`, the approved UI/action-surface protocol
adapter performs Silver's sequential `SINGLE_CARD_SELECT` decisions privately
with a persistent searcher, exact reroot where available and upstream-style
`setRoot` fallback. Each subdecision receives the full configured budget. The
final `MULTI_CARD_SELECT` is not executed privately: its selected visible card
identities are lowered once to the unchanged live atomic subset action. The
trace records selections, selectedBits, reroot/fallbacks, decision count, and
total simulations. This means future benchmark reports must distinguish native
Silver transaction compute from one atomic Searcher3 multi-select search.

## Checks run

All commands used the temporary Linux build directory
`/tmp/sts_ai_silver_bridge_build`; no gameplay seeds or GCP work were run.

| Check | Result |
| --- | --- |
| build `silver-bridge-test`, `silver-integration-test`, `combat-knowledge-neutrality-test`, `unit-test`, `silver-native-test`, `silver-native-parity-runner`, `one_combat` | pass (existing `one_combat` narrowing warnings only) |
| `silver_bridge_test` | `silver_bridge_boundary PASS`: materialized hidden-order/RNG invariance, Frozen Eye, stale fail-closed, Runic Dome redaction/pending inputs, known top/bottom order, GAMBLE/EXHAUST private transaction |
| `combat_knowledge_neutrality_test` | `PASS outcome=1 draws=40`: null observer vs installed observer had identical guarded-combat trace/outcome/piles and relevant RNG counters |
| `silver_integration_test` | `PASS outcome=1 decisions=12 simulations=96`: private conversion/search/resolution/live execution, no diagnostics failures |
| `test combat_knowledge` | pass |
| `test silver_semantic_action` | pass |
| `silver_native_test` | `silver_searcher_link_closure PASS` |
| vendored native runner, `det 16` | root edges/visits/Q/nodes/chance/transposition report exactly equals clean upstream runner |
| vendored native runner, `known_top 16` | root edges/visits/Q/nodes/chance/transposition report exactly equals clean upstream runner |
| `git diff --check` | pass before final documentation addition; rerun required immediately before commit |

Direct upstream comparison used a clean detached worktree at the pinned Silver
SHA. The same untracked fixture runner and minimal helper blocks were compiled
against it. Exact current fixture reports:

| fixture | root edges | nodes | chance outcomes | deterministic transpositions | chance transpositions | result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| deterministic opening (`det`, 16) | 4 | 16 | 6 | 0 | 2 | exact upstream match |
| known-top opening (`known_top`, 16) | 4 | 16 | 8 | 0 | 0 | exact upstream match |

## Intentional deviations / remaining uncertainty

1. `assignInformationState` is a bridge-only CardPile bulk constructor. It
   exists only to materialize a sanitized information state without replaying
   singleton normalization; it does not change Silver search transitions.
2. Live sts_ai uses atomic multi-select actions. The private transactional
   adapter preserves upstream's sequential Silver decision protocol and only
   lowers the final confirmation; it is a UI-surface adapter, not a search
   policy alteration.
3. Unknown random insertion and unexpected unclassified public pile-size
   transitions conservatively forget positional facts. This can lose useful
   knowledge but cannot inspect or leak hidden order.
4. The native parity harness is operational and has two exact direct upstream
   fixtures. Its fuller requested corpus (reshuffle, random monster/potion,
   card select, duplicate hand, transposition/cycle, and sequential select
   trace comparison) remains incomplete and is an explicit review gate before
   any scientific gameplay comparison.
5. No CI run, full upstream parity corpus, default-off full application run,
   or gameplay seed benchmark has been performed in this implementation
   checkpoint. The default-off guarded whole-combat observer neutrality test
   passed; the backend is opt-in through `STS_SILVER_SEARCH=1`.

Recommendation: review this implementation SHA before any gameplay experiment.
