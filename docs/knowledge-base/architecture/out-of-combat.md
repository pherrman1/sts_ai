# Out-of-combat policy

Last verified: 2026-10-17 for the heart1full prior default and its rollout/live fallbacks; 2026-10-17 for the opt-in Act-4 Silver route and the opt-in Silver fallback for CTM-refused combats and the Silver resolver redraw; 2026-10-16 for the CTM input encoding v2 option; 2026-10-16 for optional heart1 rollout scoring/CPU allowance (§493), the §492 evaluation recovery and Heart/key rules; 2026-10-15 for the sibling-leaf capture (§489) and the 64-rollout leaf value net (§490); 2026-10-15 for V4 policy-head rollouts (§487); 2026-10-14 for the default optional Ruby Recall filter (ADR-0034); 2026-10-14 for `LEAF_COMBATS=0` vs 3 on the current defaults (§472, §475); 2026-10-14 for bounded leaf replay and conditional target repeats (#507); 2026-10-14 for the A20 CTM stack default (ADR-0033) and manifest boss calibration (§470); 2026-10-14 for the greedy rollout shop default (ADR-0032); 2026-10-14 for bounded leaf replay (#507) and the shop deck-size playing-strength check (§463); 2026-10-13 for bounded observational leaf capture (#507), the shop deck-size default (ADR-0030), the greedy rollout shop option and shop removal prior split; 2026-10-13 for the research-candidate exposure override (§443, #514); 2026-10-12 for the OOC MCTS public X2-B win-model default (ADR-0029) and the public-futures fallback default (ADR-0028); 2026-10-12 for the CTM encoder memo (§439); 2026-10-11 for `LEAF_COMBATS=5` (§430); 2026-10-09 for the #418 pathb-r2 production CTM stack; 2026-10-08 for default ascending fallback REMOVE ordering; 2026-10-08 for the CTM escape capability; 2026-10-07 for the CTM research-candidate mode; 2026-09-28 for opt-in equivalent-outcome merging (#384), final-card reward continuation and search skip/leave equivalence; 2026-09-27 for the qualified default CTM stack when OOC MCTS is enabled; 2026-09-26 for the fail-closed depth safety cap; 2026-09-25 for opt-in authoritative semantic-prior capture; 2026-09-20 for semantic MCTS, source-prior projection and sampled noncombat outcomes; 2026-09-15 for qualified V2 combat support; 2026-09-14 for opt-in MCTS controls and continuation-limit accounting; 2026-09-10 against the current working tree (semantic OOC
decision coverage and reward continuation).
Previously verified 2026-08-09 (key collection
gated behind STS_COLLECT_KEYS=1, default off; BEST banner includes keys=collect/skip).
Previously verified 2026-08-09 (Act-4 key collection added to every REWARDS handler
and act-3+ rest rooms, now opt-in via the flag).
Previously verified 2026-08-05 (checkpoint-oracle terminal win-GBM +
margin-gate levers added and falsified §111; Wave B regret gate + Q_win
truth-check mode + map-DAG encoder (V6) + Phase F soft-target policy objective
and policy-score gate env added; Phase F falsified §104, label-noise wave §105
null — learned one-ply label line closed).

## Purpose

Describe run-level state/actions, the ordered policy stack used by `bestbench`,
and the boundary between default native inference and opt-in strategic
experiments.

## Current implementation

### Synchronous OOC MCTS substrate

Last verified: 2026-09-14 for search-local preparation, metadata, and exact root shortcuts.

`OocMctsPlanner` is a synchronous generic search core over opaque state
and action IDs. `OocGenerativeModel` supplies complete actions/priors, actual
successor samples, terminal values and injected leaf values in [0,1]. Distinct
decision nodes use PUCT; chance nodes retain independent equal-weight outcome
particles (including duplicate IDs) and reuse stochastic particles uniformly,
never by value. Providers may explicitly mark a transition deterministic; after
its first sample the core reuses that single child instead of widening it. Action Q is the Monte Carlo mean of sampled trajectory values.

Depth counts action transitions (root zero); exact terminals precede model-defined
leaf boundaries, which precede the technical depth safety guard,
and newly expanded downstream nonterminal leaves use the injected evaluator.
With `OocMctsConfig::mergeEquivalentOutcomes`, a newly sampled successor whose
provider `outcomeEquivalenceKey` equals an earlier particle's key in the same
chance node reuses that particle's decision node. The particle list still gets
one entry per sample, so uniform reuse stays frequency-weighted and the widening
schedule counts samples, not distinct nodes. Providers without keys, or with the
option off (default), keep independent particles. Merged nodes are captured once
in tree snapshots; `mergedOutcomes` counts pooled samples.
The root expands and selects an action in the first simulation. Chance visit N
uses `max(1, ceil(k*N^alpha))` with prospective N starting at one. Defaults are
`cPuct=1.5`, `k=2`, `alpha=0.5`, safety cap 512. A nonterminal,
non-boundary state at `depth >= maxDepth` aborts the entire root with
`ooc_depth_safety_cap_<cap>_state_<stored-state-id>`; partial action statistics
are discarded. The cap-hit state is never evaluated as a normal leaf.
`maxDepthReached` includes the offending depth for diagnosis. Live accounting
records this under `continuationLimitAborts`/`continuation_reasons`, without
inventing an unsupported combat. Priors normalize with uniform zero-mass
fallback. Before PUCT, every legal action receives one visit, choosing the
highest-prior unvisited action and then ascending ID. Zero individual priors
cannot suppress actions; cPuct=0 visits all actions once, then exploits Q.
PUCT ties use ascending action ID; final choice uses visits, then Q, then
ID. Each search resets its tree and seeded RNG; providers must preserve IDs and
reset any mutable sampling state for exact replay.

Particles occupy a search-local `deque<DecisionNode>` arena with stable references,
so generating each particle does not require a separate heap allocation. PUCT
computes the parent square root once per selection without changing the numeric
formula or ties. Prospective widening limits use the original formula, cached
through the budget up to 1,048,576 visits; larger visits evaluate it on demand.

For visit-selected roots, a leader locks when its visit count is strictly
greater than every challenger's count plus the remaining budget. Mean-Q
selection never uses this shortcut. Generic planner configuration requires
`model.searchGuaranteedNonAborting()` by default. Explicit
`allowUnqualifiedRootStop=true` permits stopping without that guarantee.
Live OOC MCTS enables this policy by default; `STS_OOC_MCTS_EARLY_STOP=0`
restores the guarantee requirement. A singleton locks after its first completed
simulation for direct planner callers; the live adapter bypasses a validated
singleton root before search.

This is an intentional fallback-policy tradeoff: a later support or continuation
abort would invalidate the full-budget winner, but early stopping can skip that
abort and execute the locked action. `OocGameContextModel` still returns false
for the guarantee; Smoke support and other abort paths are unchanged. Observed
zero aborts do not qualify that contract. Metrics count locked-root stops and
saved simulations separately. See [ADR-0014](../../../decisions/0014-live-ooc-visit-lock-stopping.md).

`OocMctsConfig::observeRootLock` is an opt-in diagnostic that suppresses both
locked-root stopping and the sole-root bypass.

`STS_OOC_MCTS_CHECKPOINT_TRACE=<fresh.jsonl>` instead preserves the live policy
and runs a separate discarded full-budget shadow search from the same root,
history, models and search seed. It requires 2048 visit selection and rejects
combination with the live root-lock observer. It records all action IDs, priors,
visits and Q after 128/256/512/1024/2048 completed shadow simulations, plus
live and shadow action/abort/completed-budget status. Late shadow aborts do not
change the live action. Existing live MCTS CPU and counters exclude the shadow;
process runtime includes it and is not a deployment performance benchmark.
The generic `rootCheckpointSimulations` option only records reached positive,
strictly increasing thresholds; it never disables early stopping itself.
Offline analysis uses visits/Q/ascending-ID tie-breaking, separates singleton
roots and aborts, and reports additional savings against existing live stopping
as well as nominal 2048. Checkpoint stability means stability only at observed
checkpoints, not at every intervening simulation. No rule is deployed by this
diagnostic. `tools/analyze_ooc_root_checkpoints.py` implements the offline report.

The root-lock observer suppresses
locked-root stopping and the sole-root bypass. It records the first
strict visit lock (including a zero-remaining-budget lock), its action and
remaining simulation budget, and wall time from that completed simulation to
search completion/abort. No extra sampling draws are consumed. Mean-Q roots
have no visit-lock observation. Live `STS_OOC_MCTS_ROOT_LOCK_TRACE=<fresh.jsonl>`
enables it and writes one JSON record per searched root with seed/decision,
budget/completed/attempted simulations, lock/action/tail time, full-budget status,
abort reason, final action and the non-aborting guarantee. Existing run CSV
columns and actual early-stop/saved-simulation counters retain their semantics.
Only completed full-budget roots contribute conditional opportunity estimates;
locked roots that later abort remain invalid and must be reported separately.
Even zero observed aborts or matching locked/final actions cannot prove the
provider guarantee. The Smoke-excluded V2 artifact and remaining continuation
abort paths do not qualify the provider guarantee; live stopping uses the explicit
unqualified policy instead.

Each live search builds a fresh tree; there is no reroot or tree reuse across
real decisions. Live `STS_OOC_MCTS_REUSE_TRACE=<fresh.jsonl>` measures the
opportunity without changing search. Full-state identity never matches, because
sampling redraws the unrevealed encounter suffix and so advances `monsterRng`
counters in every stored particle. Public-state identity matches often within
noncombat stretches, never across a real combat. Even then the matched outcome
is split across many independent sibling particles, since sampled mode can add
a particle on every chance visit. Rerooting to one particle therefore retains
little work (§361: 0.90% of searched simulations on the representative
workload). Merging publicly identical particles would change search semantics
and is an open question.

The focused `ooc_mcts` CTest verifies toy stochastic MDPs and malformed inputs.
`apps/one_combat/ooc_mcts_adapter.{h,cpp}` supplies the
`OocGameContextModel` integration through explicit `one_combat oocmctsselftest`
and the guarded `ooc_mcts_adapter` CTest. The adapter requires loaded native
V4 and win models. `OocStrategicTokNet::predictPolicyLogit` shares the 184-wide
state/action representation with Q, then applies `pol.0 -> GELU -> pol.2`.
Finite logits supply weights `exp((logit - max_logit) / 1.0)`; the core
normalizes them. Q remains unchanged in the live one-ply gates.

Each immutable stored `OocStateId` lazily owns candidate/boundary/uniqueness
metadata and, when needed, policy logits and raw planner priors. The same
candidate ordering and token construction feed the same policy inference.
V4 `prepareState` evaluates deck attention, relic/potion pooling, and state
fusion once per immutable candidate set. Its value-owned 128-float representation
is reused for each action's unchanged entity/action encoding and policy or Q
head. The MCTS prior and the eight token Q-gate loops use this path, including
leaf continuation and ordinary live fallback. Each loop rebuilds after state or
path changes; no cache survives the loop or model reload. Candidate ordering,
Q margins/ties, fallback dispatch and RNG consumption are unchanged. Legacy
single-action inference entry points remain available.
`OocStrategicTokNet::load()` also builds derived tables (`rebuildDerived()`, §450):
every deck token (card id, upgrade, count 0-9) with its GELU output and qkv row,
and transposed copies of the deck projection, fusion, policy and Q first
layers. The fast paths compute several output units at a time, each in its
original float order, and `PreparedState::qPrefix` holds the Q head's
first-layer sum over the 128 state inputs; outputs are bitwise those of the
reference loops (`ooc_tok_net_fast` ctest). A net whose weights are set or
edited directly must call `rebuildDerived()`; without tables it runs the
reference loops.
Subsequent queries for the same immutable state reuse cached logits/priors.
A prepared native combat transition computes support and encodings for one
fixed precombat input; each draw retains the native conditional heads and RNG
sequence. Live sampled noncombat successors prepare their own combat input:
encounter, persistent state and RNG can differ between samples of one edge.
Preparations never cross these sampled successors. Exact copied-state offline
fixtures retain the original edge cache for parity checks. No mutable
process-wide cache exists; maps remain detached from the live run.

The adapter owns complete semantic sibling sets from
`enumerateOocSemanticPrimitiveBindings` on rewards, shop, campfire, events,
treasure, boss relics and already-open supported selectors. Unsupported,
incomplete or empty enumeration is a leaf/fallback boundary; it never narrows
the tree to primitive V4 candidates. BATTLE remains a boundary and exact run
loss/victory retain precedence. MAP alone keeps its existing primitive V4
candidate contract (including missing-map and row-14 boundaries).

Before semantic OOC enumeration, detached reward states deterministically
collect every ordinary gold reward through the normal `GameAction::GOLD`
execution path. This gold-only normalization is applied at the root and after
each hypothetical successor; it leaves the REWARDS screen and all non-gold
choices intact, so `TAKE_GOLD` remains available to semantic execution and
diagnostics but is not an MCTS candidate. The simulator's live OOC policy also
applies the closure to its real `GameContext` before search, keeping subsequent
semantic action resolution on the same state. The live advisor emits one
captured gold choice as a single-action pass-through and re-observes before
scoring any remaining reward decision. Multiple captured gold choices are
handled one observation at a time, including when their native primitive bits
coincide. If the capture marks an unopened card group as
`CARD_GROUP_NOT_REVEALED`, the importer still validates the complete schema and
gold-to-live mappings before allowing that gold pass-through. A fixed potion
pickup is also permitted when all visible potion rewards fit and Sozu is
absent; remaining reward decisions require a fresh observation. Ectoplasm and
Bloody Idol retain their normal acquisition semantics.

With constrained potion space or Sozu, the driver may reveal a single card
group while retaining already-public sibling potions. The MCTS root masks
parent potion actions until card take, ordinary Skip, or Singing Bowl returns
to the parent rewards. A one-shot continuation removes only that card group;
ordinary Skip does not acquire Bowl's HP. Direct V4 and differential replay
reject this parent-potion continuation. A public physical-reward decline ledger
prevents automatic reopening of vanilla's retained skipped card icon; explicit
reopening clears the decline. Unrevealed card identities are never imported.

V4 remains a primitive-trained source-level prior. When the state's unique
semantic source primitives exactly match the complete, duplicate-free V4
candidate set, each source is scored once with the existing policy head and
temperature. Its raw prior weight is divided equally among its semantic children.
For duplicate physical UPGRADE positions, coverage still checks the full
physical set; their logits are averaged within each retained semantic card
class before applying temperature, so extra copies do not increase its prior.
One-to-one actions retain the original prior. Unqualified source coverage,
including REMOVE/TRANSFORM selector roots, yields uniform priors across the
entire sibling set; explicit `STS_OOC_MCTS_PRIOR=uniform` does the same.
Compound target preference is searched, not learned by V4. This adoption does
not imply semantic V4 training or change its artifact/schema.

Root construction requires an explicit `PathHistory`: prior room visits are not
recoverable from `GameContext` and feed both V4 globals and native win features.
The nonempty-history regression verifies both routes against direct evaluation
using the supplied history. Snapshots live in a deque, with detached map copies at root and each native
semantic or primitive successor and branch-local updated `PathHistory`.
Semantic action IDs are state-local ordinals bound to immutable candidates,
which retain canonical semantic keys, source primitives and typed actions. MAP
IDs remain primitive bits. Successors execute transactionally through
`executeOocSemanticAction`; an enumeration/execution disagreement aborts the
whole root without trusting partial visits/Q. Leaves call the native-only
`vStateWinNative` seam: unavailable models or nonfinite/out-of-range values
throw, with no server fallback and no clamping. Leaf feature evaluation
scopes the stored path history and restores the caller's history.

`OocGameContextModel` accepts an optional shared `CombatTransitionSampler`.
The default adapter options retain the offline scaffold contract described here;
opt-in live selection uses the corrected checkpoint contract below.
After the semantic action (or primitive MAP action) and prebattle history update, it captures
`combat_predictor_input_v1` before battle initialization, using the current
`potionKeepValue`. Unsupported states retain the existing BATTLE leaf and native
win-value seam. Death sets PLAYER_LOSS without continuation. Victory applies a
RAW persistent result and calls `regainControl()` once, then updates history
like the live run loop. A resulting second BATTLE remains a leaf. No sampler
preserves the original successor behavior.

`NativeCombatTransitionSampler(path)` is explicit opt-in; its constructor throws
if the requested artifact is absent or incompatible. The versioned
`COMBAT_TRANSITION_RUNTIME_V1` binary contains six frozen source identities,
normalization buffers, class/vocabulary domains and FP32 tensors in lexical
name order. `tools/export_combat_transition_runtime.py` verifies all six source
hashes before deserialization and creates its output exclusively. Four separate
Attention encoders share one native implementation; the signed-HP encoding also
feeds the relic decoder. Learned draws use only the supplied planner RNG.
The support gate retains the qualified precombat envelope and consumption-only
potion closure (explicit Alchemize and Entropic Brew excluded; off-color alone
is allowed, as documented in the [source audit](../behavior/combat-potion-generation.md)),
rejects active unqualified Lizard Tail, and excludes Inserter
because its carrier state has no qualification corpus tokens. One residue per
turn/attack/card/shuffle group reconstructs all related counters. Potion RNG
copies through; misc RNG replays the exact bounded initialization calls,
including rejection, as in #171. The four other battle streams copy through
until native reinitialization. Real artifacts and captured-state parity/smoke
results remain external. The [native adapter evidence](../../experiments/evidence/native_combat_adapter_2026-09-14.md)
qualifies this combat boundary at 1e-4 probability tolerance; it does not qualify
the full planner. `combat_transition_runtime_probe` and
`tools/qualify_combat_transition_runtime.py` perform offline CPU FP32 parity at
fixed max absolute probability tolerance 1e-4; they do not drive gameplay seeds.

The qualified `COMBAT_TRANSITION_RUNTIME_V2` artifact is tracked at `selfplay/models/combat_transition_near_full_except_smoke_v2.native`. Its default survival component is the targeted attention-HPO winner; maxHP, HP, potion and downstream heads remain the frozen near-full checkpoints. Selected component identities, passing qualification and ordered all/TEST cohort hashes are enforced by export/load guards. V2 retains the legacy envelope while supporting shared gold, Writhing, Ritual and Brew trajectories; it excludes initially held Smoke, pre-existing `smokeBombUsed`, and Writhing with Ritual Dagger. Executed support is exactly 505,935/510,030 overall and 51,036/51,441 TEST. V1 behavior above remains unchanged when a V1 artifact is selected.

V2 Brew draws a full-width planner-owned hypothetical native potion RNG on first use, reuses it recursively and retains its advanced RAW state. Unused Brew copies historical potion RNG; other streams follow the existing replay/copy contract. Explicit `ESCAPE` requires matching RAW `smokeBombUsed`, rejects boss escape and uses native `regainControl()` without victory rewards. Generated Smoke/ESCAPE remains possible in a supported Brew trajectory. The probe and `tools/qualify_combat_transition_near_full.py` verify CPU FP32 probabilities, complete RAW sampled states, planner-stream advancement and scalar/prepared parity; unsupported states consume no planner draws. All final slice gates and hard-validity checks pass as reused development evidence in the [final report](../../experiments/evidence/near_full_combat_support_2026-09-14/REPORT.md). V2 uses the same explicit model path; no default MCTS enablement is implied.

The opt-in experimental width-64 strong-WD survival alternative is exported by
`tools/export_combat_transition_survival_deepset.py`. It verifies the exact #217
checkpoint and tracked Attention control, replaces only survival tensors, and
adds `experimentalSurvival` with `qualified:false`. The V2 loader validates its
fixed identity and DeepSets tensor graph; all other components, support rules,
and defaults remain unchanged. Selection uses the existing explicit combat-model
path, not a new default. Retained control qualification metadata does not qualify
the replacement. The non-TEST checker is
`tools/check_combat_transition_survival_deepset.py`; its
[Stage-A evidence](../../experiments/evidence/deepset_survival_online_stage_a_2026-09-17/README.md)
is implementation evidence only. The independently reviewed
[Stage-B speed screen](../../experiments/evidence/deepset_survival_online_stage_b_2026-09-18/README.md)
stopped below the 10% end-to-end CPU improvement threshold; the gameplay-quality
gate did not run. The alternative remains experimental, not a promoted default.

Copied native RNG streams still govern other stochastic OOC transitions. This
adapter resolves the combat boundary only and remains **not a fair stochastic
environment model** or a scientifically qualified full OOC planner.

### Opt-in live OOC MCTS selection

`STS_OOC_MCTS=1` intercepts each nonbattle decision immediately before the
existing `runFullRunOocPolicyStep` chain in `runFullRunOOC`. Startup requires
loaded native V4 policy and native win models plus a compatible combat
artifact. When `STS_OOC_MCTS_COMBAT_MODEL` is unset, it loads the tracked
`selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native` artifact and
automatically pairs it with the pinned standard Attention Brew fallback
`selfplay/models/combat_transition_near_full_escape_pathb_r2.native` (the
pathb-r2 stack with the §423 Lizard capabilities since §435, see "Production CTM
stack since #418" below). An
explicit combat-model path overrides the automatic stack; explicit artifact
failures are fatal. Research only (§411): `STS_OOC_MCTS_COMBAT_RESOLVER=silver`
replaces the CTM with `SilverCombatTransitionSampler`, which plays each imagined
combat with native Silver (`STS_OOC_MCTS_SILVER_SIMS` per root, root prior on
via `STS_SILVER_ROOT_PRIOR_SCOPE=override`, live combats plain) on a redraw of
`gc.seed` and the six carried combat RNG streams; a Silver failure returns
UNSUPPORTED and aborts that search to the V4 fallback. The `gc.seed` redraw
(added 2026-10-17) is a safeguard: live OOC MCTS always samples non-combat
futures, and `sampleNoncombatFuture` already redraws `gc.seed` before every
imagined combat, so §411's Silver arms did not see the real hidden future. The
extra draw changes the resolver's RNG sequence, so reproducing §411 needs its
binary. Opt-in
(`STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS=N`): `SilverFallbackCombatTransitionSampler`
wraps the CTM stack and plays only the combats the CTM refuses with plain Silver
at N simulations, on the same redraw, instead of aborting the search to V4. In a
1-seed act-1 smoke (seed 111000010, A0, forced Lizard Tail, a CTM without the
Lizard correction, 256 OOC simulations) MCTS kept 31 of 32 decisions instead of
14 of 36, at 334 CPU-s instead of 16 (N=256). Opt-in
(`STS_OOC_MCTS_ACT4_SILVER_SIMS=M`): the same wrapper plays every Shield and
Spear and Heart combat with plain Silver at M simulations without asking the
CTM, because no CTM was trained on Act 4 (the deployed A20 stack predicts 0.28
Heart death where its teacher dies 0.95, audit
`/mnt/project-files/audit-2026-10-17/ctm-a20.md`). It combines with
`STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS`; set alone, other refused combats still
abort to V4. Both have the same exclusions (`STS_OOC_MCTS_COMBAT_RESOLVER`,
`STS_OOC_MCTS_LEAF_CAPTURE`) and require `STS_OOC_MCTS=1`; `=0` means off, as unset. Per run,
`[ooc-silver-fallback]` counts these combats as `act4_silver`. The opt-in
`boss` leaf value still prices the Heart through the CTM expectation. CPU cost
and playing strength are unmeasured. Startup also requires the effective Silver reuse cap to be
32,768; the experimental 131,072 override is rejected. Real combat requires
ordinary exact-10k Silver, allocated reuse, and adaptive-off, preserving the
frozen teacher cap contract. `STS_OOC_MCTS` itself remains OFF by default and
does not load a combat artifact or run MCTS. Both arms retain the same normal
real combat branch and the same fallback OOC policy chain.

The promoted DeepSets artifact declares the Entropic Brew fallback contract.
The adapter routes the whole transition to the standard Attention artifact
when Entropic Brew is present in the pre-combat inventory; it does not switch
models based on generated outcomes. The fallback's actual SHA256 must equal
the standard artifact pinned by the fast artifact's identity (`b9188de0…` for
the pathb-r2 default, `e9a18951…` for the pre-#418 `lizard_t2`); the
runtime also checks source/cohort metadata. `STS_OOC_MCTS_BREW_FALLBACK_MODEL`
overrides the automatic fallback path. Missing or invalid required artifacts
are fatal.

DeepSets encoders memoize each card, relic and potion token's MLP output per
thread, keyed by runtime instance, encoder group and the token's integer
fields; pools still sum in token order, so outputs are bit-identical (§439;
`ctm_encoder_memo_parity` checks against the unmemoized reference,
`setEncoderMemoForTesting(false)`). When an artifact's `max_hp` encoder tensors equal
its `hp` encoder byte for byte (`sharedHpEncoder()`, true for pathb-r2), the
unprepared near-full sampler takes maxHP from the hp encoding, as the
prepared path does.

**CTM input encodings.** Every shipped artifact uses the original encoding
(`ctm_input_v1`, no `inputEncoding` in the header): act and floor are
standardized scalars, card misc is `clip(misc, -20, 20)/20`, and
`potionKeepValue` is a global input. Three consequences: Act 4 is an
extrapolation of the act/floor slope even after Act-4 rows are trained on; a
Ritual Dagger (misc 15, +3/+5 per kill) looks the same from its second kill
on; and the forecast moves whenever the potion-keep model changes. An artifact
whose header declares `inputEncoding: "ctm_input_v2"` is encoded instead with
act as a fifth global category (`act-1`, acts 1..4; any other act throws) beside
the raw run floor (Act 4's floors 52..55 lie just past Act 3's 35..51; Philipp
chose raw floor over floor-within-act, which would map the Act-4 elite onto an
early-act floor), misc as `sign(m)*log(1+|m|)/log(101)` with
`|m| <= 10000`, and no `potionKeepValue` input. It must also declare the v2
`continuousFields` (8) and `globalCategoryCounts` `[4,64,10,10,4]`, and its
tensor graph has 8 scalar statistics, `global_category.4` (4x8) and
`global_mlp.0` / `global_proj` with 48 inputs. Any other `inputEncoding` value,
including an explicit `ctm_input_v1`, is rejected. The predictor input record
is unchanged, so captured rows serve both encodings. `tools/ctm_input_encoding.py`
is the Python reference; the Phase-1 `DeepSetsModel`/`AttentionModel`, the
surrogate `DeepSetsEncoder` and the ablation `AttentionEncoder` take
`encoding=` (default v1, unchanged modules) and need statistics from
`ctm_input_encoding.scalar_stats`. The retrain stage CLIs and exporters do not
pass an encoding yet, so no v2 artifact exists. CTests `ctm_input_encoding`
(native v2 DeepSets output against a numpy reference, encoding contract and
rejections) and `ctm_input_encoding_selftest`.

A retrained stack loads only as a research candidate. When
`STS_CTM_RESEARCH_CANDIDATE_MANIFEST` and its `_SHA256` are set, an artifact
whose metadata declares `researchCandidate: {"candidateId": ...}` is checked
against that `ctm_research_candidate_v1` manifest instead of the production
pins (`tools/ctm_candidate.py` stamps exports and writes the manifest). The swapped values are artifact bytes, source and checkpoint hashes,
support-census indices and the active-Lizard q/r identity. Schema, shapes, the
HP envelope, support exclusions, the qualification class and the Lizard
definitions stay pinned, with one recorded exception (§443): a standard artifact
exported with `export_combat_transition_near_full.py --exposure-override F` carries
qualification class `FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS_BY_OVERRIDE` instead of
`FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS`. F is a `ctm_gate_override_v1` (stage
`final-support-exposure`) whose `qualificationSha256` binds the exposure report and
whose `failures` name exactly its failed gated slices; each waived slice needs exact
target mass on every row (no zero-mass rows), a finite mean and a source-bootstrap
95% CI whose lower bound is ≤ 0. The header records `exposureOverrideSha256` and
`waivedSlices`, and the FAIL report stays referenced by `exposureSha256`. Only a
manifest research candidate (`researchCandidate()`) may load that class, for the
artifact itself and for the Brew-fallback pair check; production artifacts and the
built-in pathb-r2 manifests never may. A candidate cannot claim the production default or a
promoted Lizard. The Brew fallback is pinned by the fast artifact's identity, so
a candidate fast artifact needs its own standard artifact. Without the variables
nothing changes, and artifacts without the declaration always use the
production pins (CTest `ctm_research_candidate_loader`). A
`ctm_research_candidate_v2` manifest also pins `domainSha256`, a declared HP
domain from `tools/ctm_hp_domain.py`. The runtime then derives the signed HP
classes and the HP-head and relic-delta row counts from that domain. It also
recomputes the domain hash, and it requires the lowest class to equal
`1 - preCurHpRange[1]` and the maxHP deltas to stay production. Production keeps
the literal -160..143 domain.

**Production CTM stack since #418 (ledger §412).** The default is the pathb-r2
candidate promoted with unchanged bytes: fast
`selfplay/models/combat_transition_deepsets_pathb_r2.native` (`90806c25…`) and
standard `selfplay/models/combat_transition_near_full_escape_pathb_r2.native`
(`b9188de0…`), both escape-capable, with Writhing + Ritual Dagger still
excluded and no `lizardBrew`/`lizardFairy` capability. The runtime embeds a copy
of its v3 manifest (`d9d8377e…`), so the pair loads without
`STS_CTM_RESEARCH_CANDIDATE_MANIFEST` and default runs report identity
`production`; the statements above about "production pins" describe the
pre-#418 identity, which artifacts without a `researchCandidate` declaration
still use. **Since §435** the default fast artifact is the §423 Lizard-capable
`selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native` (`c6d56bbc…`):
the same pathb-r2 tensors with `lizardFairy` and `lizardBrew` added to its header,
pinned by a second built-in manifest (`64da1776…`, the §423 candidate manifest
byte for byte). Both built-in manifests declare candidate `pathb-r2`; a load
picks the one that lists the artifact's bytes, so the #418 fast artifact
(`90806c25…`) still loads as `production` without a manifest. Rollback to the
#418 stack: `STS_OOC_MCTS_COMBAT_MODEL=selfplay/models/combat_transition_deepsets_pathb_r2.native`,
`STS_OOC_MCTS_BREW_FALLBACK_MODEL=selfplay/models/combat_transition_near_full_escape_pathb_r2.native`
and `STS_OOC_MCTS_ACTIVE_LIZARD=1`. Rollback to the pre-#418 stack:
`STS_OOC_MCTS_COMBAT_MODEL=selfplay/models/combat_transition_deepsets_lizard_t2.native`,
`STS_OOC_MCTS_BREW_FALLBACK_MODEL=selfplay/models/combat_transition_near_full_except_smoke_v2.native`
and `STS_OOC_MCTS_ACTIVE_LIZARD=1`. The live advisor still uses the pre-#418
stack (open follow-up). OOC MCTS stays off by default.

**A20 stack (§470, default since ADR-0033).** With the automatic default stack
(or `STS_OOC_MCTS_A20_CTM=1`) live OOC MCTS adds a second hybrid sampler beside
the default one; `STS_OOC_MCTS_A20_CTM=0` turns it off: the §443 Stage 4 `pathb-a20` Lizard candidate,
bundled in `selfplay/models/` and pinned by a third built-in manifest
(`kA20CandidateManifest`, `00bb4da6…`). `liveSamplerFor(gc)` hands it to every
OOC MCTS search whose root state is at ascension 20; other ascensions keep the
default stack. That manifest carries `bossSurvivalLogitShift` (−0.18325, fit on
Stage 1 VALIDATION boss rows): every runtime loaded under a manifest with this
optional v3 field adds it to the death logit of boss encounters
(`sts::isBossEncounter`, which includes act-1 bosses fought from an event). An
artifact declaring `pathb-a20` with no research manifest naming that candidate
now loads under this built-in manifest. Offline on the fresh Stage 4 corpus the
calibrated stack passes all five Stage 3a criteria (ledger §470).

A `ctm_research_candidate_v3` manifest also lists each artifact's
`capabilities` (`{"standard": {...}, "fast": {...}}`), and an artifact's
metadata `capabilities` must equal its role's entry; production has none.
Capabilities need a near-full artifact. Two lift support exclusions. `writhingRitual` (`{}`,
written by `tools/ctm_capabilities.py writhing-ritual`) changes no tensors and
drops the `writhing_ritual_intersection` exclusion: the sampler already draws
the Writhing event and the Ritual Dagger payouts jointly, so the capability only
declares that the candidate was trained and gated on that cohort (CTests
`ctm_writhing_ritual_runtime`, `ctm_capabilities_selftest`). The other is
`escape` (`{"checkpointSha256": ...}`, written by
`tools/ctm_escape.py extend`); both can be applied in either order. An escape-capable near-full artifact has a 1x64
escape head on the HP encoding and the escape bit as the HP head's 73rd input,
and it drops the `smoke_bomb` exclusion (`pre_smoke_bomb_used` stays). The
sampler draws the escape after maxHP and before HP, but only for an eligible
state: not a boss fight, with a Smoke Bomb in a usable slot. HP then uses the
drawn bit. The potion trajectory is conditioned on it as well: escape 0 forbids
using a Smoke Bomb, and escape 1 forbids stopping or discarding one, so the
trajectory ends with its use. A Brew-generated Smoke Bomb therefore never
escapes. Forecast and expectation mix the two HP heads by the escape
probability. A conditioned victory (the Lizard branches) never escapes. The
fast and Brew-fallback artifacts must agree on the capability. CTests
`ctm_escape_runtime` and `ctm_escape_selftest` cover loading, Python/native
head parity and sampled escapes.

With the automatic model stack, the qualified active-Lizard correction is
enabled unless `STS_OOC_MCTS_ACTIVE_LIZARD=0` is set as a rollback. It strips
active Lizard from the ordinary CTM children, applies the frozen mechanical-q,
learned-r and T2 semantics, and restores Tail active or spent on the sampled
post-state. The pre-#418 production artifact (kept for rollback)
`selfplay/models/combat_transition_deepsets_lizard_t2.native` has artifact
SHA-256 `abb2a9ead6efd6b97ee64192e0459eb08ceff7fd93f2b5f4b87a0bf379e571ab`
and unchanged DeepSets tensor-payload SHA-256
`429f9dc018a6b9de231657df4aba787bddc2de2e4cecb2e7989e167c37813139`.
Its metadata is pinned to Gate 2 PASS report SHA-256
`1ecd285c78e69249b6e5f46943d84cc10bc4bb86eea4e912f1c0abe774fef1d9`.
On a fast artifact without Lizard capabilities (the #418 and pre-#418 stacks),
active Lizard + Entropic Brew, Fairy Potion, and Mark of the Bloom are
explicit boundaries that use the existing fail-closed or exact-path behavior.
A fast artifact can lift the first two with v3 capabilities; the default stack
has both since §435
(written by `tools/ctm_lizard.py extend`; the artifact needs its own
active-Lizard correction). `lizardBrew` (`{"rModel": ...}`) routes a Brew state's
three classes to the standard child, whose survival gives q and the reserve
feature, and uses that r model. `lizardFairy` (`{}`) composes a Fairy Potion
before the Tail, as `Player::wouldDie` does: the ordinary and reserve inputs
keep the Fairy, and the Tail-consumed branch drops every Fairy Potion. A
Brew-generated Smoke Bomb can end either winning branch in an escape. Bloom
stays on its exact path. The capabilities are fast-role only; the Brew fallback
artifact may not carry them (CTests `ctm_lizard_runtime`, `ctm_lizard_selftest`).
Explicit model paths keep the correction off unless
`STS_OOC_MCTS_ACTIVE_LIZARD=1` is also set and a Brew fallback is available.
The correction changes only OOC CTM handling; it does not enable OOC MCTS.

`selectOocMctsAction` constructs detached snapshots and uses the existing PUCT,
progressive widening and depth defaults with `STS_OOC_MCTS_SIMS` (default 512).
For a native simulator graph, set `STS_OOC_MCTS_GRAPH_FILE` to a fresh JSON path
and `STS_OOC_MCTS_GRAPH_DECISION_INDEX` to the zero-based nonbattle decision
index (default 1). The selected search captures up to 4,096 tree nodes after
search, labels them from the native `GameContext` and model action keys,
and writes seed, search seed, root state, candidates, selected action, and
truncation status. Captured game actions carry human-readable map destinations
or semantic reward choices; state summaries carry floor, room, screen, map
position, HP, and gold. Particle edges mark each combat transition sampled by
the CTM with its encounter and sampled outcome. CTM work inside leaf evaluation
does not create a retained edge. Render with `tools/render_ooc_mcts.py --snapshot JSON
--output HTML`. This is an opt-in diagnostic of the ordinary simulator search;
the graph's loss nodes are sampled terminal outcomes, not independently played
games, and their stored HP can retain its precombat value.
Its search seed is `SplitMix64(runSeed XOR SplitMix64(decisionIndex))`, using
explicit unsigned 64-bit arithmetic. The index increments once per actual
nonbattle run-loop decision, including unsupported roots. It consumes no
simulator RNG. Terminal/boundary roots and whole-root support aborts return no
action; completed supported searches must return a legal adapter candidate ID.
A root with one valid, unique semantic candidate returns that current action
without constructing a tree, even though `OocGameContextModel` cannot guarantee
hypothetical continuation support. A later unsupported real decision is handled
at that later root. The bypass reports `trivialRootBypasses` with zero
simulations, attempts, transitions, leaf evaluations, or combat draws. Explicit
root-lock observation and root checkpoints still request search. Roots with
multiple candidates retain whole-root search and abort/fallback behavior.
Snapshots are discarded before
`oocMctsPolicyStep` resolves the retained canonical key against fresh complete
semantic candidates, requires exactly one match, and executes transactionally.
Stale/missing/ambiguous identities execute nothing. An active live action
observer causes fallback before mutation; it is never silently disabled. MAP
continues to resolve fresh primitive bits. If it enters BATTLE, real combat remains pending for the
ordinary next run-loop iteration. No sampled combat result transfers to live
state.

Live leaves never apply `v_win` to unresolved rewards, shops, events, selectors
or battles: rich win features omit those pending contents. `evaluateLeaf` deep
copies the node and applies the existing ordered OOC policy chain until a map
checkpoint or exact terminal, capped at 256 continuation steps by default.
Unresolved exhaustion aborts the whole root to V4 with a dedicated continuation
reason, never a fabricated scalar value. Optional additional-combat horizons use
a 1024-step cap. This is a V4/policy-chain continuation estimate, not a
learned screen-aware value. Branch history, action/combat observers, policy
trace bookkeeping, Silver diagnostics and potion pricing are scoped and restored.
Corpus capture is incompatible with live MCTS.

Supported imagined battles use the frozen surrogate. If the precombat gate or
sample returns unsupported, `OocSearchUnsupported` aborts the **entire root's
search**. Partial Q/visits are discarded and no action is selected; the live
run loop uses its unchanged V4/OOC policy chain for that decision. Unsupported
states receive neither a generic precombat value nor an invented scalar penalty.
Their reason and all completed/attempted search work are retained in diagnostics.
A thread-local guard forbids native combat playout during OOC imagination,
including optional leaf-policy counterfactuals: these also abort the root.
There are no imagined Silver battles. Supported death is exact zero; victory
carries sampled persistent costs and native rewards. Leaf projection resolves
chained supported battles; the stop-after-act boss is an exact win horizon.

Live MCTS requires real ordinary Silver at exactly10,000 simulations, allocated
reuse and no adaptive escalation; per-room budget changes fail. The corpus teacher
was `silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77`; this aligns
actual policy configuration/budget, not teacher/model accuracy. Live noncombat
transitions use planner-owned sampled futures. Fail-closed root fallback may reduce MCTS
ownership substantially, and low ownership is evidence about support, not policy
improvement. The leaf fallback uses the standard bestbench chain options
`restV=false, shopV=true`; other driver configurations are not qualified here.

Live MCTS calls `sampleNoncombatFuture` on a detached copy before every searched
transition and during leaf continuation. It replaces native RNG states using
full-width planner draws while preserving historical counters, and replaces
the hypothetical run seed so native per-floor resets and next-act generation
cannot recover the live future. It shuffles remaining relic/colorless pools,
resamples unseen normal/elite queues with native weights and history rules,
and samples the hidden second Act-3 boss, chest contents and Dead Adventurer's
unsearched reward order. Current map/boss, chest size, public event options,
shop/reward offers, selector targets and completed picks remain fixed.

This covers transform streams (card/misc/Neow), random event effects, Library,
Pandora's Box and other random relic effects, chest/dig rewards, Courier
restocks, room generation and post-combat rewards. Semantic identity remains
the chosen operation/target, never its sampled outcome. Only the fresh semantic
action is executed live, using the live game's own RNG.

The live advisor sets `stopAtMapCheckpoint` when question-room probabilities or
seen-relic history are unqualified. Qualified histories allow downstream
MAP choices and use normal native chance updates; root hidden-counter sampling
never reinitializes a downstream room's inherited probabilities. Live imports
remove currently visible shop, combat-reward and boss-relic offers from the
reconstructed relic pools.
The advisor supplies the ordinary fixed `potionKeepValue=4` to the CTM;
`OocGameContextModel` uses the same neutral value if a custom host omits the
callback. This matches the native simulator default and the frozen model's
constant training feature. A zero value causes unsupported predictions from
this model.
Library uses its displayed heal amount and the existing MCTS reward-pity
prior for Read; its revealed cards become a qualified public OBTAIN selector.
Mushrooms and Mysterious Sphere use the same hidden reward prior; their native
leave effects now match vanilla (Parasite plus healing, and no reward,
respectively).
The default native win artifact is B0, `models/v_win_trees.txt`, except under
live OOC MCTS: with `STS_OOC_MCTS=1` and `STS_WIN_NET` unset the process win
model (native leaf, fallback rest/upgrade, `vStateWin`) is the public X2-B
`models/candidates/v_win_x2b_public_trees.txt` (§444 export, §449 A/B NOT_SHOWN
at equal CPU; ADR-0029). `STS_WIN_NET=1` restores B0 there.
The default-off X2-B candidate is `models/candidates/v_win_x2b_trees.txt`,
selected explicitly with `STS_WIN_NET` for simulator policies. Its adjacent
identity JSON binds the exact frozen UBJ, ordered features and exported bytes;
the existing `export_win_model.py` serializer exports all 445 trees. Production
C++ continues to use `CompactTreeNet`, with no XGBoost runtime dependency.
Explicit load failures stop startup instead of falling back to B0. The live
advisor has a separate `STS_LIVE_OOC_WIN_MODEL` dependency, and the legacy Python
server has a separate `VWIN` setting; the simulator override does not select
those models. This candidate is not a qualified gameplay default, and
terminal-pricing readiness remains false.

The rich fields `nextEliteId` and `nextFight0/1/2` encode encounter IDs from
native queues at their current offsets, with 0 only past the end. Full-run
policies use realized queues; OOC particles sample future queues while
preserving observed history. Live import reconstructs public encounter history
and samples unknown futures before MCTS evaluation. These values represent
hypothetical encounters, not visibility into the real game's hidden future.

The live v_win leaf evaluates the exact discrete mixture
`E[sigmoid(margin)]` over the native reachable ranges
(`potionChance=-40..60` in steps of 10 and `cardRarityFactor=-40..5`) rather
than applying the link to an expected margin or conditioning on 0/5. The
direct V4 scoring fails closed for real live captures because Java does not
expose an exact pity history. Live MCTS uses an equal public prior instead of a
fabricated midpoint; synthetic parity fixtures may explicitly mark an exact
pity reconstruction. Qualified public question-room outcomes reconstruct the
three room chances, which remain fixed when root particles sample reward pity.
Qualified legacy Juzu ambiguity is represented by a finite weighted distribution
over monster chances, conditioned on resolved outcomes, ownership, preceding
shops and Tiny Chest forcing under the fair uniform 24-bit room-roll prior.
This distribution is sampled once per root particle and retained downstream;
it is not a claim about the actual hidden PRNG state. Direct V4 and differential
tracing reject unresolved mixtures. The native room table uses vanilla's ordered
clipped fills, including last-cell overwrite when accumulated chances saturate.
Without that qualified history, room chances use the existing reachable-state
prior; this is a qualified
belief particle, not an exact joint posterior.

`OocGameContextModel::outcomeEquivalenceKey` (`outcomeEquivalenceParts`) exists
only with sampled futures; exact-replay providers return none. It omits exactly
what `sampleNoncombatFuture` re-draws before the next transition or leaf
continuation: the run seed, all RNG streams (counters only position a re-seeded
stream), pool order, unseen normal/elite queue entries, the A20 second Act-3
boss, hidden chest gold/tier and unsearched Dead Adventurer order. It keeps
everything copied forward: visible player, deck, relic, potion, map, screen and
path state, and hidden room/potion/rarity counters and pool membership. Live
root particles therefore do not merge when they draw different counter beliefs.
`STS_OOC_MCTS_MERGE_OUTCOMES=1` enables pooling. On two historical seeds at
2048 simulations it pooled about 35% of sampled successors, removed all
duplicate visible states from the trees (about 50% of decision nodes without
it), raised the maximum searched depth from 4 to 11-12, and cost about 30%
more MCTS CPU per simulation. The sibling states it still keeps apart differed
in visible state in all but a handful of event cases
([#384](https://github.com/pherrman1/sts_ai/issues/384)). A paired 128-seed
gameplay comparison (§367) was inconclusive: `floor + 10*won` difference
-0.25, 95% interval [-2.46, +1.96], wins 86 vs 83, about 13% more time per
run. Since ADR-0031 (§464, together with `STS_OOC_MCTS_TREE_RULES`) live OOC MCTS
merges by default; `STS_OOC_MCTS_MERGE_OUTCOMES=0` restores independent particles.

Live edges are never marked deterministic merely because their simulator copy
has fixed RNG. Progressive widening samples outcome particles normally, even
when a particular action has a deterministic public effect. Native leaf
features receive sampled hidden queues rather than the real future queue.
`OocAdapterOptions::sampleNoncombat=false` retains exact replay solely for the
offline/native parity seam; live startup always enables sampling and reports
`noncombatOutcomes=sampled`. There is no live known-RNG override.

The live root conditions that sampled support on public metric history before
search: current-act normal/elite consumption from completed combat floors,
acquired or lost relics, observed events, and paid shop removals. A `?` floor
that became a hallway combat is counted from `metricData.damage_taken`, not from
the retained map symbol. Private Java potion/card-rarity counters are not
copied. Historical relic offers that were seen and skipped are not present in
vanilla metrics; the live root therefore fails closed for treasure, Shovel,
Courier-restock, and random-relic event branches unless a complete
`seenRelics` history is supplied.
Live MAP roots use reconstructed public room chances when history is qualified,
and the explicit room-chance belief prior otherwise within its existing gate.
Non-root MAP states expand only when both question-room and relic-offer
histories qualify future transitions. Otherwise they remain hard checkpoint
leaves. Active Wing Boots supports ordinary Act 1–3 charged movement by default,
including hypothetical acquisition after the root: an existing next-row jump
costs one charge, ordinary edges cost none, and exhaustion becomes zero.
Native obtain/save entry reconstructs charges separately from frozen relic
features. The candidate set and transitions have native fixture coverage and
installed-JAR connectivity/counter checks; frozen-model quality and live charged
jump execution remain unqualified. Model features and weights are unchanged.

Default PUCT/widening remain `1.5`, `2`, `0.5`, with 512 simulations. Depth counts
searched semantic transitions (primitive transitions on MAP), excluding
policy-chain steps used only to project leaves. Sampling removes the concrete
future-stream leak; it is not a proof of an exact joint hidden-state posterior,
a belief-tree policy, or stronger gameplay quality. Remaining-pool membership
and historical counters are conditioned on native state; chance particles and
leaf policies are still the existing planner approximation. Live checkpoint
continuation preserves the simulator's reward-collection order and uses the
same V4 Q/margin contract for actions it can qualify. The standalone live
advisor cannot call `runFullRunOocPolicyStep(gc, agent, false, true)` directly
because that driver is coupled to simulator-global heuristic fallback
objects. The live continuation now shares the fixed free-reward prefix and
uses the simulator `ScumSearchAgent2` fallback when the V4 margin gate does
not fire; it never substitutes an ungated policy-logit argmax. Full
simulator/live checkpoint parity remains an explicit seam to extract before
claiming complete policy equivalence.

The following `STS_OOC_MCTS_` suffixes configure ON searches. Invalid finite
ranges/enums fail startup; OFF does not parse or apply search overrides. Native
V4 must load for every ON ablation. Boss mode removes `v_win` from leaf
evaluation only; the unchanged fallback policy chain may still load/use it.
Startup emits exact applied
settings in `[ooc-mcts-config]` JSON for artifact validation.

| Suffix | Default | Allowed setting / meaning |
|---|---|---|
| `SIMS` |512|positive integer, fixed completed draws per owned root|
| `PRIOR` |policy|`policy` or `uniform`; all candidates retained|
| `TEMPERATURE` |1|finite positive policy-logit temperature|
| `CPUCT` |1.5|finite nonnegative PUCT exploration multiplier|
| `WIDEN_K` |2|finite positive chance-particle width coefficient|
| `WIDEN_ALPHA` |0.5|finite exponent strictly between0 and1|
| `MAX_DEPTH` |512|integer1..512; fail-closed technical safety cap, not a value horizon|
| `ROOT_SELECTION` |visits|`visits` or `q`; Q selects only visited actions, ties by visits|
| `LEAF_VALUE` |native|`native`; `constant`0.5; or `boss`, the mean across all ten Act1--4 bosses of `0.75*survival + 0.25*survival*winningHpFraction` from the configured combat evaluator; or `bossrollout`, 1/0 for beating the next boss in a policy-chain + CTM rollout (research, ledger §391)|
| `LEAF_COMBATS` |0|0,1,3,5 additional surrogate combats before resolved checkpoint; at A0 with the ADR-0031/0032 defaults at §433 `combo` settings, 0 loses runs vs 3 (−12.5 pp [−21.9, −3.1], about 0.37x wall time, same tree depth; §472), also with 16384 instead of 4096 simulations at about matched CPU (−10.2 pp [−18.8, −1.6]; §475)|
| `LEAF_POLICY` |v4|`v4` (the policy chain), `uniform` among unique supported legal V4 candidates, or `prior` (research, §487: fixed tree rule steps, then the V4 policy-head argmax on every screen V4 encodes; `prior_leaf_steps` in the support trace); or `heart1` (research §493: the same fixed steps/candidate set, then loaded heart1/Arm C argmax if all candidates score, otherwise the unchanged chain; separate `heart1_leaf_steps`, `heart1_leaf_fallbacks`, `heart1_leaf_reasons`; requires `STS_OOC_HEART1`, independent of tree-prior selection)|
| `CPU_SECONDS` |0 (off)|Research per-decision thread-CPU allowance, finite 0..10 seconds. Starts before model/root preparation, checks after completed simulations, keeps at least one simulation; overshoot/cleanup is measured, not a hard deadline. Requires `EARLY_STOP=0`, gap stopping off, no forked leaf capture, per-rollout decision logs, or lock/checkpoint/reuse/graph/prior diagnostics. Real combat is excluded. `STS_RUN_PROFILE` records actual CPU, completed simulations and `early_stop_budget`; support trace counts `cpu_budget_stops`. Identical per-decision allowance does not imply equal CPU/run. Unset/zero leaves legacy search unchanged.|
| `ROLLOUT_SHOP` |greedy (ADR-0032)|`greedy` (single best purchase or leave per decision) or `planner` (first item of the best affordable bundle) for shops in leaf rollouts; wins not shown different, about 11% less wall time (§459)|
| `TREE_RULES` |1 (ADR-0031)|`1` applies the rollout chain's fixed steps (gold, unreviewed reward relics, potions with belt space, chests without Cursed Key, empty reward screens) in the tree and at the live root, and coalesces bottle/duplicate/bonfire targets per distinct card; with `MERGE_OUTCOMES=1` median search depth 2 → 4, wins not shown different (§464)|
| `MERGE_OUTCOMES` |1 (ADR-0031)|`0` or `1`; `1` pools sampled successors with equal search-equivalence keys (see below)|

Exact terminal0/1 overrides either leaf value. Uniform continuation retains V4
for unsupported/nonunique selectors; all transitions keep the same combat
support gate and native-simulation prohibition. Chance widening caps particles
with `ceil(k*N^alpha)`; action candidates are fully expanded, so this substrate
is not double progressive widening. Root-Q selection changes only the final
choice, not tree allocation. Leaf projection steps do not count toward tree
`MAX_DEPTH`. None of these knobs changes real Silver's budget or parameters.
Historical depth-8/16/32 parameter-screen receipts and the frozen
`tools/ooc_mcts_parameter_search.py` design describe the old value-bearing
horizon and must be replayed on their recorded source SHA, not this runtime.
The boss leaf is evaluated through one shared helper from both ordinary
`leafValue()` and the live resolved-checkpoint branch. It uses no planner or
gameplay RNG, never calls `v_win`, and fails the simulation/root closed if any
boss is outside combat-evaluator support. Each probe preserves the leaf's player
state but uses that encounter's canonical act and boss floor.

The existing trace also writes `.actions.jsonl` decision records with selected
canonical keys, planner IDs, screen/selector, compound status and execution or
fallback reason. Root-lock and checkpoint diagnostics include canonical keys.
Sampled hidden noncombat outcomes are covered by focused independence and
variation tests; this does not establish policy quality or full belief-model qualification.

Optional `STS_OOC_MCTS_TRACE` appends one CSV row per completed run, including
OFF runs when explicitly requested.

`STS_OOC_MCTS_PRIOR_TRACE=<jsonl path>` is a separate, strictly opt-in capture
of the authoritative current `OocGameContextModel` prior. It appends one
schema-versioned row per state on that state's first `legalActions()` prior
build, including root and hypothetical search states. Prior-covered
non-singleton rows retain the exact `buildTokStatePure` token values, each
distinct `strategicCands`/`tokEntity` source input and native source logit, the
ordered semantic candidates and their unchanged `priorSourceGroups`, grouped
candidate logits, raw planner weights and normalized diagnostic prior.
Singleton, uncovered and explicitly uniform rows stay compact and do not
force skipped policy inference. The trace checks source coverage, grouped-logit
reconstruction, candidate order, finite values and exact raw planner weights
before writing. It does not create a second search or change search RNG,
candidate ordering or returned priors; use a fresh path for each capture.

`STS_OOC_SIBLING_CAPTURE=<jsonl>` (default off, research) records sibling
leaves for learned-leaf tests: on every `STS_OOC_SIBLING_EVERY`-th searched
decision, each tree leaf up to `STS_OOC_SIBLING_MAX_DEPTH` below the root (at
most `STS_OOC_SIBLING_MAX_LEAVES` per root, in evaluation order) writes its
parent state id, action, the search's own leaf value and extras computed in a
forked child of the untouched pre-evaluation process: `_REPEATS` repeat leaf
rollouts and `_LONG` `LEAF_COMBATS=5` rollouts on fresh `seed_seq` streams
(policy thread state restored before each), X2-B at the leaf (`anchorValue`)
and, with `STS_OOC_HEART1`, heart1's value head and input record
(`heart1::leafAnnotation`). Siblings are leaves sharing a parent; the parent
link is kept only while capture is on. The forked child needs a single-threaded
process, as for the leaf replay probes. A20 smoke 74072220 (this capture with
1 repeat + 1 rollout5) left the decision trace and action log byte-identical
to capture off.
§489 (64 A20 seeds, 221k leaves): within parents, noise-corrected correlation
with the expected rollout3 return is 0.24 for one rollout3, 0.57 for X2-B at the
leaf and 0.30 for heart1's value head (0.56 on card-reward parents); a CPU
value net on 8-rollout means reached 0.56 vs X2-B 0.53 held out. No learned leaf
replaces rollout3. §490 (64 rollout3 labels per leaf, 64 further A20 seeds): the
same net with X2-B as an input reaches 0.645 vs X2-B 0.596 on validation seeds
at epoch 20. Those seeds also selected the checkpoint (best epoch 10; card-reward
parents 0.72 vs 0.19 there). No untouched TEST or gameplay result is established.

When sibling capture is enabled, each forked child also records a weight-free
heart1 public observation (`extra.record`, schema `heart1-public-record-v2`,
with current public battle-start encounter and masked public Match and Keep
state extensions),
separate X2-B CPU and total repeat-rollout CPU. Repeat-only metadata also records
`extra.rolloutPolicy`, `extra.heart1RolloutSteps` and `extra.heart1RolloutFallbacks`
from the forked label child. These are provenance/counters, never student inputs;
§494 requires them for its C-policy labels without rejecting legacy §491 data. `buildChoice`/`recordToJson`
need no released network weights. Unsupported records carry `recordError`.
This input is parity-unqualified for learned leaf deployment; limited hidden
field invariance fixtures do not prove live parity. The default-off path remains
unchanged. The [Heart-domain pilot](../../experiments/evidence/heart_rollout_distill_20261016/README.md)
completed its 64 sources and six fits with Arm C as tree prior and fixed V4
rollouts. The original post-latch evaluator crash remains `INVALID_TEST_EXECUTION`.
The [user-authorized §492 software-fault recovery](../../experiments/evidence/heart_rollout_distill_recovery_20261016/README.md)
reused the exact selected weights/data on the same already-opened holdout and
returned `NOT_SHOWN`: lower prediction MSE did not qualify decision quality or
compression speed. Original failure/latch remain preserved; no learned leaf or
default is promoted. The separate [§493 rollout-policy pilot](../../experiments/evidence/arm_c_rollout_20261016/README.md)
is also `NOT_SHOWN` for Heart kills; its explicit C rollout option remains off.

`STS_OOC_MCTS_LEAF_CAPTURE=<new.jsonl>` is a default-off, simulator-only
observational canary for #507. It requires enabled MCTS with the native CTM
rollout leaf and exclusively creates its output (an existing file is an error).
One header binds the running binary hash, source revision declaration, loaded
CTM identity, artifact hashes, effective OOC policy and environment. Source
revision is the declared/current checkout, not proof of binary provenance;
scientific collection must bind it to a clean, reviewed build externally.
Each completed root record includes up to eight already scheduled leaf calls,
at ordinals `1 + k * max(1, requestedSimulations/8)`, `k < 8`. Capture stops
after the first 64 root calls per process, including singleton/boundary calls.
Use one worker per capture file for reproducible prefix coverage. This sampling
is deliberately bounded, biased toward early roots, and not IID.

The target is the exact single stochastic rollout return; requested horizon,
successful combat resolutions, projection steps, terminal flag, endpoint
HP/maxHP/floor and final root abort status accompany it. Unsupported
evaluations retain a null target and the original support failure. All samples
from an aborted root are structurally invalid. Unsupported input reconstruction
retains an explicit input error, not a fake empty screen. Observer errors are
reported after search; file failures stop the run rather than triggering a
policy fallback. With capture unset, no input serialization or diagnostic RNG
copy occurs. Capture consumes no planner RNG and does not add continuations.

`candidate-public-leaf-v1` contains current visible resources, deck, bottle
flags, potion slots, relic IDs, forward-map summary, room history and supported
semantic screen contents/candidates (or current battle/terminal identity).
It omits private RNG, future queues, second boss, pity and relic counters.
It is a **candidate, incomplete observation**, marked
`publicParityQualified:false`; semantic candidate completeness does not prove
all visible event parameters or histories are represented. Simulator copied
hidden counters still affect the teacher. `structurallyValidSample` therefore
does not establish training suitability or #506 live parity. Seeds and full
planner RNG states are diagnostic fields outside `input`. No full callback
snapshot is stored: `replayability:unavailable`. Capture cannot establish
independent-repeat label variance or reproducible full-state replay. The
teacher remains `NOT_QUALIFIED` for this research milestone; no learned leaf,
training loop or default change is enabled.

The opt-in `one_combat oocselectivesilvergen 1 SEED PLAN.json OUT.jsonl`
audit, always launched through `tools/seed_guard.sh`, selects actual MAP choices
from a fixed native V4 source trajectory. Its ordinary calibrated CTM MCTS
baseline retains its selected action and highest-visit alternative. Forked
copies rescore only those two choices with CTM, native Silver and extra CTM
continuations, then use disjoint plain-native reference futures. This isolates
conditional decision utility; it does not establish whole-run wins, trainable
labels or a new runtime policy. The prospective [protocol](../../experiments/evidence/ooc_selective_silver_audit_20261014/PROTOCOL.md)
binds source selection, loaded models, streams, CPU matching, resource caps and
failure rules; its runner freezes a clean reviewed producer before seeds.

`oocselectivesilverspec` exports loaded CTM identity and effective source policy
without driving a game. `oocselectivesilverselftest` checks native sampler
isolation, RAW transfer, nonce consumption and the requested-three-combat
first-MAP checkpoint horizon, including mandatory fourth-combat chains and
earlier terminals. These audit modes are unavailable in the live advisor.
The default-empty thread-local `t_realRunContextObserver` observes the real
`runFullRunOOC` context after each path update and before policy execution.
The audit uses that address to exclude action/RAW callbacks from hypothetical
copies; child scopes clear it and restore all inherited observers afterward.
Ordinary runs leave this observer unset. Whole-source CPU accounting includes
startup/provenance hashing utilities, retained separately from evaluator forks. The audit-only nonce wrapper consumes
one outer RNG draw per combat and puts resolver draws in a private substream;
ordinary CTM baseline search retains its original sampler. The audit-only fork
callback transports a tagged success/error envelope. Standard messages are
bounded to1024 printable ASCII bytes; nonstandard exceptions have an explicit
category. The parent rejects error/malformed envelopes, retains failed-child
CPU, and invalidates the source. Ordinary replay-fork behavior is unchanged; serialization/transport errors
outside the callback envelope can still produce generic fork status.
Fixed evaluation-start records include candidate key/bits and future seed
before launch, so a failed branch remains identifiable. These records are
diagnostics, never deployable features or substitute replay snapshots.

`one_combat oocleafreplayprobe 1 SEED 20`, through `tools/seed_guard.sh`, is
a separate disposable Linux diagnostic for that collector. It requires a
native teacher with 4096 simulations, three continuation combats and a fresh
capture file. It selects only decision 0, sampled leaf ordinal 1025, and
requires a nonterminal MAP input; unavailable selection stops without a
replacement. At the original pre-evaluation boundary it verifies exactly one
OS thread and forks the complete model/state/callback/RNG context. The child
closes unrelated descriptors, evaluates once and exits through a bounded
pipe; after reaping it, the parent performs its scheduled evaluation. A child
timeout, support error or transport error invalidates the diagnostic.
Replay and stability probes reject unrelated trace/profile/probe outputs and
`STS_OOC_MCTS_DECISION_LOG` before starting a game.

The two evaluations must agree exactly on value, terminal status, endpoint,
combat/step counts and final planner RNG, with the source state/path unchanged.
The command writes one `replay_probe` result and stops before selecting or
executing a real root action. It does not emit a completed root or gameplay
result. This establishes only inherited in-memory repeatability for the
selected leaf; capture JSONL still has `replayability:unavailable`. It is not a
serialized replay format, an independent-future stability estimate or a
public-input qualification. Ordinary search never enables this diagnostic.

`one_combat oocleafstabilityprobe 1 87000000 20 PLAN.json` is a separate,
fixed-cohort conditional-target diagnostic, also guarded by `tools/seed_guard.sh`.
Its strict `ooc-leaf-stability-v1` plan contains exactly four selectors
`(decisionIndex, ordinal)`: `(0,1025)`, `(0,2049)`, `(1,1)`, `(1,513)`.
Each binds its complete expected candidate input and sixteen distinct uint64
RNG seeds; all 64 seeds must differ. Selection requires nonterminal MAP leaves
and the native A20 4096-simulation, three-combat V4 teacher. These are requested
simulations; normal visit-lock early stopping remains active.

Before each selected parent evaluation, one fresh fork evaluates the original
RNG as a control and sixteen more evaluate the supplied independent streams.
The parent then evaluates once with its unchanged original RNG. Exact control
parity, supported evaluations and unchanged source state/path are required.
Children share a cumulative 30 CPU-second allocation; before each child the
remaining budget must cover its existing 10 CPU-second cap. Child wall time is
capped at ten seconds and transport at 64 KiB. Scientific execution must also
use a frozen outer runner to enforce parent and whole-attempt limits.

Root 0's ordinary action may execute to reach root 1. After the complete root 1
search, the command stops before executing its action. It emits up to 68
provisional `stability_progress` records, two ordinary root records, and one
`stability_probe` summary. Only a complete valid cohort returns
`STABILITY_MEASURED`; any missing selection, unsupported result, parity failure,
abort or resource failure produces `INVALID` and retains partial records.
The external scientific analyzer must additionally verify complete historical
parent-root parity, producer/artifact custody and frozen stream derivation.

This measures the existing teacher's iterative future-redraw kernel conditional
on four complete inherited snapshots, including fixed hidden counters and pool
membership. It does not estimate a value conditioned only on the public input.
It supplies neither a portable snapshot nor CTM, public-input, training or
gameplay qualification. The command and its synthetic selftest are unavailable
in the live-advisor build and are inactive during ordinary search.

`STS_OOC_CPU_PROFILE=1` separately emits `[ooc-cpu-profile]` JSON to stderr at
the full-run trace boundary. Defaults remain off. Thread-local CPU scopes
record calls, inclusive CPU and exclusive CPU after subtracting timed children;
do not sum inclusive buckets. They cover real combat, MCTS, prior preparation
and predictions, V4 state/Q inference inside active scopes, native leaf value,
projection, successors, CTM preparation/resolution and metadata. Native
`leaf_value` is split into child buckets `leaf_features` (rich feature vector)
and `leaf_predict` (`v_win` tree inference); projection excludes timed child
networks. The native leaf reads the resolved state directly and makes no copy.
Counters reset at each report. `processCpuAtReportSec` is cumulative process CPU,
not per-seed CPU in a multi-seed process; use external process CPU timing for
one-seed invocations. These are attribution diagnostics, not production timings.
See the [two historical-seed profile](../../experiments/evidence/ooc_cpu_profile_2026-09-18/README.md)
for scope details, workload reconciliation and measured overhead limitations.

With the V4 prior and uniform leaf policy, `legalActions()` assigns a sole
candidate its exact normalized prior of 1.0 without running V4. For multiple
candidates, the policy head prepares its bias plus state dimensions 0–127 once
per immutable candidate set, then accumulates candidate dimensions 128–183 in
the original order. The Q head and candidate encoding are unchanged. Exact
parity and bounded performance evidence are recorded in the
[2026-09-24 V4-prior profile](../../experiments/evidence/ooc_v4_prior_uniform_leaf_optimization_2026-09-24/README.md).
The evidence supports this behavior-preserving optimization only; it does not
change the live OOC MCTS default or establish gameplay-quality improvement.

The CSV trace records
decision/ownership/fallback
counts, simulations, all sampled action transitions, combat-surrogate calls,
leaf evaluations, maximum search depth, search wall/thread CPU seconds and
ordinary real combat count. It also records imagined combat totals, unsupported
root support-abort counts and discarded completed simulations, total simulation
attempts, pending/battle/map leaf counts, projection steps,
particle creation/revisits, deterministic revisits and summed searched depth.
Appending to a trace with an incompatible header fails; use a fresh path when
changing trace schema. Historical readers default absent shortcut columns to zero.
Additional columns count trivial-root bypasses, locked-root stops, saved
simulations, immutable metadata/prior builds, prepared searched combat edges,
and searched combat-edge sampling attempts. `preparedCombats` includes supported
and unsupported preparations; `combatEdgeSamples` excludes combat samples made
only in leaf continuation. Native supported preparations run four encoders,
while unsupported preparations run none.
A `.support.jsonl` companion reconciles actual unsupported-combat reasons per
seed, plus separate `continuation_reasons`/`continuation_limit_aborts`. CSV
`continuationLimitAborts` counts unresolved continuation bounds, not combat calls.
`mctsSupportAborts=unsupportedCombats+continuationLimitAborts`, while
`imaginedCombats=combatSurrogateSamples+unsupportedCombats`.
OFF ownership/fallback/search counts are zero;
the decision count still covers actual nonbattle iterations. For ON, `simulations=configuredBudget*(owned-trivialRootBypasses)+discardedSimulations-savedSimulations` and
`simulationAttempts=simulations+mctsSupportAborts`. Search timing
includes adapter construction/destruction and unsupported-root checks, and
excludes execution of the selected live primitive. The `bestbench` `sec` field
is per-run steady-clock elapsed time, so wall time is the matching denominator.
Focused adapter tests cover search isolation, indexed determinism, exact live
primitive execution, pending real combat and unchanged fallback dispatch;
`ooc_mcts_live_startup` covers startup failure contracts. This opt-in seam does
not by itself qualify deployment or an exact hidden-information belief model.


## Semantic OOC decisions

`OocSemanticAction` is the opt-in OOC MCTS action representation above the primitive
`GameAction` interface (`include/sim/search/OocSemanticAction.h`,
`src/sim/search/OocSemanticAction.cpp`). It does not replace the deployed
policy chain, model inputs, trained artifacts, or fallback choices. The
architecture decision is [ADR-0013](../../../decisions/0013-ooc-semantic-decision-boundaries.md).

Effects and sources have explicit append-only numeric IDs. `UPGRADE_CARD=0`
and `CAMPFIRE_SMITH=0` remain stable. Keys retain schema version 1 and the
original literal Smith key, for example:

```text
ooc:v1:effect=0:source=0:card=25:misc=0:upgraded=0:bottle=-1:occurrence=0
```

Typed variant payloads distinguish deck cards, source-plus-card transactions,
selector picks, reward entities/groups, shop entities/prices, event options,
and boss relics. Deck identity includes card ID, misc, upgrade state, bottle
slot and equivalent-card occurrence. Generated selector candidates have their
own revealed-card identity. Reward card groups use a sorted visible card
multiset plus occurrence; rewards and shop entities resolve by semantic content
and occurrence, with Sapphire pairing and shop price represented where
relevant. Primitive bits and live UI indices are execution diagnostics, never
persisted semantic target identity.

`enumerateOocSemanticActions` returns `supported`, `complete`, `error` and
canonically ordered actions. Consumers must check completeness before treating
the result as the complete legal action space. MAP, BATTLE and INVALID screens
are unsupported; Match and Keep and malformed selector states cannot be
presented as complete supported decisions.

A combat that starts with a Smoke Bomb is outside the qualified CTM support.
Unless the sampler models the escape itself (an escape-capable artifact,
`modelsSmokeBombEscape()`; this includes the pathb-r2 default stack, so the
default skips the masking), the OOC model wraps its sampler
(`maskInitialSmokeBomb`) so such a combat is
valued as if the Smoke Bomb slot were empty (no escape) and the Smoke Bomb is
returned unused afterwards; a potion generated into that slot is dropped. This
Phase-0 approximation (#370) replaces the former whole-search abort. It is
pessimistic where an escape would help; against bosses only slot occupancy
differs, because escape is blocked there.

Match and Keep is enabled in the simulator (shrine selection, and therefore
event outcomes, changed for affected seeds). Each action is one click on one of
12 slots; slot state is `info.toSelectCards[i].deckIdx` (-1 unseen, 1 seen face
down, 2 face up this attempt, 0 matched), `info.eventData` counts the 5
attempts, and a matched pair is added to the deck. Its clicks are not searched:
`matchAndKeepPolicyStep` (`run_driver.cpp`) plays the fair fixed pattern in
`sim/search/MatchAndKeepPolicy` for real runs and for OOC MCTS continuations.
The pattern reads a slot's card only after that slot was flipped. Each seen
card is valued by the active primary guide as a lone card reward
(`oocHypotheticalCardTaken`): OOC MCTS when it is enabled, otherwise the
ordinary V4/one-ply chain; inside a search only the chain is used, so no search
nests inside another.

A compound may combine a source option with one target only when its complete
candidate set is public before the source click and that click reveals no new
information needed to choose. Smith, Peace Pipe and shop removal satisfy this
rule. Execution resolves the source against the current state, executes the
normal primitive, checks the expected selector, resolves the target again
against that live selector, and checks the final boundary. Shop removal also
validates the current service price; purchases remain one-step actions even
when a relic purchase opens a subsequent selector.

The event mapping describes selector metadata, not event effects. These are
single-target compounds; unlisted legal options remain `EVENT_CHOICE(event,
option)`. A mapped option also falls back to its source choice when its
transaction preconditions do not hold, including insufficient gold or Wing
Statue damage that would kill the player. Costs below are ascension below 15 / at least 15 when different.

| Event enum | Option | Target effect | Source cost |
|---|---:|---|---|
| `OMINOUS_FORGE` | 0 | Upgrade | None |
| `ANCIENT_WRITING` | 0 | Remove | None |
| `OLD_BEGGAR` | 0 | Remove | 75 gold |
| `DESIGNER_IN_SPIRE` | 0 | Upgrade | 40/50 gold |
| `DESIGNER_IN_SPIRE` | 2 | Remove | 60/75 gold |
| `DESIGNER_IN_SPIRE` | 4 | Remove, then automatic random upgrade | 90/110 gold |
| `DUPLICATOR` | 0 | Duplicate | None |
| `LIVING_WALL` | 0 / 1 / 2 | Remove / transform / upgrade | None |
| `PURIFIER` | 0 | Remove | None |
| `THE_CLERIC` | 1 | Remove | 50/75 gold |
| `TRANSMORGRIFIER` | 0 | Transform | None |
| `UPGRADE_SHRINE` | 0 | Upgrade | None |
| `WING_STATUE` | 0 | Remove | `damagePlayer(7)` |

Removal and ordinary transform candidates must be transformable and unbottled;
upgrade candidates must be upgradeable; Duplicator permits all deck cards.
The primitive implementation determines costs, automatic outcomes and RNG.
Designer option 4's random upgrade is an outcome, not target identity.
`NOTE_FOR_YOURSELF` remains a source choice because it obtains a card and
applies obtain effects before constructing the removal candidates.

Already-open selectors expose one currently legal semantic pick. Upgrade,
remove, transform, transform-upgrade, duplicate, obtain, bottle and Bonfire
Spirits sacrifice selectors are represented. Multi-select picks carry the
selector type and required/completed counts and re-enumerate live candidates
after each pick; no card-subset cross-product is constructed. Astrolabe is
first a boss-relic choice, then sequential transform-upgrade picks. Augmenter
option 1 is first an event choice, then two transform picks. Library Read is
first an event choice without generated IDs, then TAKE_CARD actions for the
revealed OBTAIN candidates. Wheel and other random event choices likewise
contain no predicted outcome.

For remove, upgrade, transform and transform-upgrade choices, the OOC MCTS
adapter searches one representative of each equivalent deck card. It retains
the first available physical occurrence and its full semantic key for live
execution. The shared semantic enumerator still exposes every occurrence.
This is search-level semantic/stochastic equivalence, not byte-for-byte
`GameContext` identity: removing different identical occurrences may leave a
different master-deck order. OOC futures are re-determinized and treat these
copies as effectively permutation-invariant.
Multi-card selectors re-enumerate after each pick, so a second copy remains
available on the next decision without searching equivalent branches now.
The live advisor checks that every omitted selector position matches the
retained choice's search equivalence key while preserving the full physical
action-set check before scoring.

Rewards enumerate all available card, relic, gold, potion and key actions
together, plus their distinct skip/leave choices. `CARD(group,5)` skips one
card group; with Singing Bowl it is represented as `SINGING_BOWL` because the
primitive grants the Bowl effect. `LEAVE_REWARDS` maps to reward `SKIP` and
leaves the entire screen. Taking or skipping the final card group immediately
invokes its saved continuation when every reward category is empty. A nested
continuation can restore parent rewards; it is never replaced with a direct
map transition. Other remaining rewards retain the explicit leave decision.
The emptiness check includes relics and both keys rather than relying on
`Rewards::getTotalCount()`, which omits relics.

For a sole card group with no other rewards and no Singing Bowl, MCTS groups
card-skip and leave into one search choice. Full semantic/wire identities and
primitive enumeration remain distinct. Root filtering precedes grouping, so
either captured alias can be the representative. The existing prior bridge
averages the source logits for that group, and the live MCTS validator accepts
an omitted alias only if it has the same search equivalence key and live action
as the retained primitive. Singing Bowl, multiple groups and mixed rewards keep
their distinct choices. Taking a Sapphire-paired relic consumes that key
choice, and taking Sapphire consumes its paired relic. Treasure `OPEN_CHEST`
ends at the revealed reward screen; it does not choose a generated reward.
In live runs with `STS_COLLECT_KEYS=0`, the adapter drops
`TAKE_KEY` and `TAKE_RUBY_KEY` candidates and their primitives from the V4
prior source set (`OocAdapterOptions::collectKeys`, set from `g_collectKeys` in
`configureLiveOocMcts`); offline fixtures and the live advisor keep keys. Before
this, live OOC MCTS could take the sapphire key and lose the chest relic (#347,
ledger §390). `runFullRunOOC` and `runFullRunOocPolicyStep` open every treasure
chest without Cursed Key before any policy runs (`openTreasureChestRuleStep`).
On any reward screen (elites, event elites, chests) they then take every
offered relic first (`takeRewardRelicRuleStep`), except Bottled Flame,
Lightning and Tornado, Dead Branch, Tungsten Rod, Unceasing Top and Juzu
Bracelet, which go to the ordinary decision (Philipp, 2026-10-07). The OOC MCTS
leaf value prices chest relics near zero (ledger §390 addendum).

`DISCARD_POTION` is append-only effect 29. It identifies a held potion and its
duplicate occurrence, and is offered only for a full belt with a visible refill
or affordable shop potion, without Sozu. It leaves the current screen/rewards
unchanged. Taking the refill is a separate subsequent decision. The frozen V4
primitive set omits discard, so MCTS uses the existing uniform-prior fallback
when this extends the candidate set. This is no model-schema migration.

Reward-origin relic acquisition preserves its remaining reward container and
leave continuation. A bottle or other selector returns to those rewards; a
relic opening child rewards returns after leaving the child screen. Nested
continuations restore each level. This primitive correction applies to all
callers (`GameAction.cpp::executeRewardsAction`). `Deck::removeSelected`
removes the sorted original indices from highest to lowest so descending or
permuted player picks remove the intended cards; transform outcomes still
follow the original player pick order. These are primitive correctness fixes;
semantic coverage itself introduces no default policy or model change.

Execution is transactional: copy `GameContext`, deep-copy its shared `Map`,
execute through legal primitive paths, and commit only after all required
boundaries pass. Other owned state is value-copied. Repository-generated
continuation callbacks use their context argument and value captures; the
transaction guarantee assumes those callbacks, not arbitrary externally
supplied closures mutating external objects. Semantic execution fails closed
when the global `g_onGameActionExecute` observer is active, because observable
callbacks cannot be rolled back with the copied game state. Failure leaves the caller's game
state unchanged and returns a useful error. Successful primitive bits are
returned separately for diagnostics.

## Semantic data/model adoption boundary

The maintained replacement workflow is
[OOC label pipeline preparation](../operations/ooc-label-pipeline.md), with
`tools/ooc_pipeline_contract.py` owning `ooc_pipeline_v1` provenance and the
whole-combat corpus validator. That validator expects the exact 1,766-feature
battle-start schema and post-battle diagnostics; it is not a semantic-action
row validator. Current K-budget manifests still bind primitive action bits and
semantic descriptions to replayed sibling sets. None of these schemas is
silently migrated by the semantic module. The separate semantic pilot uses
`ooc_semantic_manifest_v1` / `ooc_semantic_action_v1`, validated by
`tools/ooc_semantic_pipeline_contract.py`; its capture/replay and bounded
continuation contract is documented in the maintained OOC pipeline page.

The semantic pilot enumerates complete semantic sibling sets, persists the
canonical key and typed action payload, and executes each through the semantic
executor. Primitive diagnostics accompany a row but cannot replace semantic
identity. Decisions after Library/chest/relic reveals and each multi-select
pick remain separate live decision groups. Producer replay and validation bind
the semantic schema, exact candidate coverage, producer/executable identity
and frozen combat teacher before accepting rows. Stale, ambiguous, unsupported
or incomplete actions fail closed. The pilot does not establish a new model
encoder or authorize replacement-corpus scaling.

The future direct-Q and factorized trainers must consume the same semantic
rows, splits and representation, preserving the maintained source-decision
sibling/future grouping, teacher provenance, requested/actual budget schedule,
validity and quarantine contracts. Model encoders/exporters and any opt-in
runtime scorer must agree on those new action features; models trained on
primitive bits cannot be fed compound actions. Semantic corpus scaling,
training-schema migration, retraining and deployment remain separate work;
obsolete `strategicgen` paths are not expanded for coverage.

## Offline whole-Act encounter-distribution evaluator

`one_combat oocv4h1rollout` is an offline-only audit of the Act-1 floor-8,
decision-11 V4 card-reward state. `oocv4h1rolloutall` applies the same machinery
to every eligible OOC decision in the frozen source replay. Both modes replay the source state with the frozen
V4 stack, then evaluates each legal sibling over seeded
lightweight rollouts that uniformly sample legal OOC/map actions, skip rewards,
and pass through battles. It then runs the requested ordinary Silver root
budget for every observed action/rollout/encounter occurrence cell, preserving
the full battle-entry snapshot for that occurrence rather than collapsing
observations by encounter identity. The combat cells are
evaluated in parallel with OpenMP; set `OMP_NUM_THREADS` to choose the worker
count. The pass-through marks
each reached battle as a virtual victory with unchanged HP and calls the
canonical `BattleContext::exitBattle`; it is intentionally not a combat
surrogate and does not query `vStateWin` until the separate Silver cells.
Common rollout seeds are shared across sibling actions, and combat seeds are
shared across sibling actions for the same rollout/encounter occurrence. The
mode writes the requested CSV plus `.json` and `.report.txt` summaries and
has a deterministic `--self-test` canary. Run seed-driven commands through
`tools/seed_guard.sh`; this mode has one source seed, so its rollout count is
not mistaken for a multi-seed sweep by the seed-count validator.

`GameContext` owns run RNG streams, deck, relics, potions, map, resources,
act/floor, and the active `ScreenState`
(`include/game/GameContext.h::GameContext`). Legal strategic actions are packed
`search::GameAction` values enumerated and executed by
`GameAction::getAllActionsInState` and `GameAction::execute`
(`src/sim/search/GameAction.cpp`).

`ScumSearchAgent2::stepOutOfCombatPolicy` is the reusable heuristic policy.
The active whole-run research policy is the ordered branch chain in
`apps/one_combat/run_driver.cpp::runFullRunOOC`. Under current defaults it uses:

- native `models/v_rich_trees.txt` floor value for card and shop scoring;
- native `models/v_win_trees.txt` win value for rest/upgrade decisions;
- card skip threshold `-0.5`;
- heuristic map routing;
- value-based shop planning;
- heuristic/base handling for remaining screens unless an opt-in layer owns
  them.

The policy chain remains owned by `runFullRunOOC` in
`apps/one_combat/run_driver.{h,cpp}`; its live action-selection
implementations are isolated in `apps/one_combat/ooc_policy.{h,cpp}`. The
run-driver boundary uses concrete seams for retained training validity,
combat-budget/potion budgeting, VNet disconnect, and the retained
counterfactual draft hooks; it does not introduce a generic run context or
callback registry. The module owns checkpoint action ranking, the one-ply card/rest/upgrade/event/
shop/treasure/boss-relic/map gates, the server/native fallback family, map-route
search, and their candidate encodings. Model loading, `buildTokState`, model /
transport feature seams, diagnostics, counterfactual evaluators, and the
retained command/mode dispatch remain in `apps/one_combat.cpp`; the ordered
whole-run loop is in `apps/one_combat/run_driver.cpp`.

`apps/one_combat.cpp::main` enables native OOC unless `STS_NATIVE_OOC=0`.
Failure to load the floor model terminates startup; failure to load the default
win model does not. If the win model is unavailable, win-rest helpers fall back
to server requests even while native OOC is enabled. The generic
`[native OOC floor/win GBMs ON]` banner prints only when BOTH models loaded
(`g_floorNet.ok && g_winNet.ok`); otherwise the path-specific
`[native V_win NOT loaded; win-rest helpers will use v_server fallback]` line
prints instead. `WinNet::load` (`apps/one_combat.cpp`) also rejects
truncated/malformed compact tree files — stream-state checks after `ntrees` and
after every node read, `ntrees < 1` rejection, a per-tree final-node-must-be-a-
leaf check, and a trailing-data probe — instead of silently loading a partial
model with `ok=true` (silent constant predictions). With the tracked win
artifact present, `v_server.py` is not a default `bestbench` dependency; it
remains an optional localhost bridge for legacy and experimental endpoints.

Native shop planning also handles the follow-up card-removal screen in
process: `nativeShopPlan` and `vQueryRemove` score candidate removals with the
deployed floor model, so native `bestbench` does not connect to `v_server.py`
merely because a shop removal is selected. Server-backed modes retain their
existing queries. The socket bridge uses a bounded connect wait, so an
explicitly server-dependent path fails fast when localhost:5555 is unavailable
instead of stalling the whole run.

The native shop plan, card-reward pick and removal pick value their candidate
rows with `CompactTreeNet::predictDeltas` (verified 2026-10-12, §437, §442).
Each candidate is the decision's base rich vector with a few known features
changed (gold, deck size, the affected card and relic counts), passed as just
those columns. All candidates walk each tree together and separate only at
splits on those features, so every candidate reaches the same leaf and
accumulates the same margins in the same order as `predict()` on the full row.
Values and decisions are bitwise unchanged. The shop plan values all affordable
subsets in one call, keeps the first strict maximum in enumeration order, and
skips ranking removal targets when the removal costs more than the current
gold (no candidate could include it). `predictVariants` keeps the older
full-row interface (rows that differ outside the declared features take
`predict()`).

The native OOC research controls in this section and the campfire/removal/card
subsections below were verified on 2026-10-08.

The floor/win fallback rich vector includes realized `nextEliteId` and
`nextFight0..2`, and both tracked tree ensembles split on these fields. Combat
`STS_FAIR=1` does not remove this OOC information dependency. Since ADR-0028
(2026-10-12) `STS_OOC_PUBLIC_FUTURES=K` defaults to K = 8: it replaces only
those four fields at prediction time with K common, public-history-conditioned
native encounter samples and averages model predictions, including
probabilities after the logistic link. Explicit `0` restores the legacy hidden
inputs; Act 4, whose encounters are fixed, is scored without a mixture. OOC
MCTS playout steps that resample the queue first (`sampleNoncombat`, the live
setting) skip the mixture through `NativeOocResampledQueueScope`; their queue
is already a public sample. The same sampled futures score all alternatives within a
fallback decision; the source state/RNG is unchanged. Its planner seed excludes
the true run seed, RNG streams and queue-derived feature block. This is a
bounded repair for the controlled native V4 profile, not a qualification of
legacy server modes or hypothetical actions already executed with actual RNG.
The campaign keeps those routes disabled. Enabled settings (now including the
default) enter the counterfactual teacher policy specification; explicit `0`
preserves the legacy specification. Per-run public scorer counts prove actual branch use.

Shop bundle deck-size accounting is corrected by default since ADR-0030
(2026-10-13): relics add no cards and removal subtracts one card.
`STS_OOC_SHOP_DECK_SIZE_FIX=0` restores the legacy calculation, which counts
each purchased item as a card and omits removal's deck-size decrement.
Synthetic model regressions distinguish the defect from its playing-strength
effect. §463 (128 fresh paired seeds, §433 `combo` with planner rollout shops)
found no playing-strength difference: 110 vs 110 wins, 0.0 pp [−7.1, +7.8],
NOT_SHOWN; the default stays on.

`STS_OOC_MCTS_ROLLOUT_SHOP=greedy` (live default since ADR-0032; `planner` restores the bundle planner; verified 2026-10-14)
changes only shops reached inside OOC MCTS leaf rollouts: `nativeShopPlan`
scores leaving, each affordable item alone and the best removal alone, and
returns the single best one (leave on ties). The step executes it and the next
decision asks again, so purchases repeat greedily. It uses the same
deck-size accounting as the bundle planner (`STS_OOC_SHOP_DECK_SIZE_FIX`). Live shop roots and the MCTS-off chain keep the
bundle planner. §459 (128 fresh paired seeds, `combo`): wins 103 vs 101,
+1.6 pp [−5.5, +8.6], NOT_SHOWN, at about 11% less wall time per run. Philipp
made it the default on 2026-10-14 (ADR-0032).

OOC MCTS shop roots split the V4 removal prior across targets: every removal
target maps to the one `CARD_REMOVE` primitive and `legalActions` divides each
candidate weight by the number of candidates sharing its primitive, so removal
gets the mass V4 gave it, not that mass times the number of distinct cards
(same for smith targets; verified 2026-10-13).

A successfully loaded `STS_OOC_CHECKPOINT_NN=<path>` enables the compact native
checkpoint-distilled action network in acts 1–3 before ordinary policy layers
(`apps/ooc_checkpoint_net.h::OocCheckpointNet`;
`apps/one_combat/ooc_policy.cpp::oocActionNNPolicy`). A successfully loaded
`STS_OOC_STRATEGIC_NN=<path>` enables the Phase-5 one-ply card-reward gate.
Since round 3 (`OOC_STRAT_V3`), each legal reward action is scored **directly
with the Q(s,a) head** on the pre-decision state
(`OocStrategicNet::predictActionValue` — no clones or successor states), and
the best action is executed only when its margin over the runner-up reaches
`STS_OOC_STRATEGIC_MARGIN` (default 1.0); otherwise the heuristic card policy
runs. `STS_OOC_STRATEGIC_Q=0` restores the round-1/2 behaviour of scoring
copied successor states with the value head of the successor screen
(`predictValue(state, screen)`), the path used by the §70–§73 V2 gates. Since
round 4 (`§74`) the same Q gate also covers campfires and events via
`STS_OOC_STRATEGIC_REST=1` (`oocOnePlyRestPolicy` on REST_ROOM plus
`oocOnePlyUpgradeSelectPolicy` on the smith's CARD_SELECT/UPGRADE targets) and
`STS_OOC_STRATEGIC_EVENT=1` (`oocOnePlyEventPolicy` on EVENT_SCREEN options,
incl. Neow) — both default **off**, so the card-only configuration stays
reproducible. Round 6 (`§76`) added the remaining screens:
`STS_OOC_STRATEGIC_SHOP=1` (`oocOnePlyShopPolicy`), `STS_OOC_STRATEGIC_TREASURE=1`
(`oocOnePlyTreasurePolicy`), `STS_OOC_STRATEGIC_BOSS_RELIC=1`
(`oocOnePlyBossRelicPolicy`) — all default **off**. The Q
head is trained on Tier-B one-ply counterfactual labels (`strategicgen2`;
`apps/one_combat/strategic_gen.cpp::runStrategicGenSeed2`). No model is deployed by default:
the one-ply branches are opt-in only
(`apps/ooc_strategic_net.h::OocStrategicNet`;
`apps/one_combat/ooc_policy.cpp::oocOnePlyCardRewardPolicy`,
`oocOnePlyRestPolicy`, `oocOnePlyEventPolicy`, `oocOnePlyShopPolicy`,
`oocOnePlyTreasurePolicy`, `oocOnePlyBossRelicPolicy`). Historical gates: §70
pooled-head regression (−10.9pp at margin 1.0), §71 per-seed-neutral per-screen
heads, §73 Q-head result, §74 cards+rest+event +7.0pp (event gate the main
contributor; CIs span zero), §76 full coverage +18.8pp at margins 0.5/1.0
(statistically established; boss relic + treasure gates carry the bulk). Other
opt-in owners include
card, path, event, boss-relic/Neow, and all-OOC checkpoint evaluator flags
parsed in `apps/one_combat.cpp::main`.

Since round 5 (§75), a token-based state net (`OOC_STRAT_V4`) exists alongside
V3: `STS_OOC_STRATEGIC_TOK_NN=<path>` loads `apps/ooc_strategic_tok_net.h::OocStrategicTokNet`,
and the four one-ply gates score with it when loaded (V3 stays the fallback).
Its input is built by `apps/one_combat.cpp::buildTokState` (50 globals — 44
richRow scalars + 6 derived thresholds hpFrac/missingHp/freePotionSlot/
goldGeRemoval/canTakeEliteKey/bossNear — plus canonical counted deck tokens
`(id, upgraded, count)`, relic tokens `(id, counter)`, potion tokens
`(id, count)`; exact contract in
`docs/knowledge-base/architecture/ooc-strategic-v4.md`) and per-action
candidate entity embeddings via `tokEntity`. Training/export:
`train_strategic_tok.py` (rung-masked ablation trainer on the existing §73
CSV, no new datagen; the 482-col group-ordered fp16 state file is uploaded to
GPU VRAM once and rows are gathered on-device with a CPU-mmap fallback on OOM;
the 8 per-screen value/quantile heads run as full-batch GEMMs + gather instead
of masked per-head writes — math-identical, see the 2026-08-03 decision-log
entries; `STRAT_TOK_COMPILE=1` (default ON) wraps the net in `torch.compile`
(mode="default", Triton fusion, ~2x step; needs CPython dev headers;
`torch._dynamo.config.suppress_errors` falls back to eager if compilation
fails; `reduce-overhead` CUDA graphs are NOT usable — capture rejects the
masked entity `index_put_`)),
`export_strategic_tok.py`, `strategic_tok_net.py`.
Deployment parity hooks: exporter numpy-vs-PyTorch asserts and
`STS_OOC_STRATEGIC_TOK_CHECK=1` (first gated decision per run compares the 44
globals against `richFeatureVec`; zero mismatches across §75 benchmark runs).
§75 verdict: held-out ranking beats V3 (policy top-1 0.793 vs 0.784) and the
gate is directionally win-positive at margin 5.0 (+3.1pp, CIs span zero), but
V3's +7.0pp @ m1 is not beaten — **V3 remains the deployed default; the V4
net is opt-in**.

## Wave B regret gate (2026-08-04, opt-in)

`STS_OOC_STRATEGIC_GATE=regret` (default **off**) replaces the margin rule
`best − second ≥ m` with the regret rule **Qmax(s) − Q(a_heur) > ε** for every
one-ply gate (`oocOnePlyCardRewardPolicy` … `oocOnePlyBossRelicPolicy`,
`oocOnePlyMapPolicy`) and the M2 route search (`oocMapRouteSearchPolicy`);
`STS_OOC_STRATEGIC_GATE_EPS` (default 0.03) sets ε. `a_heur` is the action the
**live fallback chain of the screen** would take (the code path that would run
if the gate returned false — for SHOP that is `shopVPolicy` under bestbench,
for cards `serverCardRewardPolicy`, for rest/upgrade the win-rate layers, else
`ScumSearchAgent2::stepOutOfCombatPolicy`, with the `eventV`/`bossRelicV`/
`pathV` opt-in layers mirrored when their flags are set), identified by the
datagen-proven successor-fingerprint match
(`regretGateChoose` + `stratFingerprint`, one_combat.cpp:5844): the per-screen
heuristic runner (`regretHeurCardReward` / `regretHeurRest` /
`regretHeurUpgrade` / `regretHeurEvent` / `regretHeurShop` /
`regretHeurBossRelic` / `regretHeurMap`, SHOP gated on the run's `shopV` flag
via `t_shopV`) runs on a pre-state
copy (map detached, agent RNG stream copied so RNG-consuming heuristics
match), and the legal action whose successor fingerprint equals the
heuristic's is `a_heur`. When `Qmax − Q(a_heur) > ε` the Q-max action runs;
otherwise `a_heur` itself runs (the gate acts, so the heuristic layer is not
re-entered). When `a_heur` is unidentifiable — RNG-tied divergence, multi-step
heuristics, indistinguishable successors — the decision **falls back to the
margin rule** (`regretGateTail`). Implementation is shared via
`regretGateChoose`/`regretGateTail` (defined after `stratFingerprint`);
policies keep the margin path byte-identical when the flag is off (verified:
margin-mode runs reproduce the pre-change binary's results on the recorded
block). Q-consistency: `tools/analysis/check_vwin_calibration.py --ckpt <trainer.pt> <csv>`
adds a Wave-B truth-check mode that predicts the V5 Q_win head (torch
checkpoint, export parity-checked to ~1e-5 logit) on terminal
(`labelBootstrap==0`, chosen) rows instead of the win trees — run with the
pre- and post-recalibration checkpoints to test bootstrap-bias propagation
into the head.

## Map-DAG encoder (V6, 5.3.2 — falsified 2026-08-04, opt-in)

`OOC_STRAT_V6` artifacts (V5 layout + a reverse-DAG map encoder + a
zero-init 96→168 residual adapter) let `oocOnePlyMapPolicy` score MAP
candidates with downstream route information: node = room/row/col/burning
embeddings, bottom-up sweep rows 14→0 with mean+max child messages, readout
pools the chosen child's subtree (roots when `curMapNodeY < 0`). Training
inputs come from `one_combat mapbatch` tables joined per (seed, act) —
**no new datagen**: the tierb MAP-screen rows already carry per-child
counterfactual labels. Trainer knobs: 3rd CLI arg / `STRAT_MAPS_CSV`,
`STRAT_FREEZE_BASE=1` (train only `map_*`), `STRAT_INIT_PT` (seed the frozen
base from a prior checkpoint); exporter writes the V6 magic and numpy-parity
checks the graph path; C++ gains `OocStrategicNet::predictMapActionValue`
(+`mapnntest` parity mode). E1 (frozen `ooc_strategic_qwin_cal.pt` base,
40 epochs): val_pol_ce 0.426, q_top1_map 0.506 — offline gain, but the
recorded-block A/B is neutral-to-negative at every probability-point margin
(§100): the MAP gate itself costs ~12pp on the base at m0.01, and the encoder
does not close it. **Verdict: the encoder lever is falsified on the current
K=3 labels (§62 lesson repeats); V6 stays opt-in and undeployed; the
heuristic pathing and the map-gate-off stack remain the deployed config.**
Caution: a killed trainer can leave a byte-size-valid but corrupt
`_state.bin` — verify frozen-model metrics against the source run before
reusing it.

## Phase F search distillation (5.7.1 + 5.7.2 — falsified 2026-08-04, opt-in)

`STS_OOC_STRATEGIC_SCORE=policy` (default `q`) switches the one-ply gates'
score source from the Q_win head to the **policy head** for V5/V6 artifacts:
`oocStrategicScore` returns `sigmoid(predictPolicyLogit(state, bits, cats,
actionType, screen))` (the raw logit is sigmoided to the probability scale,
so the probability-point `STS_OOC_STRATEGIC_MARGIN` semantics apply
unchanged) instead of `predictActionValue`. The token-net path and the V6
map-encoder path are untouched; the margin/regret tail (`regretGateTail`) is
shared, and with the env unset the gates stay byte-identical (verified on the
recorded block). The trained policy head itself is produced with the
soft-target distillation loss in `train_strategic.py`: `STRAT_DIST_LAMBDA`
(0.5) + `STRAT_DIST_TAU` (1.0) blend the one-hot `chosen` CE with
`CE(softmax(labelWon/τ))` per decision group — `(1−λ)·CE(one-hot) +
λ·CE(softmax(labelWon/τ))` — plus a held-out `dist_top1` metric (policy
argmax vs label argmax). λ=0 reproduces the pre-change numbers exactly.
**Verdict (§104): falsified on the current K=3 labels** — the tie-dominated
`labelWon` caps the ranking signal (dist_top1 ≈ behavior's 38% agreement),
the distilled policy flattens the logits (margin 18.6 → ~1.2), and every
policy-score gate arm loses to the Q-gate and to the V3 reference on the
recorded block. Both knobs stay opt-in; `q` remains the default. The
label-noise follow-up (§105, 2026-08-05) is also null: futures=2 variance
reduction (matched 500-seed control; the labelWon value grid collapses from
55 to 126k distinct values) and the trainer-side denoising knobs
(`STRAT_DIST_MARGIN_EPS`, `STRAT_DIST_SPREAD_W`, `STRAT_DIST_TERM_W` —
defaults byte-parity with the §104 numbers) move neither `dist_top1` nor
`q_top1`; the one-ply label **ranking** itself is the transfer ceiling.
K=6 deep targets (5.7.1b) are not run for that reason (truncation is the
weak lever per the §105 L0 probe).

## Checkpoint-oracle live-policy levers (2026-08-05, opt-in, falsified)

`STS_ACT_FIGHT_PROBE_TERM_WIN=w` adds a terminal pricing term to the capped
all-OOC checkpoint objective (`apps/one_combat.cpp::checkpointedActFightUtility`):
on the final scored checkpoint, each option's post-fight branch state is
priced by the native win GBM (`g_winNet.predict(richFeatureVec(local))`,
P(win) units, scale-compatible with the HP-safety sigmoid) and blended by `w`.
`STS_ACT_FIGHT_PROBE_MARGIN=m` gates the oracle
(`apps/one_combat.cpp::actFightProbeAllOocPolicy`): it overrides a decision
only when `best − second ≥ m`, else control falls through to the ordinary
policy stack. Both default off; unset behavior is byte-identical. §111
falsifies both as a live full-run policy on the §107 stack: the ungated oracle
lost 0/13 paired seeds and the m=0.15 arm −4.50 (SE 2.33) at n=62; the
HP-safety/win argmax replaces the margin-gated one-ply Q stack on every gated
decision and is net-negative, and the terminal term cannot rescue it. The
oracle machinery remains an offline teacher/ranker tool (§66k/§66l/§67).

## Strategic model design (semi-Markov decomposition)

The stable design target for learned run-level decisions, adopted as the
Phase-5 architecture and recorded in `docs/knowledge-base/decisions/2026-08-02-semi-markov-strategic-model.md`:

- **Combat is a temporally extended transition.** The strategic model acts
  only at run-level decision points (card reward, map node, shop purchase,
  rest/upgrade/lift/toke/recall, event option, relic/potion pick); one
  transition may span an entire stochastic combat. This separation is the
  core design bet and the reason strategic learning never mixes per-tick
  combat actions into its policy.
- **Run value is the common language.** A single run-value model
  `V(s_t) = P(run victory | s_t)` prices HP, potions, gold, and upgrades
  consistently across all screens. Screen-specific decision heads share
  that value signal rather than learning independent resource pricing.
- **Action-conditioned scoring, not fixed output heads.** Legal actions are
  heterogeneous and variable in number; the policy encodes the run state
  once, encodes each legal candidate by type, and scores
  `logit(s,a) = f(z_state, z_action, z_state ⊙ z_action)` over the legal
  set. Skip is a real learned action token.
- **Hidden-information boundary.** The model may see only what the player
  sees: no future card rewards, no unknown shop contents, no exact future
  encounter identity beyond the known pool, no event outcomes before
  selection, no hidden RNG state. Strategic rollouts must sample unknown
  outcomes from conditional distributions, never copy the true future seed
  — the C++ tree search uses the game RNG state, so this boundary is an
  explicit implementation requirement, not an agent-API assumption
  (see `docs/knowledge-base/behavior/determinism-and-rng.md`).
- **Deployment contract: margin-gated overrides.** Greedy un-gated NN
  overrides of heuristic decisions are a recorded failure mode (§66m, §70,
  §73 margin 0). Any learned override path fires only when the candidate's
  margin over the runner-up reaches a threshold
  (`STS_OOC_STRATEGIC_MARGIN`), else the heuristic policy runs.
- **Representation roadmap.** The spec targets token-based run state
  (counted deck tokens, relic/potion entity tokens, map DAG graph
  encoding, decision-context encoding) and distributional value heads.
  The token-based state (V4, round 5) is delivered and recorded (§75):
  counted deck/relic/potion tokens through a single-head deck attention,
  thresholds, and candidate entity embeddings — trained on the existing
  Tier-B CSV with no new datagen. It improves held-out ranking (policy
  top-1 0.793 vs 0.784) but its deployed one-ply gate (+3.1pp @ m5) does
  not beat the V3 flat-vector net (+7.0pp @ m1), so V3 stays deployed and
  the V4 net is opt-in behind `STS_OOC_STRATEGIC_TOK_NN`. The current
  deployment still uses per-screen scalar value heads; distributional
  heads and the map DAG remain future work. The original roadmap is historical;
  current priorities are routed
  through `docs/knowledge-base/evaluation/current-research.md`.

## Important data flow

1. `GameAction::getAllActionsInState` defines legal actions for the active
   screen.
2. `runFullRunOOC` evaluates opt-in action networks/evaluators first, then map,
   rewards, shop, rest, boss-relic/Neow, and finally the base policy.
   `collectFreeOocReward` in `apps/one_combat/ooc_checkpoint_policy.cpp`
   takes potions through `search::potionRewardAction` (ADR-0039,
   `STS_POTION_REWARD_SWAP`, default on). With a free slot it takes the
   best-ranked reward potion. With full slots it discards the worst-ranked held
   potion when the best reward potion ranks strictly higher, then takes it
   (`potionKeepRank`, fitted on CTM fight data). Sozu keeps the legacy pickup.
   The effective teacher specification includes `potion_reward_swap: true`
   for unset/`1`; `=0` omits it and restores the legacy pickup, which took
   reward potion 0 only when
   `potionCount < potionCapacity` and never discarded. A Potion Belt reward
   collected earlier in that chain can add two slots before the potion
   decision. The audit below predates ADR-0039 and describes the legacy pickup.
   In the 3,069-fight `v_win` audit, 147 unmatched full-belt drops were classified
   by the adjacent-floor proxy (4.79%, or 4.8% of RAW fights); 199 more
   unmatched full-belt rows had unknown proxy status. If all 199 represent
   forfeited drops, the code-path upper count is 346/3,069 (11.27%, or 11.3%).
   This is a conditional upper bound, not an estimated rate: 17 unmatched
   space-available rows show that missing POST capture has other causes.
   Capacity was full in 95.3% of unmatched RAW rows versus 15.3% of matched
   rows; one matched full-belt drop was explained by a new Potion Belt. The
   belt was full in 759/3,069 RAW rows (24.7%); among 301 full-belt rows with
   classifiable adjacent-floor status, 148 (49.2%) had a potion drop. The legacy
   run policy took a potion only when capacity was available and had no discard
   or swap path. The exact cohort forfeiture rate is unknown. This historical
   full-run collection behavior is separate from the live semantic MCTS path,
   which now exposes `DISCARD_POTION` when a visible reward or affordable shop
   potion can refill a full belt (see the live inspector contract).
   `one_combat` enables `STS_COLLECT_KEYS` by default. `heartKeyAction` runs
   before learned choices and reward relic rules: take offered keys before
   their paired relic, take Ruby Recall at the first legal Act-3+ campfire,
   and on Act 3 choose the first legal map edge still reaching the visible
   burning elite while Emerald is missing. Earlier acts retain normal path
   decisions. The helper also runs in the fallback chain and tree-rule
   projection. Explicit `STS_COLLECT_KEYS=0` restores keys-off behavior.
   `runGoalVictory` keeps missing-key Act-3 clears out of Heart win labels;
   explicit benchmark horizons retain their separate Act-clear semantics.
   Sites: `apps/one_combat.cpp` REWARDS chains + `restWinPolicy`,
   `src/sim/search/ScumSearchAgent2.cpp::stepRewardsPolicy` and its REST_ROOM
   case, `src/sim/search/SimpleAgent.cpp::stepRestScreen`.
3. Native rich state is built numerically by `richFeatureVec(gc, path)`; the
   driver overload supplies the current thread-local path or an empty path.
   CSV remains in `richRow`/`vFeatCsv` for datasets and server compatibility.
   All row operands are integral; the parity regression compares every float
   byte against legacy CSV parsing, including integers beyond float precision.
   Current server-side
   raw layout has 1,017 values, including full card/relic/potion counts,
   forward-map summaries, and map position (`apps/one_combat.cpp::vFeatCsv`;
   `v_server.py::RAW`).
4. Native tree models map artifact feature names to raw rich indices through
   `richIdxMap` at load time and store final raw indices in split nodes.
   `CompactTreeNet` stores nodes contiguously with root offsets and an end
   sentinel; child indices remain relative to their tree. `load()` also builds
   a packed evaluation copy (8-byte nodes, each tree in preorder with the yes
   child next to its parent; §442) that `predict()` and `predictDeltas()` walk;
   trees filled in directly (tests) are walked from `nodes` unless `pack()` is
   called. Traversal, float thresholds/leaves, sequential double accumulation,
   and logistic/clamping operations retain their original order. Models score state or copied
   post-action states.
5. Counterfactual evaluators copy `GameContext`, apply a legal action, detach
   shared map state when mutation is possible, and simulate or predict future
   checkpoints.

```mermaid
flowchart LR
    START["runFullRunOOC evaluates layers in order"] --> OPT["Opt-in action networks / evaluators<br/>(OocCheckpointNet acts 1-3, one-ply Q gates)"]
    OPT -->|"no override qualifies"| MAP["Map"]
    MAP -->|"no override qualifies"| REW["Rewards"]
    REW -->|"no override qualifies"| SHOP["Shop"]
    SHOP -->|"no override qualifies"| REST["Rest"]
    REST -->|"no override qualifies"| BOSS["Boss-relic / Neow"]
    BOSS -->|"no override qualifies"| BASE["Base policy (fallback)<br/>ScumSearchAgent2::stepOutOfCombatPolicy"]
    GATE["Margin gate: learned override fires only if margin >= STS_OOC_STRATEGIC_MARGIN (default 1.0), else fall through to the next layer / base policy"] -.-> OPT
```

## Invariants and assumptions

- `GameAction` is distinct from combat `Action` and acts on `GameContext`.
- Native/server feature ordering must match the `vFeatCsv` producer.
- Counterfactual map mutation requires a detached `Map` because
  `GameContext::map` is a `std::shared_ptr<Map>`.
- Candidate policy validity requires evidence that the intended model loaded
  and actually owned the relevant branch.
- The default operating configuration keeps floor value for card/shop and win
  value for rest;
  unified V_win card/shop attempts are recorded regressions, not an invariant
  of future designs (`EXPERIMENTS.md` entries 49–50).

## Known limitations

- The strategic policy is an ordered integration function, not one composable
  policy object. Adding an earlier branch can silently bypass later behavior.
- `bestBench`'s `BEST stack` banner is emitted from parsed flags and load
  messages (skip threshold, rest/win layer, shop-V, path mode, native OOC,
  searcher, threads, model paths) but still omits some experimental layers; it
  is not a complete provenance record.
- The generic native-OOC startup message does not prove `g_winNet` loaded; a
  missing win tree can silently reintroduce server calls on win-rest screens.
- `v_server.py` documents the implemented 1,017-value `RAW` layout and links
  `apps/one_combat.cpp::vFeatCsv` as the schema owner.
- `OocCheckpointNet::load` and `OocStrategicNet::load` validate header/dims and
  every payload read; truncated files fail load (issue 08, closed).
- `runtrace` is not a wrapper around `runFullRunOOC`: it prints a diagnostic
  header, skips server-only draft logging when no server is reachable, but still
  omits some fallthrough policy layers and its event/treasure scores are
  diagnostic (`apps/one_combat/run_trace.cpp::runTraceRun`, `tr_logDraft`).
- Model-driven pathing with the old forward-map-blind win model was a recorded
  regression; heuristic pathing remains the operating baseline.
- Python cannot issue card-by-card combat actions.
- The fast predicted checkpoint evaluator compounds approximate transition
  error and is not in the default policy; historical results are in
  `EXPERIMENTS.md` §66j.
- `STS_OOC_STRATEGIC_TRACE=<csv>` is the deployment-aligned gate trace;
  `tools/analyze_strategic_trace.py` consumes it strictly and reports
  per-screen fire rates, margins, and outcome summaries. The outcome split is
  decision-level because final run outcomes repeat on each decision row.

## Open questions

- Which policy layers should move out of `one_combat.cpp` into a stable owner?
- How should action-conditioned card/shop/path targets replace observational
  state-value counterfactuals?
- Should native model formats include checksums and complete payload-read
  validation?

## Relevant code

- `include/game/GameContext.h::GameContext`, `ScreenState`
- `src/game/GameContext.cpp::transitionToMapNode`, `enterBattle`, `afterBattle`
- `include/sim/search/GameAction.h::GameAction`
- `src/sim/search/GameAction.cpp::getAllActionsInState`, `execute`
- `src/sim/search/ScumSearchAgent2.cpp::stepOutOfCombatPolicy`
- `apps/one_combat/run_driver.cpp::runFullRunOOC`,
  `apps/one_combat.cpp::vFeatCsv`, `richIdxMap`, `main`,
  `oocOnePlyCardRewardPolicy`, `runStrategicGenSeed`, `runStrategicGenSeed2`,
  `strategicGen2`, `buildTokState`, `tokEntity`
- `apps/ooc_checkpoint_net.h::OocCheckpointNet`
- `apps/ooc_strategic_net.h::OocStrategicNet`
- `apps/ooc_strategic_tok_net.h::OocStrategicTokNet` (V4 token net, opt-in)
- `train_strategic.py`, `export_strategic.py`, `v_server.py::H.handle`, `RAW`
- `train_strategic_tok.py`, `export_strategic_tok.py`, `strategic_tok_net.py`
- `docs/knowledge-base/architecture/ooc-strategic-v4.md` — V4 token-state contract
- `docs/knowledge-base/evaluation/current-research.md` — current research routing
- `docs/knowledge-base/decisions/2026-08-02-semi-markov-strategic-model.md`
- `bindings/slaythespire.cpp::PYBIND11_MODULE`


### Real-run floor and decision profile

Set `STS_RUN_PROFILE=/path/to/fresh.jsonl` for default-off observational
profiling in `runFullRunOOC`. An empty/unset path creates no output and performs
no floor clock reads or branching-histogram updates. Rows are serialized across
workers and write failures are explicit. This does not enable OOC MCTS, change
its budgets/model/RNG, or force full-budget execution. Unlike the older
`STS_OOC_MCTS_CHECKPOINT_TRACE` shadow diagnostic, it records checkpoints inside
the existing search with no second search. It preserves singleton bypasses and
all configured early stopping. If both diagnostics are explicitly enabled,
the older shadow still runs and its extra work is included in floor totals.

A floor interval starts when the real driver first observes `(act, floor)` and
ends when it first observes the next pair, or when the run stops/aborts. All
screens on the same floor share one row. Map-choice/entry work is charged to
the floor being left. Metadata names the floor being measured, including room,
coordinates and all observed combat encounters. Outcomes distinguish advancing,
death, victory, requested act-stop victory and abort. Fallbacks/support aborts
are separate counts, not floor outcomes. Exceptions emit a partial floor row
with the error; completed-component counters on that row do not account for
unfinished work and must not be treated as a complete profile.

Floor rows report wall and thread CPU time, real-combat lifecycle time,
combat decisions/simulations, and differences of the existing run-level OOC
search/transition/particle/leaf/CTM counters. Real-combat timing includes state
conversion and backend overhead, not just Silver tree search. OOC time includes
search preparation and result construction. Component times are nested inside
floor totals; do not add totals and components. I/O and profile overhead can
remain in floor totals, so this is not an isolated speed benchmark. Final floor
emission and post-run reporting are outside the sum of floor intervals.

Each actual OOC search records root actions (prior, visits, mean Q), selected
semantic key, execution/fallback status, configured/completed simulations,
exact expanded-node legal-action histogram, sampling work and depth. The
histogram counts each expansion, including repeated sampled decision states;
terminal/semantic boundary states do not expand and are excluded. Histograms
sum to the existing coarse expansion census. Singleton roots have zero
expansions/simulations. Root checkpoints at 128/256/512/1024/2048/4096 appear
only when reached. A support-aborted search retains partial expansion and
checkpoint evidence but has no final action statistics.

`python3 tools/analyze_run_profile.py PROFILE.jsonl --output SUMMARY.json`
validates floor/decision counts, execution/fallback/abort statuses, and search
work. Floor records explicitly count `unprofiled_disabled` calls and
`unprofiled_observer` early returns: neither emits a search row, and only the
latter contributes to fallbacks. Older schema-1 records default these counters
to zero; an old profile with such unrecorded early returns cannot be certified
and is rejected. Partial abort floors remain unqualified. The analyzer reports
exact branching shares, slow
floors by wall/CPU, room mean/median cost, top-5/top-10 CPU share, and root
stability cross-tabs. It derives visit/Q gaps, prior entropy and a strict visit
winner lock using `leader_visits - runner_up_visits > remaining_budget`.
That mathematical visit lock is not a guarantee against later support failure.

`b_stable_observed` is the earliest recorded checkpoint after which the winner
never changes through the **observed** final search. `b_stable_full_budget` is
null for early-stopped, singleton, boundary or aborted searches. Full-budget
cross-tabs use only uncensored searches and can be selection-biased. Neither
statistic qualifies an adaptive stopping policy on independent future searches.

### Optional Ruby Recall under keys off

`STS_COLLECT_KEYS=0` alone does not remove Ruby Recall from the V4 campfire
candidate set or the random fallback. `GameAction::getAllRestActions` uses the
simulator's `keysEnabled` and owned-key state; the fallback at intermediate HP
can sample Recall even when the run policy does not seek Act 4. This is a
reproduced policy eligibility defect, not an engine rule change.

Since ADR-0034 the filter is on by default (`STS_OOC_SKIP_OPTIONAL_RECALL`
unset or `1`; `0` restores the legacy eligibility). It applies one shared filter to
V4 REST candidates before scoring and to `ScumSearchAgent2::stepRandom`.
When keys are off and another legal action exists, it removes only Recall,
keeping the remaining action order. This can change the V4 margin and gate
ownership as well as the fallback's uniform action distribution. With the
flag `0`, legacy choices and RNG progression are unchanged. Enabled
sampling uses the existing single uniform-distribution invocation on the
filtered set; its underlying engine consumption may change with the bound.

If Recall is the sole legal action (for example, Coffee Dripper plus Fusion
Hammer without another campfire action), it remains available. The repair
does not fabricate an illegal Skip or alter simulator mechanics. The frozen
native V4 research profile uses MCTS off and REST_WIN off; this filter is not
a promise that every alternative policy stack enforces identical eligibility.
The enabled flag is bound into the effective OOC teacher specification.

### Full-health REST research candidate

`STS_OOC_SKIP_FULL_HP_REST=1` is a separate default-off policy experiment.
In an unresolved campfire at positive full HP, with Dream Catcher absent and
both REST and SMITH legal and present in the candidate set, it removes only
REST. Other actions retain their order. The filter follows optional Recall
filtering in the V4 gate and random fallback; the direct low-HP heuristic also
honors it when maximum HP itself is below 15. Damaged players, Dream Catcher,
unavailable upgrades and forced-action cases preserve their existing choices.
The enabled policy flag is serialized into the teacher specification.

This does not establish that upgrading always helps. Upgrades can change
exhaust behavior (for example, Limit Break), draw timing or downstream policy
choices. The candidate needs independent whole-run evaluation. Ancient Tea Set
and Eternal Feather apply on campfire entry; Regal Pillow's extra healing is
clamped at full HP. These facts explain the eligibility predicate, without
turning a local no-healing observation into a claim of trajectory dominance.

### Default fallback card-removal ordering

The fallback REMOVE selector ranks ascending
`Expert::getObtainWeight(cardId)` by default. Unset and
`STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT=1` select that corrected ordering;
explicit `0` restores the legacy highest-acquisition-weight-first rule.
Bonfire's distinct reward objective and every other selection type retain
their existing ordering. Native model-based shop removal is a separate
upstream policy. Living Wall and Peace Pipe can reach this fallback.

The selector still uses the simulator's legal menu indices and existing sort;
it adds no upgrade-aware values, curse priority or tie-breaking rule. Basic
cards and some specialized cards share weight zero, while upgrades retain
their base card weight. This is a policy-ranking correction, not an engine
defect or a dominance argument. The effective teacher specification includes
`remove_low_obtain_weight: true` for unset/`1`; explicit `0` omits it and
restores the legacy identity. Malformed values fail during startup. The user
authorized this default change after the frozen §395 confirmation; its
measured gain remains specific to that experiment's profile.

### Card reward ranking research candidate

`STS_OOC_CARD_WIN_RANK=1` preserves the public8 floor model's take-versus-skip
decision at each reached fallback reward state. When that decision is take,
it ranks the offered cards by the loaded logistic win model using the same
public8 scenarios and post-link averaging. It introduces no win-probability
skip threshold. The normal V4 margin gate retains ownership of its decisions;
the change is restricted to the native card reward fallback invocation.

Startup requires loaded native floor/logistic-win models, public8, finite
floor skip threshold, margin gating, MCTS off and conflicting card policies
off. The enabled helper rejects nonfinite returned base values or marginals.
The enabled flag enters teacher identity. Optional
`STS_OOC_CARD_WIN_RANK_TRACE=1` records existing predictions and semantic card
actions without additional evaluations or RNG draws.

This differs from legacy `STS_CARD_WIN`, whose native feature-edit path bypasses
the public scenario wrapper. That old flag must not be enabled in the controlled
fair campaign. Neither path models every acquisition effect: offered upgrades,
eggs and other card-acquisition relics remain existing feature approximations.
The historical broad win-head comparison (§24) did not confirm a gain; a binary
win target alone does not establish better current-policy action rankings.
Per-root take/skip preservation does not imply equal skip counts after
trajectories diverge. Default-off and other decision families are unchanged.

### heart1 policy adapter (opt-in)

Last verified: 2026-10-15 for distilled-student weights (network size and map trim from the file) and §488, reward-potion
swaps (ADR-0039), the Neow curse fix (ADR-0038), the OOC MCTS prior hook and the AVX forward pass; 2026-10-14 for the
native port and its parity harness.

`STS_OOC_HEART1=<weights.bin>` makes the real run driver (`runFullRunOOC`) take
every out-of-combat decision it can encode with silverbot's released `heart1.pt`
policy (daniel-ziegler/sts_lightspeed @84ab3ea, MIT). Combat stays on our
default Silver. Unset, nothing is loaded and the run is unchanged; the flag
enters the effective OOC policy identity with the weights' SHA-256. With live
OOC MCTS it is allowed only as the tree prior (below); then real decisions stay
with the search and its chain.

- Code: `apps/one_combat/heart1_policy.{h,cpp}`. It ports silverbot's
  `getNNRepresentation`, `construct_choice`, `take_free_rewards`, `collate_fn`,
  `map_dag_features` and the network forward pass (pre-norm transformer, dim
  256, 4 layers, 8 heads, ~6.0M parameters, value head). Padding tokens are
  dropped instead of key-masked, which leaves every valid output unchanged.
- Weights are not vendored. `tools/heart1/export_heart1_weights.py` converts
  `heart1.pt` (SHA-256 `deaba59d…`, checked) to the native file.
- Distilled students (heart1-distill, smaller silverbot `NN`s trained on heart1's
  logits) load through the same flag. The loader reads dim, hidden size and
  layer count from the tensors, the head count from an optional
  `meta.n_heads` tensor (default 8) and `meta.trim_map`; with trim the forward
  first drops the map rows below the current floor, as the student's training
  records did. The exporter writes the meta tensors with
  `--allow-other-checkpoint --n-heads N [--trim-map]`; heart1's own export has
  none and scores byte-identically to the fixed-size port. The load line
  names the size (`[heart1] loaded PATH (dim …, heads …, hidden …, layers …,
  trim_map …)`). Student C (dim 64, 2 layers, 4 heads, trim) matches
  silverbot's torch forward to 1.6e-5 on 3,000 tree-node records at about
  1.5 ms per call (heart1 about 31 ms).
- The tree prior and the leaf policy read only the choice logits, so they call
  `Net::forward(record, logitsOnly=true)`: the last block computes keys and
  values for every token but queries, attention output and feed-forward only
  for the choice tokens, and the value head is skipped. Every row is computed
  as before, so the logits are bit-identical; `one_combat heart1logitscheck
  <weights> <records.jsonl> [reps]` checks that and times both passes
  (student C: about 1.55 → 0.79 ms per call). `policyStep` keeps the full
  pass when `STS_OOC_HEART1_TRACE` records the value.
- Policy: temperature 0, the first maximum logit in token order. Gold, and
  relics on screens without a key reward, are taken before the decision, as
  silverbot does. A single offered choice is executed directly. Screens
  silverbot does not encode (Match and Keep, Bonfire Spirits, any unmapped
  event) fall back to the ordinary chain, where silverbot would call its own
  `pick_gameaction`.
- Diagnostics: `STS_OOC_HEART1_TRACE=<jsonl>` appends each scored decision's
  record and logits. `one_combat heart1score` scores records offline;
  `one_combat heart1replay` replays one seed's action bits for the harness.
- Parity: `tools/heart1/heart1_reference.py score` runs silverbot's own
  `collate_fn` and `NN` on our records; `tools/heart1/heart1_parity_seeds.py
  early` replays silverbot's engine's early-game decisions (Neow to the first
  combat) in our engine and compares records and logits. It compares each
  branch up to its first divergence, attributes that divergence to a known
  engine difference (below), and fails on any argmax disagreement or an
  unexplained divergence.
- Engine differences silverbot's policy sees through this adapter:
  - Before ADR-0038, Neow "transform two cards" also added a random curse in
    our engine; `STS_NEOW_TRANSFORM_CURSE_FIX=0` still does.
  - After a Neow card or potion pick, silverbot's engine keeps the reward
    screen open with only "proceed" left; ours goes straight to the map.
  - Our engine offers a reward potion only with a free slot; silverbot's always
    does. The ADR-0039 swap (`STS_POTION_REWARD_SWAP`) applies to our own
    policy, not to heart1. Singing Bowl is not enumerated by our
    `getAllActionsInState`, so the adapter adds it.
  - Keys are offered as in silverbot (Recall, emerald and sapphire rewards),
    so heart1 can collect them and enter Act 4 unless `STS_STOP_AFTER_ACT`
    stops the run.
- Cost: about 30 ms per scored early-game state on one core (Release, no
  `-march=native`), ~100 tokens per state. The projections run in an AVX
  kernel chosen at runtime (`__builtin_cpu_supports("avx")`); it keeps the
  reference loop's eight partial sums and reduction order with separate
  multiply and add (no FMA), so logits are bit-identical to the scalar path
  (`STS_OOC_HEART1_SCALAR=1` forces it). Map and path feature projections are
  batched over rows with the same per-element addition order. About 2.1x faster
  than the first port (`heart1score` on the adapter's 104 early records x10).
- OOC MCTS tree prior (research, default off): `STS_OOC_MCTS_PRIOR=heart1` with
  `STS_OOC_HEART1` set. At each node V4 would score (the unchanged
  `sourcePriorCovered` rule), heart1's logit replaces V4's for every source
  primitive (a primitive behind several tokens takes its best token; grouped
  candidates keep the mean), then the usual softmax at
  `STS_OOC_MCTS_TEMPERATURE`. Reward-screen primitives that silverbot's choice
  space lacks are mapped (`heart1::mapPriorLogits`): skipping one card reward
  (`CARD` idx2 5) takes silverbot's skip token (the bowl token with Singing
  Bowl), gold takes the node's best logit (silverbot always takes gold), and a
  potion discard on a full belt (rewards or shop) takes the node's lowest logit
  (silverbot's engine offers no discard). Where heart1 has no encoding for the
  screen or another source has no token (Match and Keep, Bonfire Spirits,
  unmapped events), the node keeps V4; the support trace counts
  `heart1_prior_nodes`, `heart1_prior_fallbacks` and `heart1_prior_reasons`
  (`scored:`, `mapped:` and `fallback:` by screen and kind). Before this
  mapping (run commit `ec19d1e`) every card-reward node kept V4. A node V4 does
  not cover (a full-belt shop or reward with discard sources, two or more card
  groups, a reward screen without a card reward, a non-upgrade selector) gets
  the uniform prior even with heart1. `STS_OOC_MCTS_PRIOR=heart1full`
  lets heart1 score such nodes too; if heart1 cannot score one, it stays
  uniform (no V4 fallback). It is the default whenever `STS_OOC_HEART1` is set
  and `STS_OOC_MCTS_PRIOR` is not (ADR-0042); `=heart1` restores the
  V4-gated heart1 prior and `=policy` the V4 prior. Card selects other than
  UPGRADE stay uniform under heart1full, because student C was distilled with
  no CARD_SELECT rows and picks the best card to remove. With
  `STS_OOC_MCTS_LEAF_POLICY=heart1`, heart1full also runs heart1 rollout steps
  on screens V4 cannot encode (same card-select exclusion); the remaining
  chain steps are counted as `chain:screenN` in `heart1_leaf_reasons`. A live
  root the search returns no action for (abort, CTM refusal) goes to
  `heart1::policyStep` before the V4 chain (decision trace `heart1_fallback`).
  `STS_OOC_MCTS_PRIOR_TRACE` refuses heart1 priors. §486 (A20, 64 paired seeds, `combo`): floors NOT_SHOWN, act-3 clears
  25 vs 10 (+23.4 pp [+9.4, +37.5]) at 8.7x CPU per run; no default change.
  heart1 inside rollouts was not implemented: a timing smoke
  (2026-10-15) put it at tens of core-hours per A0 run.
  §487 (A20, the same 64 seeds, `combo`, V4 tree prior): V4 policy-head
  argmax rollouts (`STS_OOC_MCTS_LEAF_POLICY=prior`) vs the chain: act-3
  clears 12 vs 10 NOT_SHOWN, floors −5.70 [−9.33, −2.17] WORSE (more act-2
  deaths); the chain stays.
  §488 (A20, the same 64 seeds, `combo`): student C as the tree prior
  (`STS_OOC_HEART1=studentc.bin`, `STS_OOC_MCTS_PRIOR=heart1`) vs V4: act-3
  clears 26 vs 10 (+25.0 pp [+10.9, +39.1]) IMPROVED, floors NOT_SHOWN, at
  619 vs 460 s per run (1.35x); about the §486 heart1 arm's 25 clears. Same
  seeds as §486, so not an independent replication; no default change.
