# Live Silver combat capability census

Status: implementation baseline for protocol-v4 live combat import.

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
- up to five encounter slots, including dead/escaped slots when the observer
  supplies them, so target indices are not compacted after a death.

Protocol-v4 import now has one centralized mapping table for Java monster IDs,
encounter IDs, monster move bytes, player powers, monster powers, and selection
tasks. Cards, relics, and potions continue to use the canonical
`SaveFileMappings` converters rather than a second copy of those tables.

## Public-information rules

- The importer never consumes or accepts live RNG fields.
- An ordinary draw array is imported as an unordered multiset. Concrete order is
  retained only when `Frozen Eye` is present.
- `Runic Dome` remains fail-closed at the Java boundary. Native deferred hidden
  intent support exists for native fixtures, but the current observer does not
  yet provide the complete public pre-roll tracker needed to qualify a live
  import.
- Java physical UUIDs are assigned monotonically by a battle-lifetime
  `SilverImportContext`. The registry resets only when the protocol session or
  combat instance changes and rejects duplicate UUID claims in one snapshot.
- The installed game JAR exposes power amounts but no public `justApplied`
  field. The producer therefore serializes the schema field conservatively as
  `false` at stable user boundaries; this is a producer limitation, not proof
  that every transient application phase was observed.

## Explicit current exclusions

These are deliberate boundaries, not silently fabricated defaults:

- live OOC `GameContext + PathHistory` import and OOC MCTS;
- Runic Dome live import;
- unknown Java card/relic/potion/power/task IDs;
- encounter, move, or monster `miscInfo` values that are not present in the
  public schema or cannot be derived from the current public tracker;
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
power/relic/potion mapping, and a visible single-card selection. Existing
schema-v2 native-parity fixtures remain in place as a compatibility regression.

Knowledge impact: this page records the current importer/native boundary and
the explicit live exceptions; it does not claim gameplay equivalence for any
mechanic outside the listed wire and public-information contract.
