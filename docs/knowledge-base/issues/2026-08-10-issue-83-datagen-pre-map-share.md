# Issue 83: Datagen `pre` snapshot shares map with live run

- **Status:** closed (2026-08-10)
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `apps/one_combat.cpp:8093, 8614`

## Symptom

`runStrategicGenSeed` (8093) and `runStrategicGenSeed2` (8614) take `pre`
snapshots that share the map pointer with the live run. The live policy's
`transitionToAct` overwrites `*map` in place while `pre` still holds the
pointer. Impact is bounded by `forwardMapFeatures` early-return at y==15,
but the exact hazard class the decision log claims to have closed remains
open in the reverse direction.

## Evidence

- `one_combat.cpp:8093`: `pre` snapshot created without map detach.
- `one_combat.cpp:8614`: same.
- `GameContext.cpp:709`: `*map = Map::fromSeed(...)` in-place overwrite.
- Decision log `2026-08-09-strategic-datagen-shared-map-detach.md` documents
  probe→live fix, leaves live→snapshot open.

## Candidate fix directions

Add `pre.map = make_shared<Map>(*gc.map)` detach to the pre-snapshot sites.

## Relevant code

- `apps/one_combat.cpp:8093, 8614`
