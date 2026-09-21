# Silver retained-search queue-item audit — 2026-09-21

**Status:** open; bounded audit complete, implementation not authorized

**Last verified:** 2026-09-21 against audit baseline

**Classification:** `NARROW_QUEUE_CANONICALIZATION_PLAUSIBLE_BUT_UNQUALIFIED`

## Baseline and scope

The audit baseline was `origin/main` at
`43ef6a6df2ea9af56840c9a298c92623c14bcff6`, inspected in the separate
Codex-managed worktree
`/home/philippherrmann/.codex/worktrees/silver-retained-search-audit/sts_lightspeed`.
The pinned submodules were `json=2222d386c905e6a6ebf73c61571a8a2cf196e843`
and `pybind11=63d627c5747befad7720a43ebbe5614fd5d83247`; worktree validation
passed.

This is an investigation only. It does not relax `BattleContext::equalForSearch`,
change Silver search behavior, change the reuse cap, update PR #272, or promote
a default.

The motivating capture is
`/home/philippherrmann/.codex/visualizations/2026/09/21/01a0c2f7-9750-79e1-bb64-5eba6649b52d/live-small-slimes-silver-tree-fixed.json`
(SHA-256
`e20001e051e65e723c8cdf51e73890bc3df971454aa3713854acb2d9980ad22d`). It is
from live session `78c0ee4f9f67`, sequence `9`, observation hash
`efb8bcf0367f908221521ab79f09c5f666ee5a6cf3d6e0b047b41f95558c84d8`, and was
replayed offline on PR #272 head `f97f4015cb036fe2c46d049c6ea00e44e8be19af`.
PR #272 is used only as capture provenance and motivation; all source facts
below were revalidated at the audit baseline.

## Symptom and scope

The corrected graph retains separate nodes for #9 and #21 even though their
projected native fields match except for `curCardQueueItem` and their reported
hash is equal. The scope is to quantify that fragmentation and test whether
queue-item-only canonicalization is safe at settled player decisions. It does
not include production implementation, a full-combat reconstruction, a broad
seed sweep, a new default, or a PR #272 update.

## Question and decision rule

The question was whether Silver can merge substantially more retained states by
ignoring only `curCardQueueItem` when a state has settled at a player decision.

The candidate passes only if native evidence supports all of the following:

1. the legal action surface is unchanged;
2. deterministic successors are unchanged;
3. stochastic outcome distributions and RNG/information boundaries remain valid;
4. evaluation inputs remain equivalent;
5. reroot identity and retained statistics remain safe; and
6. the measured work reduction does not trade away decision quality.

The supplied graph can measure opportunity, but it cannot prove the complete
native state because its Wire projection does not retain every `BattleContext`
field. Its counts are therefore an upper-bound screen, not a merge authorization.

## Opportunity in the corrected Small Slimes graph

The tree has 1,133 retained nodes: 997 decision/state nodes and 136 chance
nodes. It contains 974 unresolved `PLAYER_NORMAL` states and 23
`EXECUTING_ACTIONS`/terminal state nodes.

Grouping state projections by every serialized field except `curCardQueueItem`
produced:

| Quantity | Count |
| --- | ---: |
| Distinct non-queue state keys | 942 |
| Duplicate candidate groups | 49 |
| Nodes in candidate groups | 104 |
| Excess nodes if every group merged | 55 |
| Unordered candidate pairs | 61 |
| Candidate groups that are pairs/triples | 43 / 6 |

The 55 excess nodes are 5.52% of decision/state nodes and 4.85% of all
retained nodes. The duplicate-member nodes own 124 of 2,131 outgoing edges
(5.8%), but this is not a runtime saving estimate: sharing nodes also pools
visits, values, expansion order, and reroot identity.

All 104 candidates are unresolved, settled `PLAYER_NORMAL` nodes. No candidate
group includes a chance, selection, pending-action, or terminal node. The
capture therefore shows a real opportunity in one representative root, but not
a whole-run or cross-root rate.

The supplied #9/#21 pair is one of these candidates. Its projected state is
equal except for `curCardQueueItem`, and both nodes report the same hash, but
the nodes remain distinct because the hash is only a candidate bucket and exact
matching includes the queue item.

## Native state and field classification

The audit rechecked
`third_party/silver_lightspeed/src/combat/BattleContext.cpp` and
`third_party/silver_lightspeed/src/sim/search/BattleSearcher.cpp` at the audit
SHA.

`equalForSearch` compares turn/outcome/input and card-selection state, monster
turn state, terminal and turn flags, action/card queues, potions, player and
monster state, card-manager state, `curCardQueueItem`, and semantic misc bits.
It intentionally excludes RNG/debug fields such as `rng`, `loopCount`, and
`sum`.

`hashBattleState` omits `curCardQueueItem`, `energyWasted`, `cardsDrawn`, and
other exact-state fields. `getOrCreateNode` resolves same-hash candidates with
full `equalForSearch`; equal hashes are not semantic equality.

The relevant classes of differences are:

| Class | Examples | Audit treatment |
| --- | --- | --- |
| Gameplay-relevant | HP, block, energy, statuses, piles, potions, card selection, action/card queues | Must remain exact. |
| Identity/UID | Card UIDs, special data, queued card identity, purge/exhaust metadata | Must remain exact unless a separate semantic canonicalization proves otherwise. |
| Evaluation-only/omitted | `energyWasted`, `cardsDrawn`, and other counters | Existing proof obligation; equal hash/equality is not a complete evaluator-input proof. |
| Potentially stale bookkeeping | `curCardQueueItem` after queues drain at `PLAYER_NORMAL` | Candidate only at a narrow boundary. |

`executeActions` drains action and card queues before setting `PLAYER_NORMAL`,
and `playCardQueueItem` overwrites `curCardQueueItem` when the next card is
processed. This supports the stale-bookkeeping hypothesis. It does not make
the field globally irrelevant: delayed actions and card effects read or capture
it while work is pending. `_DiscardNoTriggerCard` explicitly captures the card
because later card-queue dequeues can overwrite the mutable queue item.

## Native paired checks

A temporary test-only probe was added, run, and removed from the clean audit
checkout. It compared two actual native roots that differed only in the queue
item, using 32 paired common seeds and 32 search steps per arm. The run was
through `tools/seed_guard.sh` and stayed below the local 128-seed ceiling.

Observed result:

```text
queue_item_seed_pair_audit seeds=32 steps=32 result=PASS
silver_search_optimization PASS
```

**Expected:** paired roots differing only in stale queue-item bookkeeping should
have identical immediate action surfaces, deterministic successors, and tested
root statistics at a settled `PLAYER_NORMAL` boundary. A selection-producing
continuation should remain an explicit boundary rather than being treated as a
globally equivalent state.

**Observed:** the 32-seed/32-step native screen and the separate 128-step
fixed-root screen met the first condition. The Attack Potion screen met the
second condition by preserving different queue items at `CARD_SELECT`.

Across the 1,024 paired search steps, the probe found no difference in:

- best action;
- root legal-action count;
- root action identities or visit counts; or
- deterministic successor state after normalizing only `curCardQueueItem`.

A separate 128-step fixed-root probe also passed direct search-statistics
comparisons. This supports a narrow statement only: in the tested native
fixtures, a settled `PLAYER_NORMAL` root with empty queues behaved equivalently
for immediate actions, deterministic successors, and short-horizon root
statistics after ignoring only the stale queue item.

The probe also exercised an Attack Potion. Both roots reached `CARD_SELECT`,
but retained different queue items:

```text
potion_card_select_queue_difference=OBSERVED
```

This is a concrete boundary counterexample to global canonicalization. Attack,
Skill, Power, and Colorless Potions enter discovery selection; Gamble, Liquid
Memories, and Stance Potion also create selection boundaries. Entropic Brew and
Distilled Chaos introduce stochastic or queued-card behavior.

The saved graph supplied a limited stochastic screen: 22 candidate groups had
both END_TURN chance parents expanded, and 310 common sampled outcome indices
had identical child projections after omitting the queue item. Unequal sample
coverage and chance-parent statistics mean this is not a proof of equal full
distributions.

## Unsafe boundaries and proof obligations

The following are not qualified for queue-item merging:

- `EXECUTING_ACTIONS` or any non-empty action/card queue;
- card selection or other selection states;
- potion paths that enter selection or stochastic generation;
- delayed effects, autoplay, exhaust ordering, and queued-card exclusions;
- chance parents or chance outcomes without a full distribution and RNG proof;
- terminal states, unless a separate terminal identity contract is established;
- global reroot and transposition identity.

The existing same-turn audit also confirms that `energyWasted` and `cardsDrawn`
can affect evaluation while being omitted from hash/equality. That is an
existing limitation and must not be hidden by treating a queue-only projection
match as complete evaluator equivalence.

## Hypotheses and eliminated hypotheses

- **Inference — narrow stale-item hypothesis:** after `executeActions` has
  drained both queues and the state is settled at `PLAYER_NORMAL`, the prior
  queue item is not needed to enumerate or execute the next ordinary action.
  The paired native screen supports this for the tested fixtures only.
- **Inference — global queue-item irrelevance:** `curCardQueueItem` can be
  ignored for all retained states. The Attack Potion to `CARD_SELECT`
  counterexample eliminates this hypothesis.
- **Eliminated explanation — hash collision:** the #9/#21 relationship is not
  merely a hash collision; the current source uses exact `equalForSearch` after
  the hash bucket, and the exact comparison rejects the queue-only pair.
- **Unresolved — full stochastic/reroot equivalence:** common sampled END_TURN
  outcomes matched, but full distributions, reroot identity, and pooled search
  statistics were not qualified.

Prior evidence remains constraining:

- Ledger §263–264 retained the 32,768 production cap; 131,072 remained
  experimental without quality qualification.
- Ledger §318 accepted only a bounded GAMBLE multiplicity canonicalization.
- Ledger §320 rejected stochastic UID/chance merging: traces differed in
  53/64 cases, timing increased by 0.82%, and exact reroot/fallback behavior
  worsened.
- Ledger §320 explicitly records that queue-item inequality alone is not a
  semantic obstruction, but that this observation is not a general equality
  proof.

## Recommendation and smallest future change

Do not relax `equalForSearch` or change Silver search behavior from this audit.

If separately authorized, the smallest reviewable implementation would be a
boundary-local lookup canonicalization that applies only when:

- input is settled `PLAYER_NORMAL`;
- both action and card queues are empty;
- outcome is `UNDECIDED`; and
- no selection state is pending.

The canonicalized item must not be allowed to cross selection, pending-action,
terminal, chance-parent, or reroot boundaries. The actual observed state should
still be used to execute the next action.

Before implementation could be accepted, a frozen baseline/treatment benchmark
would need common seeds, identical model/configuration/budget, and roots
covering ordinary cards, delayed effects, autoplay, exhaust, potions,
selection, and END_TURN stochasticity. The predeclared gate should require zero
legal-action or deterministic-successor mismatches, bit-exact evaluation inputs,
no reroot-identity/fallback regression, no unexplained action-trace divergence,
and a measured node/memory/runtime benefit before any quality screen or default
discussion.

## Current blocker and next check

The blocker is missing proof for stochastic distribution identity, evaluation
inputs, and reroot/statistics preservation under a shared retained node. The
next check, if implementation is separately authorized, is a frozen
baseline/treatment benchmark over the boundary roots listed above with paired
common seeds and a predeclared zero-mismatch semantic gate. No expensive sweep
or production change is part of this investigation.

## Relevant code

- `third_party/silver_lightspeed/src/sim/search/BattleSearcher.cpp` — hash
  bucket lookup, exact dedup resolution, and end-state evaluation.
- `third_party/silver_lightspeed/src/combat/BattleContext.cpp` — queue
  draining, queue-item overwrite, potion behavior, and `equalForSearch`.
- `third_party/silver_lightspeed/src/combat/Actions.cpp` — deferred card
  identity, discovery/card selection, and queue-item-dependent effects.
- `docs/knowledge-base/architecture/combat-search.md` — retained-state,
  dedup, and reroot invariants.
- `docs/experiments/ledger-06.md` — §§263–264, 318, and 320 prior evidence.

**Knowledge impact:** durable unresolved Silver search investigation and
experiment evidence only; no production Silver behavior, model, RNG, schema,
budget, gameplay default, or PR #272 changed.

## Reproduction and checks

The focused audit build used the exact audit checkout in
`/tmp/silver-retained-search-audit-build`:

```bash
cmake -S . -B /tmp/silver-retained-search-audit-build \
  -G 'Unix Makefiles' -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_COMPILER=g++
cmake --build /tmp/silver-retained-search-audit-build \
  --target silver-search-optimization-test silver-native-test silver-bridge-test -j2
ctest --test-dir /tmp/silver-retained-search-audit-build --output-on-failure \
  -R '^(silver_search_optimization|silver_bridge_boundary|silver_searcher_link_closure)$'
```

The final clean checkout passed all three focused tests. The temporary paired
probe was removed before the audit checkout was finalized; no production source
diff remains.
