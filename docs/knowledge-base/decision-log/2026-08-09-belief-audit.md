# 2026-08-09 — S3 belief/posterior correctness audit

Date: 2026-08-09
Session/task: Audit whether Searcher3 samples the correct hidden-state
distribution during fresh and carried-tree searches. Static code audit,
regression tests, and dynamic instrumentation.

## Decision

**MULTIPLE CORRECTNESS BUGS — FIX SEQUENTIALLY.**

Three independent issues were identified. The most severe is #2, which
renders the particle belief non-functional after the first few MCTS
simulations. All fixes should be tested behind flags before any deployment.

### Bug #1: HIDDEN-ORDER LEAK (confirmed by regression test)

`Belief::update` conditions on `drawPileContents` using positional
comparison (`drawOrderConsistent` checks `pile[i].getId() == rem[i].getId()`
positionally). Two `CombatObservation`s that are equal under the observation
contract (`operator==` returns true, `visibleHash()` identical) can produce
different belief posteriors because the internal vector ordering differs.

The regression test `belief_order_invariance` demonstrates this:
- Two observations with identical draw-pile multiset but different vector
  order produce different particle weight distributions.
- This means the belief is conditioning on information the player cannot
  observe (internal vector order of `CombatObservation::drawPileContents`).

**Severity**: Medium. The belief uses unobservable information, which could
introduce bias but may not be practically harmful if the ordering is stable.

### Bug #2: INTERNAL BELIEF MUTATION DESTROYS PARTICLE DIVERSITY (confirmed by dynamic audit)

`step()` calls `belief.update()` on the ROOT-LEVEL `BattleScumSearcher3::belief`
object at 5 call sites during simulated tree descent. This permanently
conditions the root belief on imagined observations from simulated
trajectories.

Dynamic audit results (4 seeds, fresh searches):

| Metric | Value |
|--------|-------|
| Initial nonzero particles | 64/64 |
| After search: nonzero | **0/64** |
| After search: ESS | **0.0** |
| `belief.update()` calls/search | ~10,000 |
| Particles zeroed/search | ~500,000 |
| All-zero posterior events | ~1,000 |
| Uniform-all-zero fallback samples | ~1,000 |
| Uniform-equal fallback samples | ~1 |

After the first ~60 simulations (60 × 5 updates ≈ conditions on 300 imagined
observations), ALL 64 particles are zero-weighted. Every subsequent
simulation samples uniformly from a dead belief.

**Severity: CRITICAL.** The particle belief is non-functional. The
`g_s3Belief=1` default is performing uniform random sampling for >99% of
simulations. This explains why `g_s3Belief=0` was measured as NEUTRAL or
BENEFICIAL in previous experiments (§106-107): the belief was never actually
conditioning the search.

### Bug #3: CARRIED TREE KEEPS STALE BELIEF (confirmed by code audit)

In the fair-S3 path, `advanceRoot()` preserves the promoted subtree and
statistics but does NOT update or rebuild the belief for the new root state.
The carried belief is the one from the previous search (already dead — see
Bug #2), plus the agent-level `belief.update()` in the non-fair path (line
438-439 in `ScumSearchAgent2.cpp`), which only fires in the non-fair path.
In the fair path, the belief is NEVER updated with the real observation.

**Severity**: Medium. In the fair path, a fresh searcher is built each
decision, so this only matters for the N=1 reuse case where the tree is
carried. Combined with Bug #2, the carried belief is already dead.

### Additional findings

- **`applyParticle` fallback rate**: 0% — the stored draw-pile order always
  matches exactly. No stale-particle shuffling occurs.
- **RNG counter reset**: `applyParticle()` resets all 6 RNG counters to 0
  instead of capturing actual counter values. `HiddenBattleState` stores
  only seeds, not counters. This means carried particles don't faithfully
  represent the post-action hidden state.

## Belief lifecycle diagram (actual current behavior)

```
constructor
    ↓
Belief::initial(bc, 64, rng)         ← fresh 64 particles, all weight=1
    ↓
prepareCRNParticles()                 ← separate CRN particles
    ↓
search(1000)                          ← loops step() × 1000
    ↓
step(): belief.sample(rng)            ← samples particle (uniform after ~60 steps)
    ↓
step(): belief.update(obs)            ← ✗ MUTATES ROOT BELIEF (5 sites × ~60 steps)
    ↓                                     after ~300 updates: all 64 zeroed
    ↓                                     remaining 940 sims: uniform dead belief
    ↓
[search completes: belief is dead]
    ↓
real action chosen from root edges
    ↓
advanceRoot(action, newState)         ← keeps tree, does NOT update belief
    ↓
carried search: belief is still dead
```

## Files changed

| File | Change |
|------|--------|
| `src/sim/search/BattleScumSearcher3.cpp` | `g_s3BeliefAudit` globals, `t_ba*` thread-local counters, instrumentation in `applyParticleImpl` |
| `src/sim/search/CombatObservation.cpp` | Added include; instrumentation in `Belief::update()` and `Belief::sample()` |
| `src/sim/search/ScumSearchAgent2.cpp` | Per-search belief audit output (nonzero, ESS, updates, zeroed, fallbacks) |
| `include/sim/search/BattleScumSearcher3.h` | `g_s3BeliefAudit`, 7 `extern thread_local` counters |
| `apps/one_combat.cpp` | Flag parsing for `STS_S3_BELIEF_AUDIT` |
| `apps/test.cpp` | `testBeliefOrderInvariance()` regression test (FAILS — confirms hidden-order leak) |

## Evidence

- Regression test: `./build/test belief_order_invariance` → FAIL (4 checks)
- Dynamic audit: `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF_AUDIT=1 bestbench 1000 4 0` → all searches show nonzero=0/64, ESS=0
- Regression test output confirms `drawOrderConsistent` compares positionally
- Code audit confirms 5 `belief.update()` call sites in `step()` and no belief rebuild in `advanceRoot()`

## Recommended fix sequence

1. **Fix #2 first** (internal belief mutation): Remove or guard the 5
   `belief.update()` calls in `step()`. The root belief should represent
   uncertainty at the REAL root, not be conditioned on imaginary
   trajectories. Flag: `STS_S3_INTERNAL_BELIEF_UPDATE=0` (default 0).
2. **Fix #1** (hidden-order leak): Change `drawOrderConsistent` to compare
   draw-pile contents as a multiset after removing cards that were actually
   observed to be drawn. Requires understanding which cards left the pile.
3. **Fix #3** (carried belief staleness): After `advanceRoot()`, rebuild
   belief from the new root state: `belief = Belief::initial(newRootState,
   maxParticles, rng)`. Flag: `STS_REUSE_FRESH_BELIEF=1`.

## Status and follow-up

- **Status: audit complete. Three bugs identified. Fix #2 is highest priority.**
- After fixing #2, re-measure the `g_s3Belief=0` vs `=1` paired gate. The
  existing §106-107 measurements (belief=0 beating belief=1 by +8.6pp) were
  measured against a non-functional belief — the comparison was effectively
  "uniform particles vs uniform particles with extra work."
- Only after #2 is fixed and the gate re-run should fixes #1 and #3 be
  applied and tested.

## ELI5

> **"After the AI makes a real move and keeps its old search tree, does it
> also update its guesses about the hidden deck/RNG correctly? Or is it
> keeping guesses from the old situation—or even learning from imaginary
> simulations as if they actually happened?"**

**It's worse than either of those.** The AI's guesses about the hidden deck
are being destroyed DURING the search itself. Every time it imagines a
possible future and sees what cards get revealed, it permanently updates its
belief about the real hidden deck — as if imagining something makes it real.
After about 60 imagined futures, all 64 guesses are proven "impossible" and
the AI gives up entirely, reverting to random guessing for the remaining 940
simulations.

The "belief" system that was supposed to track which hidden deck orders are
still possible is completely broken. Turning it off (which previous
experiments showed was better) was actually just avoiding the wasted work of
updating a belief that immediately destroys itself.
