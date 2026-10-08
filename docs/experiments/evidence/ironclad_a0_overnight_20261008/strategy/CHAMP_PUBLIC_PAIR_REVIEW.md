# Independent review of the public D13 Champ pair probe

Implementation source review: **PASS for the bounded diagnostic, pending the coordinator's build, contract check and two-future runtime gate.** Scientific scope review: **PASS for one fixed public state's conditional combat contrast; this does not estimate production-controller or Act-3 improvement.** The reviewer did not edit the probe, build it or execute a game/continuation.

## Reviewed identities

| Artifact | SHA256 |
|---|---|
| Final `apps/silver_public_pair_probe.cpp`, including health diagnostics | `e78ac9e5d229f48f2e28429855eafaa9e158589b359ad50369d3c10536ffda9a` |
| `audit/champ_d13_probe_specification.json` | `8d562f08f61bec9ce12f1a303a33376f532fab7cafd32ac75d6245aefd90fbb5` |
| `audit/champ_d13_public_root.json` | `4ddbdefc045d4e7467fa448bcec48c235ae6c10716796df10a99b695bd7e6e93` |
| Original `Capture_0.public.jsonl` | `0a679ddf01a75eae8186a7c68eda9d6b808decb42c6c2c0457b4c2fc980a4f83` |

The extracted row exactly equals line 13 of the hash-verified original capture, located by seed 610081002, floor 33 and decision 13. Its recorded producer is source `3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0`. The probe source and specification were stable when reviewed.

## Implementation findings

The environment hydrates only the captured public wire. Its future streams are derived from the fixed domain, frozen row hash and future index, with no historical simulator RNG or source seed used as the environment seed. Both forced actions start from copies of that same sampled environment. The abstract CardPile defers unknown draws to the environment RNG while retaining known top/bottom positions. This is a public conditional environment sampler, not a replay of the original hidden world.

Every continuation planner receives a newly exported and hydrated public root with `isolatedSearchSeed=0`. Hydration resets both the root's `seed` field and all six combat RNG streams. This matters because `SilverSearcher::reseedRollouts` also seeds its rollout engine from `rootState->seed + floorNum`. Neither environment seed nor RNG state enters planning. Source immutability is checked after planning and after each branch.

Semantic resolution binds the forced alternative to the unupgraded Shrug It Off instance with uniqueId 14 and its complete card attributes, rather than a positional hand index or an arbitrary equivalent copy. The baseline is the captured END action. Planning uses a fresh SilverSearcher at each decision, fixed Act-2 boss context and its default evaluation weights. Both `profile.completed` and root visits must equal 10,000. There is no retained tree, learned stopping, adaptive budget or model loading in this executable.

Public export/hydration equality checks all fields supported by the wire at every root, including known draw regions, current card context and exact supported selector queue tails. Normal roots must have empty queues. Unsupported selection tails or hidden intents fail the branch. The original stale Discovery selector record and Bash queue item are ordinary historical fields at a PLAYER_NORMAL root; hydration does not replay them there. The omitted Discovery debug flags do not control this continuation policy. Smoke Bomb cannot escape this boss encounter. These observations are specific to this supported Champ case, not a proof that arbitrary public wires can reproduce every simulator state.

The 1,000-decision cap, non-death engine stops, semantic failures and unsupported states are invalid results, not losses. Both sibling result rows are attempted and their validity is retained. The executable records action fingerprints, endpoint hashes, actual continuation simulations and CPU/wall time. Runtime execution remains necessary to establish that the complete sampled trajectories stay within the supported wire boundary.

The final health-diagnostic delta was independently reviewed after the initial `b296388cedac0b01accf720103a8ba4194ee0d18ee7bb6faf2086a096a259e13` implementation. It aggregates each completed search simulation's endpoint category and records the actual completed denominator. Any turn-limit, engine-stop or nonterminal search endpoint invalidates the branch before the chosen action executes. The actual world must also remain within the existing 500-turn and 1,000,000-loop limits with nonnegative live-monster count. The delta adds reporting and stricter validity gates; it does not change a valid branch's policy, search budget, state or RNG. Source review **PASS** carries to the final `e78ac9e5d229f48f2e28429855eafaa9e158589b359ad50369d3c10536ffda9a` helper and unchanged root/specification hashes.

## Scientific and launch boundaries

The two contract/cost futures are k 0,1. The fresh evaluation block is fixed at k 2..63. The controller and END/Shrug alternatives must remain frozen after the contract gate; cost or support failures stop the lane rather than justify a new favorable allocation. Report every allocated pair and any invalid branch. The source was selected after an observed loss and the historical action was known, so this is a diagnosis of one public state, not a population-strength test.

Any contrast estimates the conditional combat outcome under this fresh exact 10,000 controller. It cannot identify the effect under the original retained-tree learned-stop controller, nor isolate which later decisions explain the original loss. Common future seeds couple the two arms but do not force equal realized draw sequences after actions consume randomness differently.

The executable records the supplied producer source SHA and hashes its running binary, specification and extracted row. It does not itself prove that the source SHA produced that binary or rehash the original capture named in the specification. The coordinator's immutable launcher/freeze must enforce those source, binary, specification and capture identities before the contract check, canary and evaluation. Aggregate process capacity and seed-guard execution remain coordinator responsibilities.

Knowledge impact: experimental review evidence only. No gameplay default, production controller, model or maintained engine invariant is changed by this review.
