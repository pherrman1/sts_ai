# 2026-08-22 — Phase-1b Search-Age EARLY/LATE preregistration

## Decision

Run a new diagnostic experiment on baseline
`4a0b3772be7fa402049594816ee18ed5969c0154` to test whether posterior-supported
controlled draw-order sensitivity differs between EARLY leaves
`searchSimulation ∈ [100,300]` and LATE leaves
`searchSimulation ∈ [2800,3000]` from the same 3000-simulation Searcher3
search. This does not retroactively modify the valid Phase-1b §177
INCONCLUSIVE result.

The implementation captures lightweight eligible `frontierType=0` leaf
snapshots during the single actual Searcher3 search, selects 16
approximately evenly spaced eligible ordinals in each whole window at search
completion, and then runs the expensive posterior replay on those stored
snapshots while the same Searcher3 instance remains alive. `ageBin` records
the deterministic selected-leaf rank `0..15`; it is not a fixed simulation
sub-bin. Selection occurs only at `fightIdx=0` and `decIdx=0`. The run is
fixed at 3000 simulations, 64 particles, K=0, and R=4 controlled diagnostic
rollouts. Fewer than 16 eligible callbacks in a window remains invalid; there
is no backfill.

## Hypothesis and decision rule

H_age: mature Searcher3 search may change the visited leaf distribution and
therefore controlled draw-order sensitivity; the practical direction of
interest is LATE > EARLY. The analyzer reports existing controlled and
full-particle targets separately by stratum, paired seed-level contrasts, and
10,000 paired-seed bootstrap intervals. Descriptive depth, turn, draw-pile,
and compatible-support composition is explanatory only.

The external practical LATE reference gate is PASS only if controlled
fraction(range >5) >= 10%, seed-bootstrap lower 95% bound >5%, and equal-group
controlled mean range >=3. This is not a new formal §177 gate and does not
authorize particle-conditioned VNet training or gameplay promotion.

Validity requires zero source replay failures, invariant failures, replay
explosions, K=0 caps, structure/mass violations, complete 16/16 EARLY and
16/16 LATE bin coverage per seed, no duplicate seed×stratum×ageBin, valid age
windows, and fresh first-decision roots with `rootCarried=0`.

## Evidence and freeze point

The Searcher3 loop assigns a 1-based `searchSimulationOrdinal` immediately
before each `step()` in `BattleScumSearcher3::search()`; it resets for each
search invocation and is copied into `S3LeafDiagnostic`. The age mode is
opt-in and behavior-neutral, bypasses the legacy first-16 cap, and preserves
the existing semantic replay, deduplication, mass accounting, K=0, controlled
R=4, and secondary full-particle machinery. The lightweight capture callback
is read-only; expensive replay is deferred until search completion and does
not alter the completed Searcher3 search.

Scientific seeds are 0..15 only. Structural smoke uses separate seeds
100000..100007 at the full 3000-simulation budget. The scientific command is
run only after smoke and after this implementation/preregistration is frozen.
No 32-seed extension, VNet training, gameplay change, or merge to `main` is
part of this experiment.

## Bounded smoke outcome

The initial fixed-sub-bin implementation was smoke-tested at 8 seeds (`100000..100007`),
3000 simulations, 64 particles, K=0. It produced 176 source groups rather
than the required 256: EARLY coverage was 104/128 bins and LATE coverage was
72/128 bins. There were zero source replay failures, invariant failures,
replay explosions, structure violations, mass violations, and duplicate bins;
all selected groups were `fightIdx=0`, `decIdx=0`, `rootCarried=0`,
`reuseGeneration=0`, and `reuseSearchCount=-1`. The missing bins were genuine
absence of eligible frontierType-0 callbacks in those age bins, not tree reuse
contamination. The smoke is therefore implementation-invalid/incomplete and
has no scientific interpretation.

A matched 2-seed OFF-vs-age check (`100000..100001`, 3000 simulations) passed:
committed action fingerprints and run outcomes were identical. Scientific
seeds 0..15 were not run.

The initial fixed-sub-bin implementation and its incomplete smoke are
superseded by this whole-window deferred-probe design; their artifacts remain
preserved for provenance.
