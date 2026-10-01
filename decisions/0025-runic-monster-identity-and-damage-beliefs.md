# ADR-0025: Runic monster identity and persistent damage beliefs

Date: 2026-10-02
Status: accepted

## Context

Runic Dome hides queued monster intents. Existing live reconstruction records public executions and pre-roll state for stable original monsters. A split or summon creates a new object partway through combat, sometimes reusing a slot. Slot-only history cannot distinguish occupants or qualify a newborn's first hidden roll. Installed LouseNormal/LouseDefensive and Darkling constructors choose a damage scalar once and retain it across attacks; intent sampling alone cannot represent that uncertainty.

## Decision

Identify a native slot occupant by combat identity and monotonically increasing occupant generation. Register source-qualified births before initialization's first hidden roll and expose the completed birth with canonical slot and local execution timeline. Reset old occupant knowledge when the slot changes. Keep same-object revival separate from replacement.

Represent persistent hidden damage as a finite public candidate mask over the installed constructor prior. Narrow the mask using public hit outcomes, retaining all compatible values under mitigation, blocking and censored HP loss. Materialize one private value per simulated world and retain it through successive attacks and same-object revival. Public wire, information hashes, knowledge events and model observations retain the mask and redact the sample.

## Alternatives considered

- Keep slot-only histories: replacement can inherit the previous occupant's pending move or Spot Weakness predicates.
- Capture private queued moves or constructor damage: leaks hidden information under Runic Dome.
- Use a mean damage value or resample each attack: changes the persistent parameter's mechanics and correlations.
- Infer a unique damage scalar from every HP loss: mitigation and overkill can make multiple candidates observationally equivalent.

## Affected files and evidence

- `Monster.h`, `Monster.cpp`, `MonsterSpecific.cpp` and `MonsterGroup.cpp` define occupant generations, source-qualified births and persistent damage.
- `CombatKnowledge.cpp`, `CombatObservation.cpp`, `SearchStateHash.cpp` and `SilverSearcher.cpp` preserve public identity and beliefs while redacting private samples.
- `PublicDamageBelief.h`, `PublicLatentDamageCapture.java` and its damage patch replay public hit outcomes at the immediate damage boundary; Buffer reduction is a later queued action.
- `RunicDomeCapture.java`, `RunicDomeTracker.java` and `live_silver_importer.cpp` validate canonical slots, local timelines and ordered public damage history.
- `BattleContextBinary.h` writes version 4 snapshots with generation and damage belief fields.
- Reproducible fixtures: `persistent_latent_damage`, `runic_dome_lifecycle`, `live_silver_importer_test`, `RunicDomeTrackerTest` and `PublicLatentDamageCaptureTest`. The focused native suite (28 checks), Java suite (21 test classes), affected Debug targets and Release advisor build pass. Independent implementation review found no unresolved findings after corrections.

## Consequences

The supported public information state now includes lifecycle identity and persistent-damage uncertainty. No-Dome public roots canonicalize the irrelevant damage belief to zero and retain the concrete scalar; raw simulator snapshots may retain internal bookkeeping. Capture rejects unqualified birth sources, missing timeline/provenance and impossible masks. This decision establishes representation correctness; it does not establish gameplay-quality improvement.
