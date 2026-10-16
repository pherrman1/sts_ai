# §493 Arm C in A20 Heart rollouts: prospective protocol

Authorized by Philipp's “Let's go then” after the paired rollout-policy proposal.
Hypothesis: Arm C's distilled heart1 decisions improve CTM continuation quality
and actual Heart kills under the same per-decision OOC search CPU allowance.
Alternative explanations: imitation of tree preferences may compound mistakes;
inference overhead may leave too little search; greedy choices may reduce useful
continuation diversity. No RL loop, retraining or leaf-student promotion.

Both arms: A20 Ironclad, full Heart objective, keys collected, no act stop; Arm C
tree prior; exact-10k native Silver actual combat, allocated reuse cap32768,
adaptive/learned-stop/direct-leaf off; automatic calibrated A20 CTM, native X2-B
leaf after three CTM combats, public hidden-future sampling, ordinary tree rules,
greedy rollout shops and outcome merging. Same legal candidate construction,
mandatory Heart/key steps, PUCT1.5, widening4/.75, depth safety32, root visits.
Control: current `LEAF_POLICY=v4` continuation chain. Treatment:
`LEAF_POLICY=heart1`, same fixed rules first, then Arm C argmax over the existing
unique supported V4 candidates if every candidate scores, otherwise the unchanged
chain. The legacy `prior` option continues to mean V4 policy-head rollouts.
Arm C native SHA256 eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509.

Budget: both arms get0.25 thread-CPU seconds per OOC decision, starting before
model/root preparation and checked after each completed simulation. At least one
simulation completes; a simulation and post-search cleanup can overshoot. This is
a completion-boundary CPU allowance, not a hard deadline or equal total CPU/run.
Simulation ceiling8192; visit-lock and gap stopping off. Singleton shortcuts are
common. Record per-decision actual CPU, completed simulations, budget-stop,
ceiling-hit, singleton/abort and fallback status. Timed runs forbid forked capture,
replay, per-rollout decision logs, root-lock/checkpoint/reuse/graph diagnostics. Timing makes exact campaign
reproduction non-bitwise; default-off deterministic parity is separately tested.

Inventory: §491/492 data uses the old rollout policy, selected student and opened
holdout; it cannot qualify this treatment. §487 tested V4 policy-head rollouts,
§488 tested Arm C only as tree prior on Act-3-stop reused seeds; neither establishes
Arm C rollout/Heart quality. Reuse exact qualified Arm C weights and baseline
artifacts, but use fresh paired seeds. No historical pooling/relabeling/reselection.

Freeze reviewed source, clean checkout, binary/build receipt, all bundled models,
runner/validator/seed-guard/protocol and exact clean environment before gameplay.
One-shot canary seeds110161992/993, each both arms. Do not inspect canary efficacy
for tuning. Every launch goes through bundled seed_guard.sh. Native-Silver,
configuration, binary/model custody, exact seed/sidecar, legal executed selection,
Arm C prior in both arms and rollout usage counters must validate. Control has
zero C rollout steps; treatment positive with at least90% of attempted model
rollout decisions scored; record fallback reasons and supported-domain scope.

Canary and final resource gates on non-singleton, nonaborted searches:
positive completed simulations and legal executed choice; budget-stop fraction
at least95%, ceiling-hit fraction at most1%; p95 overshoot≤25ms, max≤100ms.
Report unsupported roots and common fallback cost separately. Failure stops for
review as INVALID_RESOURCE_MATCH, with no cohort launch/replacement/adaptive tuning.
An independent canary/custody review receipt is required before cohort opening.

Cohort:32 fixed pairs, seeds110162000..110162031. Three single-thread workers,
OMP_NUM_THREADS=1; each worker executes both arms of a source serially, AB for
even source seeds and BA for odd.900s/unit and4h cohort wall cap (each child timeout is clamped to the remaining
phase allowance; at most5s signal/reap cleanup afterward). No seed deletion,
replacement, retry, extension or outcome-dependent early stopping. Any missing or
invalid pair yields INCOMPLETE (or INVALID_CUSTODY/RESOURCE_MATCH as applicable),
with no partial efficacy verdict. Preserve all failures/partial data.

Primary: paired Heart-kill difference (treatment minus control),10,000 paired
source bootstrap resamples, RNG49320261016, percentile95% CI; exact two-sided
McNemar p and discordants. IMPROVED only if CI lower>0 and p<.05; symmetric WORSE
only if CI upper<0 and p<.05; otherwise NOT_SHOWN. The bounded pilot may not resolve
small effects or rare Heart wins. Act/floor/endHP/fightsLost/death encounter,
actual CPU per root/run and real-combat CPU are descriptive secondary outcomes.
A bundled/hash-pinned GNU time records whole-process user/system CPU; floor and
OOC profiles separately expose real-combat, search and other/fallback CPU.
No post-hoc metric becomes the primary endpoint. No default promotion from this
pilot. Only an independently reviewed improvement warrants a separate rollout
label/distillation protocol; no automatic fresh training from this campaign.

Knowledge impact: explicit rollout/CPU-control implementation contracts, §493
experiment evidence and maintained current research status.


## Pre-cohort validator amendment (version 2)

Version1's first control unit110161990 completed normally, but the validator
classified a normal root-boundary fallback (no search/actions, zero simulations,
no execution) as a completed search requiring an action. It stopped INCOMPLETE
before treatment, second canary or cohort. Preserve that original bundle/latch;
no outcomes were inspected or used for tuning. The native code is unchanged.

Version2 excludes only an exact validated root_boundary no-search event from
the completed-search resource denominator and reports its bypass count. Any such
event with simulations, selection, actions, execution, abort or singleton markers
is rejected; malformed actual search results still fail. CPU/control/coverage/
quality gates remain unchanged. Synthetic positive/negative regression fixtures
and independent review precede a new frozen bundle with fresh paired canary seeds
110161992/993. The untouched32cohortseeds remain110162000..031. No retry in the
original bundle, pooling, replacement of cohort seeds or threshold relaxation.
