# ADR-0015: Rebase the immediate live Silver root for equivalent card copies

- Status: superseded by [ADR-0022](0022-remove-vendored-silver.md)
- Date: 2026-09-19

## Context

Silver deduplicates gameplay-equivalent cards while enumerating root actions,
so each retained action names one physical card representative. The live panel
intentionally recommends only the card kind, not that hidden representative.
When a human played another equivalent copy, the resulting gameplay state was
supported but its card UIDs and hand order did not exactly match the retained
successor. The session therefore discarded useful visits through the safe
`candidate_missing` fallback.

Globally ignoring card UIDs is not safe: retained decision and chance nodes
use exact physical identity as part of search-state and continuation identity.
The rejected global alternative also changes transposition semantics far
beyond this live input ambiguity.

## Decision

Match the immediate observed live root against every explored action edge at
the retained root, not only Silver's selected recommendation. Permit
equivalent-copy reuse only at that boundary after an ordinary card action.
The retained and observed actions must be gameplay-equivalent and differ only
in physical UID. Swap exactly those two
UIDs throughout the reachable retained subtree, align the candidate root hand
and card-edge source indices with the observation, and retain it only when the
normal full search-state equality check succeeds. Compact the graph around the
accepted candidate before continuing search.

Keep `equalForSearch()`, global dedup keys, ordinary action equivalence, and
chance-node identity unchanged. Refuse the narrow remap for queued intermediate
states or any additional card-state mismatch; those cases use the existing
fresh `candidate_missing` fallback.

## Alternatives and consequences

Always falling back is correct but makes visit reuse depend on an invisible
physical representative that the human cannot intentionally select. Globally
relaxing UID identity could reuse more states, but would merge identities in
unrelated decision and chance paths and is outside this live-boundary fix.

The chosen scope preserves visits for equivalent starter-card copies while
retaining the strict global identity model. It adds a bounded subtree rewrite
and compaction on this reroot path. Any proof failure remains fail-closed and
starts a fresh root.

## Evidence and affected files

- `third_party/silver_lightspeed/bridge/SilverStateBridge.cpp`: immediate
  candidate proof, reachable UID remap, root alignment, and compaction.
- `include/sim/search/SilverBridge.h` and
  `apps/one_combat/advisor_stdio.cpp`: explicit equivalent-copy reroot
  diagnostic.
- `apps/live_silver_importer_test.cpp`: non-selected action and equivalent-copy
  inherited-visit cases, strict global-state inequality, and changed-card-state
  fallback case.
- `mods/sts-model-inspector/src/main/java/stsmodelinspector/STSModelInspector.java`:
  distinguishes equivalent-copy reuse from fallback in the live panel.
