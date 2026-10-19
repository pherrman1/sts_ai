# Live Silver combat capability census

Status: protocol-v4 live combat import with the full pinned-native encounter
manifest qualified at the wire boundary.

This page records the bounded local census used by the general live importer.
The native `BattleStateWire` and `SilverConversion` paths are the authority;
this page does not promote a mechanic merely because an enum exists.

## Supported at the wire boundary

The pinned native boundary has explicit representations for:

- arbitrary `CardId` instances that are accepted by `SaveFileMappings` and
  `CardInstance`, including upgraded/misc/cost/free-to-play/retain state;
- Ironclad and colorless card instances in hand, draw, discard, exhaust, limbo,
  and the two native stasis slots;
- public draw knowledge as known-bottom, unknown multiset, known-top, and
  full-order-visible (`Frozen Eye`);
- all native player scalar fields in `PlayerWire`, native player status bits and
  counters, native relic possession bits/counters, and native monster scalar,
  status, move-history, unique-power, and `miscInfo` fields;
- native card-selection tasks enumerated by `CardSelectTask`, including the
  sequential Silver transaction for `EXHAUST_MANY` and `GAMBLE`;
- native potion slots and semantic potion actions, including targeted and
  discard forms;
- all 63 reachable `MonsterEncounter` values in the pinned native enum, with
  an explicit manifest entry; the only excluded enum value is the `INVALID`
  sentinel, which is not a reachable Ironclad combat;
- up to five encounter slots, including dead/escaped slots when the observer
  supplies them, with a battle-lifetime Java-object-to-slot registry so target
  indices are not compacted after a death, escape, summon, or replacement.
- the ordinary `LARGE_SLIME` split preserves native child slots 0 and 1;
  `SLIME_BOSS` remains the separate 0 and 2 layout.
- the separate non-native exclusion manifest records `FOUR_BYRDS`: vanilla
  defines a "4 Byrds" encounter, but no normal act pool or event generates it
  (Act 2 uses "3 Byrds" and "Chosen and Byrds"), so it is not expected in
  standard runs (**Unverified** against `desktop-1.0.jar`). This pinned
  simulator has no `MonsterEncounter` or four-slot layout for it; the live
  importer reports `silver_unsupported_four_byrds` explicitly;
- exact player damage-event bookkeeping when the observer's post-
  `AbstractPlayer.damage()` boundary is installed; each finalized public damage
  call is one event, and the last such unblocked damage is retained.

Protocol-v4 import now has one centralized mapping table for Java monster IDs,
encounter IDs, every simulator-supported vanilla monster move byte qualified
from the installed `desktop-1.0.jar`, player powers, monster powers, and
selection tasks. Cards, relics, and potions continue to use the canonical
`SaveFileMappings` converters rather than a second copy of those tables.
The producer-side exceptions are part of that contract: Cultist Ritual reads
`RitualPower.skipFirst` as native `justApplied`, `SlaverBlue` emits native
`miscInfo` zero, Java `Weakened` maps to native player `Weak`, and Java
`Flex`/`FlexPower` maps to native player `LoseStrength` (the pending temporary
Strength loss).

## Public-information rules

- The importer never consumes or accepts live RNG fields.
- An ordinary draw array is imported as an unordered multiset. Concrete order is
  retained only when `Frozen Eye` is present.
- `Runic Dome` omits `nextMove`, `moveHistory`, `intent`, and `intentDamage`.
  Audited monster groups use public executed history and pre-roll state for
  deferred hidden intents, including Spot Weakness's attack predicate. Small
  Acid Slime's deterministic continuation uses an explicit public-derived
  known-next proof. The qualified roster and lifecycle limits are maintained
  in [live-model-inspector.md](../operations/live-model-inspector.md); other
  monsters and unaudited overrides remain fail-closed.
- Java physical UUIDs are assigned monotonically by a battle-lifetime
  `SilverImportContext`. The registry resets only when the protocol session or
  combat instance changes and rejects duplicate UUID claims in one snapshot.
- Monster and player power `justApplied` is serialized when the installed
  runtime exposes the actual field through the bounded observer reflection
  helper; the importer rejects required powers when that field is unavailable.
  `RitualPower.skipFirst` is the qualified producer exception for Cultist
  Ritual, `Weakened` is the qualified Java alias for native `Weak`, and Flex's
  temporary Strength loss is represented by native `LoseStrength`.
- Bronze Orb Stasis is represented when the runtime exposes the public-facing
  `StasisPower.card` and Bronze Orb constructor slot: the exact physical card
  UUID/state is placed into native stasis slot 0 or 1. If either field is
  unavailable, only the active-Stasis snapshot is rejected. A dead orb keeps
  its Stasis power after `StasisPower.onDeath` has returned the card under the
  same UUID; the importer drops that entry (native `returnStasisCard` empties
  the slot) when the UUID is present in another pile, and rejects it otherwise.
- Hexaghost Divider damage is captured from the public Divider intent and
  retained by monster object identity after that move resolves, matching the
  native `miscInfo` value until the next public Activate/Divider cycle. Under
  Runic Dome the tracker instead records public player HP at Activate execution;
  Divider and the subsequent orb phase are derived without reading intent.

## Explicit current exclusions

The currently qualified live Silver combat domain is Ironclad. All autonomous
live OOC shop candidate paths (V4, semantic OOC MCTS, native V, shop beam, and
action-NN) exclude Prismatic Shard through the shared policy-support
predicate, while a displayed Shard is allowed to remain a visible shop choice
and is not treated as a wholly unsupported shop. An Ironclad combat import fails closed with
`silver_off_color_card` when a GREEN, BLUE, or PURPLE card is present in the
projected combat card state; RED, COLORLESS, curse, and status cards remain
accepted. The existence of other-character enums and card pools does not mean
those cards are implemented by `BattleContext`.

These are deliberate boundaries, not silently fabricated defaults:

- Runic Dome outside its audited public-history/lifecycle domain;
- unknown Java card/relic/potion/power/task IDs;
- encounter or monster `miscInfo` values that are not present in the public
  runtime or cannot be derived from the current public tracker;
- combat observations from a producer that does not assert exact damage-event
  tracking; turn-level damage totals are not accepted as a substitute;
- ordinary resolving/action-queue snapshots; qualified card selectors instead
  preserve exact public pending card/action tails, including source cleanup,
  as described in the inspector contract;
- selection options that exceed the native `CardSelectWire` public option
  capacity or require unrevealed random choices;
- native mechanics that are absent from the pinned simulator implementation.

An exclusion must be reported with a specific `silver_*` reason. The generic
fallback `silver_state_parity_failure` is reserved for a post-materialization
bridge failure.

## Verification surface

The focused importer fixture covers protocol-v4 import, upgraded/generated
card UUID stability, hidden draw-order non-leak, Frozen Eye order visibility,
power/relic/potion mapping, active Stasis card identity, sparse stable slots,
burning-elite acceptance, group-bit preservation, and card selection. The same
test contains independent literal move-byte checks and a native construction,
public-render, import, exact search-state parity, and one-simulation
Silver-decision sweep for all 63 reachable encounters. It also runs a bounded
dynamic-transition corpus using producer-shaped public observations rather than
copying native status fields: ordinary Large Slime split (slots 0/1),
Reptomancer summon, Darkling Regrow, Bronze Orb Stasis, and Awakened One stage
2. Negative/sentinel amounts are covered for the boolean monster powers Minion,
Asleep, Regrow, Stasis, and Painful Stabs. Existing schema-v2 native-parity
fixtures remain in place as a compatibility regression.

Knowledge impact: this page records the current importer/native boundary and
the explicit live exceptions; it does not claim gameplay equivalence for any
mechanic outside the listed wire and public-information contract.
