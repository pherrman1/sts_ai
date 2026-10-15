# Independent initial integrity review

Reviewer: native integrity/combat specialist. Frozen source inspected:
`a4b3df35d170abba7860e8e854cc24cfd3579075`. Source inspection and model-file
parsing only; no game seeds, builds, model training, protected TEST rows, or
shared-source edits were performed by this reviewer.

## Launch verdict

The coordinator's `PLAN.md`, `profiles.json`, and `run_arm.py` were reviewed
before outcomes. **PASS for the bounded diagnostic smoke only**: smoke seed
610080000 once under Bprod with traces, once under Bflat with traces, and one
Bprod repetition without traces. This proves mode/model/instrumentation
contracts; it cannot qualify fair playing strength because the inherited
native OOC fallback consumes actual unrevealed encounters (below).

Before launch, freeze the binary SHA-256, source identity, V4/floor/win model
hashes, exact environment and the smoke-only allowed seed list. Require:

- Correct backend banner: learned stopping, no exact-root for Bprod; flat
  budget and exact-root for Bflat. Explicit argument `bestbench 10000 ...`
  alone does not enable learned stopping (`one_combat.cpp:2859`).
- V4 successful-load banner and native floor/win successful-load banner.
  An explicit V4 path failing to load silently leaves its gate disabled;
  zero process exit is insufficient.
- Bflat `STS_SILVER_TREE_PROFILE` rows have completed_simulations=10000 and
  singleton_skip=false. Exact-root mode also searches singleton roots.
- Bprod searched roots stop at the configured checkpoints; singleton roots
  may have zero steps. Compare traced/untraced run outcomes and all available
  aggregate search counts, excluding elapsed time. Record trace overhead.
- Do not use `STS_SILVER_STOP_TRACE` as a neutral observer: it searches all
  checkpoints and is incompatible with enabled learned stopping.

The runner's explicit environment allowlist, artifact hash checks, exact
seed allowlist, seed_guard wrapper, refusal to overwrite outputs, and
completion/timeout receipts are appropriate. Current permission to run this
smoke is not approval for an expensive scientific cohort or confirmation.

## Blocking information-boundary finding

**Confirmed source/model contract violation for actual public-information
play; no whole-run quality estimate yet.** `STS_FAIR=1` guarantees the native
combat search boundary, but does not sanitize native OOC fallback features.

The card-reward path is direct:

`runFullRunOocPolicyStep(gc)` (run_driver.cpp:309) →
`serverCardRewardPolicy(gc)` (ooc_policy.cpp:905) → `vQuery(gc)`
(one_combat.cpp:834) → `nativeFloorCardPick(gc)` (one_combat.cpp:971) →
`one_combat::nativeFloorCardPick(gc,...)` (ooc_native_fallback.cpp:22) →
`features(gc,path)` → `richFeatureVec(gc,path)` (run_features.cpp:132).

Shop fallback is also direct:

`runFullRunOocPolicyStep(gc)` (run_driver.cpp:313) → `shopVPolicy(gc)`
(ooc_policy.cpp:1069) → `nativeShopVPolicy(gc)` → `nativeFloorShopStep(gc)`
→ `nativeShopPlan(gc)` → the same features. No call along either route
redraws a detached hidden future. Shop removal uses the same unsanitized
features through nativeFloorRemovePick. Win-rest is disabled in the campaign
profile, but its helpers also consume the rich vector when enabled.

`richFeatureVec` reads nextEliteId and nextFight0/1/2 from the actual queue
suffix. These fields are hidden future, as the maintained ledger §371
already establishes. The loaded floor and win tree files actively split
those features; parsing their native `S` rows gives:

| Model | nextEliteId | nextFight0 | nextFight1 | nextFight2 |
| --- | ---: | ---: | ---: | ---: |
| models/v_rich_trees.txt | 2,807 | 3,574 | 3,105 | 3,042 |
| models/v_win_trees.txt | 310 | 446 | 315 | 299 |

The V4 token net omits these fields, but its margin gate can defer to these
fallbacks. Calling the whole stack project-fair does not satisfy the
charter's stricter information gate. Original Bprod/Bflat measurements must
remain diagnostic-only until this is resolved.

Minimal compatible repair proposal: average fallback candidate values over
common planner-owned encounter-suffix samples conditional only on public
encounter history. Reuse the native weak/strong/no-repeat generation rules
in `sampleNoncombatFuture` (ooc_mcts_adapter.cpp:75–101), preserving every
public feature and the live state. Do not indiscriminately call its full
routine, which also redraws RNG streams, pools and treasure contents. A
fixed small sample count changes the decision procedure but preserves
model/schema compatibility. A single deterministic sample is a cheaper
fairness mechanism to compare if averaging is too expensive. Rebaseline
all arms after the repair; it must remain opt-in.

Required focused proof: states differing only in hidden queues and hidden
RNG produce identical sampled rows and chosen actions under the same
planner seed; actual queue/RNG/public state are unchanged. Check native
weak/first-strong/no-repeat legality, acts 1–3, empty suffixes, and that
observed-prefix changes may affect samples. No claim of an exact joint
hidden-state posterior follows from this narrower feature repair.

## Current-main delta

`git diff 67973e7f..a4b3df35` changes CTM candidate loading and declared HP
domains (#437/#439), scoring helpers, tests and documentation. The ordinary
driver dispatch changes only `ctmscorerows`. `configureLiveOocMcts` returns
at its MCTS-off guard before CTM runtime loading. The inspected delta does
not change native Silver, real mechanics, or non-MCTS OOC fallback behavior.
This is a source-path argument, not executed binary equivalence evidence.

## Combat objective and available probes

`SilverSearcher::evaluateEndState` still values potions (11 each), remaining
Fairy/Lizard restoration, gold, max HP and victory speed in the final Act-3
boss. A0 boss victory HP is already valued at max HP through
postBattleHealedHp, so varying actual ending HP is not itself the suspected
final-boss error. Loss shaping includes turns survived (1.5 per turn through
turn 100), damage, draw and resources. Thus the objective is not solely
terminal win probability. This is an objective-mismatch hypothesis, not an
observed supported policy error.

The minimal candidate is an opt-in final-Act-3-boss terminal score with
victory above loss and no leftover-resource utility. Evaluate first with
exact-budget Bflat because changing score distributions can invalidate the
compiled learned-stop model. Preserve earlier fights' resource prices.

Relevant prior evidence prevents duplicate experiments:

- #400 / §369, current ledger: broad exploration/widening screen found no
  global improvement and no justified per-context controller. Do not repeat
  broad constant tuning without a sharper tactical mechanism.
- #422 is CLOSED and unmerged. Its branch `97d1e00ab` contains §385, absent
  from current main: 128 paired seeds, v_win terminal pricing lost 8.6 pp;
  hallway potion underpricing was the subsequent supported diagnostic.
  That implementation deliberately kept Act-3 final wins handcrafted.
  Final-boss-only objective repair is distinct from that negative global
  pricing experiment; lowering potion prices in early fights repeats its
  likely failure mechanism.
- Existing bossrescue347 reconstructs a complete current-source run and
  detached boss entry, checks exact original replay, and varies planner seed
  on fair roots while leaving the live future untouched. It requires exact
  10k source, source-arm parity, reuse cap 32768 and stop-after-act 3. A
  historical different-mechanics entry cannot be inherited automatically.

## Trace limits

`STS_OOC_DECISION_TRACE` emits pre/offers/post, seed, OOC index, and broad
owner (`chain`, chest_rule, relic_rule, match_and_keep, mcts). Battle rows
include encounter and outcome. It has no executable combat snapshot,
complete primitive action identity, fallback identity, or root values.
`STS_OOC_STRATEGIC_TRACE` adds gate scores/ownership. Tree profiling adds
combat root identity, selected action bits, actual steps and search shape,
but no complete public snapshot. Named tactical cases will need a minimal
targeted capture or current-source replay, followed by neutrality checks.

Knowledge impact: campaign evidence now; the inherited information-boundary
finding requires the canonical OOC/determinism KB to be corrected in the
coordinator's final change, independently of experimental strength.
