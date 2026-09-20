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
- the separate non-native exclusion manifest records `FOUR_BYRDS`: vanilla can
  form that event composition, but this pinned simulator has no
  `MonsterEncounter` or faithful four-slot layout for it; the live importer
  reports `silver_unsupported_four_byrds` explicitly;
- exact player damage-event bookkeeping when the observer's post-
  `AbstractPlayer.damage()` boundary is installed; each finalized public damage
  call is one event, and the last such unblocked damage is retained.

Protocol-v4 import now has one centralized mapping table for Java monster IDs,
encounter IDs, every simulator-supported vanilla monster move byte qualified
from the installed `desktop-1.0.jar`, player powers, monster powers, and
selection tasks. Cards, relics, and potions continue to use the canonical
`SaveFileMappings` converters rather than a second copy of those tables.

## Public-information rules

- The importer never consumes or accepts live RNG fields.
- An ordinary draw array is imported as an unordered multiset. Concrete order is
  retained only when `Frozen Eye` is present.
- `Runic Dome` remains fail-closed at the Java boundary. The observer now
  omits `nextMove`, `moveHistory`, `intent`, and `intentDamage` while the relic
  is active; native deferred hidden-intent support exists for native fixtures,
  but the live producer still does not provide the complete public pre-roll
  tracker needed to qualify a fair import.
- Java physical UUIDs are assigned monotonically by a battle-lifetime
  `SilverImportContext`. The registry resets only when the protocol session or
  combat instance changes and rejects duplicate UUID claims in one snapshot.
- Monster and player power `justApplied` is serialized when the installed
  runtime exposes the actual field through the bounded observer reflection
  helper; the importer rejects required powers when that field is unavailable.
- Bronze Orb Stasis is represented when the runtime exposes the public-facing
  `StasisPower.card` and Bronze Orb constructor slot: the exact physical card
  UUID/state is placed into native stasis slot 0 or 1. If either field is
  unavailable, only the active-Stasis snapshot is rejected.
- Hexaghost Divider damage is captured from the public Divider intent and
  retained by monster object identity after that move resolves, matching the
  native `miscInfo` value until the next public Activate/Divider cycle.

## Explicit current exclusions

These are deliberate boundaries, not silently fabricated defaults:

- live OOC `GameContext + PathHistory` import and OOC MCTS;
- Runic Dome live import (`silver_hidden_information_required` until the
  public pre-roll tracker is serialized);
- unknown Java card/relic/potion/power/task IDs;
- encounter or monster `miscInfo` values that are not present in the public
  runtime or cannot be derived from the current public tracker;
- combat observations from a producer that does not assert exact damage-event
  tracking; turn-level damage totals are not accepted as a substitute;
- resolving/action-queue snapshots;
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
