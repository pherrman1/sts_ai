# Frozen public Champ D13 conditional combat probe

Status: source/specification frozen for independent review; binary/source launch custody and measured canary gates remain coordinator-owned. No probe search or full continuation was executed during preparation.

## Question, fixed contrast and scope

At discovery source610081002, Act2 floor33 Champ, zero-based turn1 decision13, the recorded policy ended with HP75, block3 and energy1 facing visible weak Face Slap, while unupgraded Shrug It Off#14 was legal. The experiment compares forcing that exact END with forcing that exact Shrug. It does not select another alternative after outcomes. The initial action and root were frozen before conditional outcomes. The root is public, with unknown draw-order contents and legitimately known top/bottom; no private historical GameContext or RNG state is loaded.

The endpoint is actual combat victory in the sampled continuation, with HP, potions, turn count and CPU as diagnostics. This is one outcome-informed source decision under a new fixed continuation policy. It cannot establish population policy strength, an Act3 win-rate gain, or what the original retained learned-stop search would have done with a larger budget.

| Frozen artifact | SHA256 |
|---|---|
| Full public capture | `0a679ddf01a75eae8186a7c68eda9d6b808decb42c6c2c0457b4c2fc980a4f83` |
| `champ_d13_public_root.json` | `4ddbdefc045d4e7467fa448bcec48c235ae6c10716796df10a99b695bd7e6e93` |
| `champ_d13_probe_specification.json` | `8d562f08f61bec9ce12f1a303a33376f532fab7cafd32ac75d6245aefd90fbb5` |
| Initial helper source, `apps/silver_public_pair_probe.cpp` | `b296388cedac0b01accf720103a8ba4194ee0d18ee7bb6faf2086a096a259e13` |

END fingerprint: `sa/t=5/s=0/c=0_0_0_0_0_0_0_0/o=0/p=0_-1/x=-1/d=0/k=0/task=0/sel=`.

Shrug fingerprint: `sa/t=1/s=1/c=301_14_0_1_1_0_0_0/o=0/p=0_-1/x=-1/d=0/k=0/task=0/sel=`.

The captured source was3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0. The new helper's source SHA, executable hash and reviewed CMake diff must be frozen separately before expensive continuations. Every invocation emits its executable hash, explicitly supplied producer SHA, spec/root hashes, stage, budget and context. The coordinator's receipt must bind the command, clean environment, exit code, timing and every output; refuse existing output prefixes and retain failures.

## Sampling and continuation policy

For pair index k, derive the environment seed from the first16 hexadecimal digits of SHA256 of `champ-d13-public-pair-v1-environment:<root-file-sha256>:<k>`. Both forced actions start from separate copies of the exact same hydrated public root and environment RNG streams. CardPile's existing information-set operations sample unknown cards on demand, preserve observed known top/bottom facts and clear order knowledge on shuffles. Intervention-dependent RNG consumption may diverge; this coupling does not assert identical semantic random events after different action histories.

Every subsequent decision exports only the simulated world's public information-set wire, replaces isolatedSearchSeed with0, hydrates a separate search root, and starts a **fresh SilverSearcher with exactly10000 new simulations**. No model loads, learned stopping, inherited tree or adaptive budget is used. This simpler common continuation is deliberate: the original retained search graph is not captured. The world seed and all six environment RNG streams never enter the planner; the wire loader sets both planner.seed and planner RNG streams from0. State and RNG equality checks prove planning does not mutate the world.

Evaluation context comes from the wire through existing searchContextFromWire and must report act2, boss room true, finalBossBinary false. It therefore uses the existing Act2-boss terminal evaluation including act-transition healing. It does not silently use an Act1/default context. The measured outcome is actual combat victory, separately from that search objective.

Fail-closed checks cover the initial captured-wire hydration (only observer-generation metadata normalized to0), entire export/hydration wire equality at every decision, abstract draw lifecycle, visible-intent scope, supported exact pending card/action queues at selections, no pending queues at normal decisions, semantic action identity and legality, untouched paired source copies, and exactly10000 completed simulations at every fresh continuation root. Unknown queues or a nonterminal1000-decision cap are errors, never losses or rows to discard. A non-death loss/engine stop is invalid. Every attempted branch emits validity and error information; one invalid branch blocks a clean comparison.

## Stages and fixed work limit

1. `SPEC check`: four one-step transitions, repeating each forced action twice from the same k0 public world. Require exact state and RNG repeat parity, unchanged original paired root, environment0-versus1 planner-view equality, exact public-wire hydration, END's immediate6HP loss and Shrug's immediate8block/draw. No search or full continuation occurs in this check. Invoke through the seed guard because it executes simulated actions.
2. `SPEC canary 0` and `SPEC canary 1`: exactly two paired futures/four full branches. Inspect contract validity, unsupported-boundary errors and CPU/wall cost. Continuation is permitted solely on contract validity and measured affordability within campaign time/resource reserve, not on outcome signs. Canary outcomes do not select actions or count toward the evaluation contrast.
3. If those gates pass and the coordinator records the cost decision, `SPEC evaluation K` for each K=2..63 once: exactly62 new paired futures/124 branches. The helper rejects other stage/index combinations. There is no retry, replacement, extension or budget change for a close result. At most64 distinct paired futures and128 full continuations total, plus four one-step check transitions. All game-driving commands use tools/seed_guard.sh.

The coordinator limits this lane's concurrent processes according to remaining shared capacity, never above6 campaign-wide, and sets one OMP/BLAS thread per process. The launcher must impose a reviewed per-pair wall timeout and preserve incomplete output. A new affordability decision is mandatory before evaluation; the protected final confirmation reserve takes precedence. No final confirmation seed or historical TEST file is used.

## Analysis and interpretation

Before evaluation output opening, freeze an analyzer that accounts for all62 allocated pair indices, exact common provenance, complete2arm pairing, valid endpoints, unchanged10000 budget and source/spec/capture identity. Report each arm's combat wins, both-win/both-loss and each discordant direction; use the paired binary difference and a descriptive paired bootstrap95% interval with10000 resamples and RNG20261008. Report all canary and failed/absent cases separately. A positive conditional interval supports the fixed action only under this public-future sampler and fresh exact continuation, not a deployment claim. An inconclusive result stays inconclusive; do not search other D13 alternatives or extend this cohort.

A known immediate benefit is not full-trajectory dominance: Shrug prevents the immediate6HP loss, but advances a card draw, changes future hands, preserves Blood for Blood's higher cost and avoids Self-Forming Clay's next-turn block trigger. This is why a paired continuation is needed.

Knowledge impact: bounded diagnostic evidence and a standalone helper. No production backend, model, gameplay default or general combat policy is changed.

Independent source review by strategy: PASS at helper SHA `b296388cedac0b01accf720103a8ba4194ee0d18ee7bb6faf2086a096a259e13`. Custody boundary: the helper verifies the extracted root hash and semantic contract but does not itself rehash the parent capture file or prove that the environment-supplied source SHA produced the binary. The coordinator launcher must verify capture_path/capture_sha256/capture_source_sha and bind reviewed source, immutable executable and specification hashes before every stage. Wire parity proves the supported public wire fields, not unmodeled engine internals; debug Discovery flags do not control this helper, and Smoke Bomb state is irrelevant to this boss root.

Pre-execution health receipt refinement: final helper SHA `e78ac9e5d229f48f2e28429855eafaa9e158589b359ad50369d3c10536ffda9a`. Each branch now records aggregate search endpoint counts for victory, death, turn_limit, engine_stop and nonterminal, along with actual completed-simulation denominator. Any of the last three categories invalidates the branch; it is not silently scored as a loss. Actual-world turn500/loop1M/nonnegative-monster health guards are checked too. This strengthens validity reporting without changing search policy, budget, state or RNG.

## Reviewed invocation tooling handoff

The coordinator built source `a557ace5770f26983db4a55ec2c9318a95bf328d` to immutable executable SHA `f316bbbb27d86f2628889607c7e7069a26d53f81c2ffef9e436ea1a355a66fbf`. Its unchanged build freeze is `champ_d13_build_freeze.json`, SHA `8edcc9126e9049b92f574bfce2eccebf2f54a7fe45125dfcbf4e351c6566f259`. It narrows the lane to one game process and600seconds per pair. The four one-step check has60seconds. These timeouts are fixed before running; no automatic retry follows a timeout.

The custody runner `run_champ_probe.py` SHA `4a5239b27a8322185e72b73a69b6a535156e3fb119d5a6b99874d48cd12f6158` and analyzer `analyze_champ_probe.py` SHA `817985e65b649fe4d6de431ca2cf2d5fdcf09781d6bd9f97f496e0c69e01e4f4` are bound in `champ_d13_tools_freeze.json` SHA `ad32cc58f79d97b45c1e8e9c7270f3ebff4f3fe619d971cc430650a4067b0b49`, together with seed guard, paired-analysis implementation and producer CMake object. Independent review remains required before simulator launch. Full custody dry verification passed without invoking a simulator. Five synthetic tests passed, covering pair completeness, future coupling, budget drift, search-health stops, and failed/no-output attempts.

Runner common arguments:

```
python3 docs/experiments/evidence/ironclad_a0_overnight_20261008/audit/run_champ_probe.py --freeze docs/experiments/evidence/ironclad_a0_overnight_20261008/audit/champ_d13_build_freeze.json --freeze-sha256 8edcc9126e9049b92f574bfce2eccebf2f54a7fe45125dfcbf4e351c6566f259 --tools docs/experiments/evidence/ironclad_a0_overnight_20261008/audit/champ_d13_tools_freeze.json --tools-sha256 ad32cc58f79d97b45c1e8e9c7270f3ebff4f3fe619d971cc430650a4067b0b49 --stage check
```

For the two cost canaries, replace only `--stage check` with `--stage canary --k 0` or1. The runner invokes the seed guard internally. Output stems are fixed under `build/overnight_20261008/champ_d13/`, refuse any prior files, and use a nonblocking lane lock. Receipt, JSONL and stderr hashes are retained even on failure. The analyzer takes the same freeze/tools arguments, `--stage canary` and a fresh `--out`; it validates all allocated files before returning cost/contract statistics and emits no win summary.

Evaluation requires a separate hashed coordinator authorization with schema `champ_d13_evaluation_authorization_v1`, both build/tools freeze hashes, canary report path/hash, `canary_contract_pass:true`, `cost_fits_reserve:true`, criterion `contract_and_cost_only`, approved_epoch after the canaries, and evaluation_k exactly2..63. The runner validates that report and all its raw hashes on every invocation. Run each authorized index once with `--stage evaluation --k K --authorization PATH --authorization-sha256 SHA`. The fixed analyzer checks all62 pairs, complete receipt-first inventory including failed/no-output and orphan attempts, context, action and future identity, exact new simulation denominator, all search health categories, and normal actual terminal outcome. It uses only those62 evaluation pairs for the bootstrap. A failed gate writes a new INVALID_STOP_LANE analysis record without partial win metrics.

Independent tooling review by strategy: PASS at runner `4a5239b27a8322185e72b73a69b6a535156e3fb119d5a6b99874d48cd12f6158`, analyzer `817985e65b649fe4d6de431ca2cf2d5fdcf09781d6bd9f97f496e0c69e01e4f4` and tools freeze `ad32cc58f79d97b45c1e8e9c7270f3ebff4f3fe619d971cc430650a4067b0b49`. The reviewer independently rehashed binary, committed helper/CMake and bound tools, and found no blocker in lock, overwrite, stage gates, paired allocation, budgets, health validation, failed/orphan coverage or62-pair bootstrap. Frozen tools bytes remain unchanged; their initial pending-status field is historical. Check and two canaries are ready for coordinator execution; evaluation still requires measured affordability authorization.
