# Prospective selective native Silver OOC-choice audit

Authorized by Philipp's request to execute the next step after §474. Bounded
pilot only: no training, production change or whole-run gameplay qualification.
Baseline source commit:37594e3bab761408cf255621be31dc72d75cc96e; implementation
is stacked on draft PR539, which is not merged by this request.

## Question and evidence inventory

Does selective gen6 E2k rescoring of two actual MAP choices improve a held-out
native requested-three-combat continuation return, relative to the calibrated CTM's
ordinary choice and to further CTM rescoring at the same measured CPU cost?
Competing explanations: native evaluation corrects CTM ranking bias; any gain
comes from more samples/compute; or stochastic noise/policy mismatch overwhelms
small differences. Primary objective is continuation decision utility, not HP
forecast error or full-run win probability.

§474 preserves32 sources/147 combat forecasts, but no complete pre-OOC-choice
snapshots. §461/462/471 preserve diagnostic inherited leaf replay and four
early correlated Neow variants, not a multi-source MAP choice panel. §432/445
short-branch labels use a different source/controller/model and cannot supply
this calibrated CTM/gen6 E paired comparison. Reuse native models and reviewed
fork/continuation primitives; collect only the new bounded panel below. CSV
features are never treated as replayable GameContext snapshots.

## Fixed source panel and selection

- Excluded canary97151001. Cohort97151010–97151017 inclusive,8 fresh sources.
- Ironclad A20, no keys, stop after Act3; source uses V4 OOC policy, MCTS off,
  original-future plain Silver10k, exact flat budgets, no singleton skipping.
- At most3 roots/source: the first MAP decision in each act after at least one
  real combat in that act, floor≥3, with at least2 distinct legal map actions.
  Select chronologically before knowing search support or either teacher's
  samples. No replacement for absence, unsupported roots or failures.
- At each selected complete inherited state/path, run one calibrated CTM
  MCTS4096 baseline, native public X2-B leaf,3 additional leaf combats,
  V4 prior/continuation, K4/alpha.75 widening, tree rules and outcome merging
  fixed on, early stop off, greedy rollout shop, public futures8.
- Retain its selected candidate and highest-visit distinct runner-up; ties by
  canonical action key. These same2 choices are used by every rescorer/reference.
  Failed/aborted baseline search invalidates the audit rather than falling back.
  Source actions remain the V4 policy's ordinary choices; audits cannot affect
  the source run. Absent later-act slots are recorded without substitution.

## Evaluation and randomness

Evaluate each candidate by copied root/path, independently redrawing future
state with the existing counterfactual kernel, executing that MAP primitive
without resolving combat, then calling the existing bounded native-value
continuation at state0. Horizon uses the existing first-MAP-checkpoint rule after at least3
requested combats from that primitive, or earlier terminal outcome. Mandatory
pending event/combat chains can add combats before the next MAP checkpoint;
actual combat/step counts are retained. Every arm uses the identical rule. This avoids sampleSuccessor's extra edge combat.
Use the identical fixed V4 continuation and X2-B endpoint value in every arm.
Returns are surrogate continuation values, not observed eventual run wins.

Four selectors: baseline CTM MCTS choice; CTM8 rescoring; gen6 E2k Silver8
rescoring; extra calibrated CTM rescoring with measured CPU matched to Silver8.
Each fixed rescorer uses8 paired futures per candidate. Ties retain baseline.
Additional CTM uses complete paired batches, stopping solely on CPU after at
least8 and at most4096 futures/candidate. Include feature/model and isolation
work; report child evaluator CPU, reaped child CPU and parent overhead separately.
Matched-control validity requires measured cost ratio0.90–1.10 and no sample
ceiling underfill; otherwise report compute matching unresolved, without
claiming matched-CPU benefit. This is extra CTM *continuation rescoring*, not
extra MCTS. No generic planner CPU-stop interface is introduced.

Independent reference:16 paired futures/candidate using plain10k native Silver,
prior off, same requested3-combat MAP-checkpoint horizon/endpoint value. Reference streams never select
candidates, retune budgets or affect choices. Selection and reference streams
are disjoint. They remain independent stochastic surrogate references, not
optimal-play or full-run labels.

For `(sourceSeed,act,phase,replicate)`, SHA256 the exact ASCII string
`ooc-selective-silver-v1|seed|act|phase|replicate`; first8 digest bytes as unsigned
big-endian uint64 seed. Freeze phase names/seed arrays before game execution.
Candidates share starting environment streams within a phase/replicate.
An audit-only combat wrapper consumes exactly one outer nonce, then uses private
substreams for CTM outcomes or native combat/planner randomness. Different
resolver draw counts cannot advance the common later-event stream. Different
choices can still visit different encounters and consume different future
sequences; common seeds do not imply identical trajectories. Native sampling
explicitly redraws gc.seed plus six battle-related carried streams, preserving
counters and the native four-stream initialization correlation. The old
research Silver resolver is left unchanged. Existing OOC noncombat sampling
already redraws gc.seed; no blanket old-OOC leakage claim is made.

Gen6 E hashca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228;
K8, weight400, root bonus on, flat2k with singleton skipping off and search
parameter overrides reset. Reference uses flat10k/prior off. Calibrated A20
manifest00bb4da6eb9b3117feb0579356436a96f7315ea28a8f3d1f29fd10b827c254ea;
FASTae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b;
STDe338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d.
Pin effective policy, native value/V4 models, actual loaded identities, source,
binary, all scripts/protocol and output paths after independent review, before
any game seed. Models existing on disk do not prove loading/use.

## Exact phase/batch and zero-root rules

Phase names are `search`, `rescore`, `matched`, `reference`. Baseline search
uses the `search` seed with replicate0. CTM8 and Silver8 share the exact
`rescore` seeds0..7; matched CTM starts with that identical eight-draw prefix
and must match its CTM8 values/endpoints exactly, then uses `matched` seeds
for indices8..4095. Reference uses only `reference` indices0..15. All prescribed
uint64 arrays are materialized/hash-checked before launch; no collisions
across phase/source/act allocations. Each batch is exactly one complete future
for each of the two candidates. Paired batches never stop halfway for a value
or cost reason. Each fixed CTM8/Silver8/reference evaluation is one isolated child for one
candidate/future; two such children complete one paired batch. The parent
aggregates their entire selector cost. Matched CTM runs its paired batches in
one child, restoring copied root/policy before each candidate evaluation. CPU stopping is measured inside
the matched child after each complete batch, using its own process user+system
CPU, to min(total observed Silver8 strategy CPU,50 seconds). The50s ceiling
reserves time inside the60s child cap for the last batch and serialization;
if it underfills the matched budget, no matched-CPU conclusion is allowed. At least8 pairs remain
mandatory. Record final-batch overshoot and actual measured costs afterward.

The gate numerator is matched-CTM strategy reaped-child user+system CPU plus
parent user+system CPU used in its fork, transport, validation and choice.
The denominator is the identically scoped Silver8 cost. Shared baseline search,
source generation, reference computation and final cost-record serialization
are excluded from both selectors and recorded separately. Thus CPU-stop
overhead may cause the actual gate to fail; never silently retune the deadline.
Before each child reserve its full pinned CPU allowance from remaining1200s;
settle against wait4 or cumulative RUSAGE_CHILDREN delta after successful reap,
including failed children. Whole-process accounting includes startup/provenance
utility children; retain their measured pre-game CPU in a separate header bucket
and reconcile it with all diagnostic forks. Parent CPU is checked independently. No concurrent
children inside one source process. Failed reservations/children invalidate.

A source with no eligible root is valid source accounting but makes this
prespecified eight-cluster comparison INVALID_OR_INSUFFICIENT; do not assign
zero utility, discard it, pool survivors or replace its seed. Absent later-act
slots remain permissible if every source has at least one root.

## Isolation, integrity and resource contract

Every diagnostic child inherits the same complete root/callback/cache context,
restores the pre-search policy bookkeeping, owns its copied states and fresh
streams, and cannot write inherited output files. Verify one OS thread before
fork, close inherited descriptors, redirect stdio, bounded pipe, wait4/reap,
_exit. Parent is the sole writer of exclusive flushed progress/data outputs.
Check copied source/path/policy bookkeeping are unchanged; duplicate baseline
same-state/search-seed controls must exactly match choice/root stats/work.
Check native smoke escapes, RAW victory transfer before regainControl and
healthy terminal detection; unsupported, stalled, nonfinite, malformed or
missing work is invalid, never a zero target or a dropped branch.

At most9 source attempts including canary;2 one-thread source workers.
Each diagnostic child≤60 CPU/90 wall seconds and2MiB transport. The canary
also uses one fork-isolated source-only control (no diagnostic roots), with
200 CPU/300 wall seconds, whose complete ordinary source action trace/end
summary must exactly match the audited parent trajectory. This is one extra
initialization of the same excluded seed, not another cohort source. Nine
top-level source attempts/unique seeds plus this one canary-only control are
permitted; its CPU is part of the same1200s child allocation. Parent≤200 CPU
seconds; all children≤1200 CPU seconds per source. Reserve each child's full pinned CPU allowance (60s normally,200s for the canary source control)
before dispatch and stop on exhausted reservation; whole-source wall cap1800 seconds. Aggregate
allocation12,600 CPU seconds. Outer runner must account reaped child CPU, kill
only its owned process group on failure and preserve receipts/latches. No retry,
cap increase, source/choice replacement, outcome-driven extension or partial-
cohort quality inference. Canary must pass before dispatching the fixed cohort.

## Analysis and decision rules

For each source average its selected roots; give sources equal weight. Primary:
held-out reference return of Silver8-selected choice minus baseline-selected
choice. Also report the CTM8 and matched-compute CTM selectors against baseline,
and Silver8 against those controls. All draws, selected actions, disagreement
counts, terminal/death/support states, endpoint HP/floor and cost are retained.
Use5000 paired source-cluster bootstrap resamples, analysis-only seed97151099,
nominal2.5/97.5 percentile intervals. No iid-root interval, post hoc subset,
winner selection or training/default qualification. Reference replicate
variation and small8-source sampling remain limitations.

Directional conditional improvement requires the primary interval entirely
above zero; otherwise improvement is NOT_SHOWN. A matched-CPU claim additionally
requires all cost-match gates and a positive Silver8−matchedCTM interval.
Main later-act interpretation requires≥4 Act2 slots and≥2 Act3 slots; unmet
coverage yields a limited-coverage reading without extension. Count absent
slots and all failures. Report both all-root primary effects and disagreement
counts; do not compute a favorable selected-disagreement efficacy gate.

Complete valid cohort verdict DECISION_AUDIT_MEASURED regardless of direction.
Any integrity/resource failure yields INVALID_OR_INSUFFICIENT and no complete
cohort quality claims. No outcome from this audit establishes actual run-win
improvement, all-action regret, public-input sufficiency (#506), compressible
leaf targets (#507), or permission to train/change defaults.

Knowledge impact: prospective experiment, maintained opt-in diagnostic interface,
then measured evidence/current research. No runtime default or model promotion.
