# Silver retained-search queue-item audit evidence packet

This packet makes the bounded PR #274 audit independently reviewable without
rerunning a broad experiment or changing production search behavior.

## Frozen provenance

- Audit/source baseline: `43ef6a6df2ea9af56840c9a298c92623c14bcff6`
- Audit worktree: `/home/philippherrmann/.codex/worktrees/silver-retained-search-audit/sts_lightspeed`
- Original capture path:
  `/home/philippherrmann/.codex/visualizations/2026/09/21/01a0c2f7-9750-79e1-bb64-5eba6649b52d/live-small-slimes-silver-tree-fixed.json`
- Capture SHA-256:
  `e20001e051e65e723c8cdf51e73890bc3df971454aa3713854acb2d9980ad22d`
- Live session: `78c0ee4f9f67`
- Sequence: `9`
- Observation hash: `efb8bcf0367f908221521ab79f09c5f666ee5a6cf3d6e0b047b41f95558c84d8`
- Replay provenance: PR #272 head `f97f4015cb036fe2c46d049c6ea00e44e8be19af`

The compressed capture committed in this directory is the source graph used by
the opportunity script. Its contents are unchanged from the supplied JSON;
compression is only for repository size. The script also verifies the
uncompressed capture SHA-256.

## Opportunity reproduction

Run:

```bash
python3 docs/experiments/evidence/silver_retained_search_audit_20260921/analyze_silver_retained_search_audit.py \
  docs/experiments/evidence/silver_retained_search_audit_20260921/live-small-slimes-silver-tree-fixed.json.gz
```

Expected summary fields:

```text
total_nodes=1133
state_nodes=997
chance_nodes=136
player_normal_unresolved=974
distinct_non_queue_keys=942
candidate_groups=49
candidate_groups_with_distinct_queue_items=49
candidate_groups_with_matching_state_hash=49
candidate_nodes=104
excess_nodes=55
unordered_pairs=61
candidate_pairs=43
candidate_triples=6
candidate_edges=124
queue_variant_group_sizes={2:43,3:6}
state_fraction=0.055165496489468405
total_fraction=0.04854368932038835
```

The committed `opportunity_summary.json` is the same output in structured form.
The screen intentionally remains Wire-level: fields absent from the capture are
not inferred as native equality. Every candidate group is additionally checked
to contain at least two distinct serialized queue items, and all 49 candidate
groups report matching retained node hashes. The packet intentionally does not
claim the earlier partial END_TURN count; full stochastic distribution identity
remains a future proof obligation.

`MANIFEST.sha256` hashes the script, compressed capture, derived summary, probe
patches, captured outputs, and this README.

## Native probe reproduction

The two patch files preserve the exact temporary test-only changes that produced
the recorded outputs:

- `queue_item_seed_pair_probe.patch`: 32 paired common seeds, 32 steps per arm.
- `queue_item_fixed_root_probe.patch`: one fixed native fixture, 128 steps per
  arm, plus the Attack Potion selection-boundary observation.

Apply one patch at a time to the clean audit-baseline source checkout, build the
existing test target, and run through the repository guard:

```bash
git apply docs/experiments/evidence/silver_retained_search_audit_20260921/queue_item_seed_pair_probe.patch
cmake --build /tmp/silver-retained-search-audit-build --target silver-search-optimization-test -j2
bash tools/seed_guard.sh /tmp/silver-retained-search-audit-build/silver_search_optimization_test
git apply -R docs/experiments/evidence/silver_retained_search_audit_20260921/queue_item_seed_pair_probe.patch
```

The exact root construction, seed formula, configuration boundary, and captured
output are in `queue_item_seed_pair_probe_output.txt` and
`queue_item_fixed_root_probe_output.txt`. The fixed-root output is:

```text
queue_item_root_audit steps=128 best_action_parity=PASS potion_card_select_queue_difference=OBSERVED
silver_search_optimization PASS
```

The seed-pair output is:

```text
queue_item_seed_pair_audit seeds=32 steps=32 result=PASS
silver_search_optimization PASS
```

The probe is a native simulator fixture check, not live gameplay or a fair-play
benchmark. Both arms use the same native RNG initialization; only the queue
item differs. The guard and 32-seed count are retained to make the local ceiling
explicit.

## Interpretation correction

The Attack Potion observation is not a demonstrated downstream semantic
divergence. It proves only that a differing queue item survives into
`CARD_SELECT`, a boundary not covered by the settled-player equivalence probe.
The defensible conclusion is therefore:

> Global canonicalization remains unqualified because the stale value survives
> into states outside the tested equivalence boundary.

The result does not claim that the queue item itself changes discovery legal
actions, selected-card successors, evaluation, RNG, or eventual behavior. Those
remain proof obligations for any future implementation.

## Focused checks

The audit-baseline focused CTest selection passed 3/3:

```text
silver_searcher_link_closure PASS
silver_search_optimization PASS
silver_bridge_boundary PASS
```

No source-level production change was made. The durable conclusion remains
`NARROW_QUEUE_CANONICALIZATION_PLAUSIBLE_BUT_UNQUALIFIED`.
