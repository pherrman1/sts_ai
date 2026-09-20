# ADR-0013: Resolve semantic OOC intent at public decision boundaries

- Status: accepted
- Date: 2026-09-10
- Last verified: 2026-09-20

## Context

`GameAction` is the legal primitive simulator interface. Its packed reward and
selector indices describe current screen positions. Smith and removal-service
source clicks can defer the strategically meaningful target to another screen;
reward collection shifts indices. Conversely, Library reveals random cards
only after choosing Read, and Astrolabe exposes several successive selections.
A uniform fixed-length click macro would therefore either retain unstable
indices or choose across information and player-decision boundaries.

## Decision

Keep `GameAction` authoritative for execution and expose a shared typed
`OocSemanticAction` intent layer. Persist explicit effect/source IDs and
versioned canonical entity identities; preserve Smith's existing v1 identity.
Resolve legal primitives anew against each live intermediate state.

Combine source and target only for a deterministic single-target selector whose
complete candidates are public before the source click. Keep random-reveal and
multi-target source choices separate. Multi-target selectors expose one live
pick at a time, with no combinatorial card-subset enumeration. Automatic RNG
consequences are outcomes, never semantic identity.

Enumerate every available reward choice simultaneously. Individual card-group
skip, Singing Bowl and leaving all rewards are distinct actions. Enumeration
reports support and completeness explicitly. Execute on a transactional
`GameContext` copy with a detached map, committing only after resolution,
legality and boundary checks pass. This assumes repository-owned continuation
callbacks rather than arbitrary external closures with mutable side effects.
Execution rejects an active `g_onGameActionExecute` observer because external
observations cannot be rolled back. Source-level event fallback remains legal
when compound preconditions fail, including affordability and survivable Wing
Statue damage.

The semantic core is opt-in. Its action features are not compatible inputs for
models trained on primitive bits. Opt-in OOC MCTS uses semantic transitions
with V4 only as a source-primitive prior: qualified source mass is split equally
among targets; states without complete V4 source coverage use uniform priors.
This adapter bridge requires no retraining and does not qualify copied hidden
noncombat RNG as a fair generative environment. Feeding semantic features to
a learned scorer still requires a separate schema/model change.

## Alternatives and consequences

Keeping only primitive clicks preserves screen mechanics but splits a public
single-target transaction into source and target labels and leaves identity
dependent on transient positions. Caching full click scripts avoids neither
index drift nor newly revealed information. Enumerating joint multi-select
sets expands combinatorially and changes the player-decision boundary. The
chosen representation instead needs explicit target freshness, completeness
and manual-path parity checks, but can reuse the existing simulator effects.

Default policy selection and training remain unchanged. Reward-origin relic
continuations are fixed at the primitive layer so selector completion or child
reward completion returns to the remaining original rewards. That correction
is needed for order-free collection and applies to semantic and primitive
callers equally. Multi-select removal uses sorted descending original deck
indices to preserve intended targets under arbitrary pick order, while random
transform outcomes retain player selection order.

## Evidence and affected files

- `include/sim/search/OocSemanticAction.h`: explicit IDs, typed targets,
  enumeration and execution results.
- `src/sim/search/OocSemanticAction.cpp`: canonical keys, legal live resolution,
  event-selector metadata and transactional execution.
- `src/game/GameContext.cpp::chooseEventOption`, `openCardSelectScreen`,
  `chooseSelectCardScreenOption`, `obtainRelic`: public-target, reveal and
  sequential-selection boundaries and existing RNG effects.
- `src/sim/search/GameAction.cpp::executeRewardsAction`: separate card-group
  skip/whole-screen leave and nested reward continuation.
- `apps/test_ooc_semantic.cpp::runOocSemanticTests`: literal typed keys, complete
  non-mutating enumeration, source/manual state and RNG parity, stale and
  ambiguous target rejection, reveal and sequential-selection boundaries.
- `apps/test.cpp::testOocSemanticSmith`: literal Smith v1 and primitive parity.
- `src/game/Deck.cpp::removeSelected`: stable removal of original target indices.
- `apps/test_ooc_reward_continuation.cpp::runOocRewardContinuationTests`:
  collection order, Sapphire pairing, nested reward/selector continuation and
  descending/permuted removal and transformation picks.
- `tools/ooc_pipeline_contract.py::validate_corpus`: current whole-combat
  schema is not a semantic-action dataset schema.
- [Maintained OOC architecture](../docs/knowledge-base/architecture/out-of-combat.md#semantic-ooc-decisions)
  records supported families and the future producer/trainer adoption boundary.
