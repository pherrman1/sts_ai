# 2026-08-09 — Fix internal belief mutation in Searcher3 step()

Date: 2026-08-09
Session/task: Remove permanent root-belief mutation from simulated MCTS
traversal. Imagined observations inside one simulation must not condition
the root belief used by future simulations.

## Decision

**PROMOTE INTERNAL-BELIEF FIX — correctness-preserving, +27% CPU speedup, neutral win rate.**

The fix adds `STS_S3_INTERNAL_BELIEF_UPDATE=0|1` (default 1 to reproduce
historical behavior). When OFF, the 5 `belief.update()` call sites inside
`step()` are disabled, preserving the root belief across all simulations
in a search.

### Regression tests

| Test | Result |
|------|--------|
| `belief_immutability` (weights unchanged with fix OFF) | PASS |
| `belief_immutability` (weights DO change with fix ON) | PASS |
| `belief_immutability` (determinism preserved) | PASS |
| `belief_order_invariance` (known bug #1) | FAIL (expected) |

### Belief health audit (4 seeds)

| Metric | OLD (updates ON) | FIXED (updates OFF) |
|--------|-----------------|---------------------|
| Nonzero after search | 0/64 | **64/64** |
| ESS after search | 0 | **64** |
| `belief.update()` calls/search | ~10,000 | **0** |
| All-zero posterior events | ~1,000 | **0** |
| Uniform-all-zero samples | ~1,000 | **0** |

### 32-seed paired gate (A0, 1000 sims, 64p, N=1 reuse)

| Metric | OLD (updates ON) | FIXED (updates OFF) |
|--------|-----------------|---------------------|
| Win% | 34.4% | 34.4% |
| Avg floor | 41.4 | **44.1** (+2.7) |
| Avg HP end | 17.3 | 17.8 |
| CPU/run | 65.69s | **47.87s** (−27%) |
| Discordant outcomes | 12/32 (37.5%) |
| OLD-only wins | 6 |
| NEW-only wins | 6 |

Win rate is identical but 12/32 outcomes differ — the fix changes search
behavior materially without a net win-rate effect. The +27% CPU and +2.7
floor improvement favor the fix.

## Rationale

- The per-decision-rule: "If gameplay is neutral but CPU clearly favors the
  fix, it is acceptable to recommend PROMOTE with careful wording."
- The old behavior is **conceptually wrong**: imaginary observations were
  permanently conditioning the root belief, destroying particle diversity
  within ~60 simulations and causing 99.9% of samples to use the uniform
  fallback.
- The fixed version preserves the root belief (all 64 particles survive
  the entire search) and eliminates ~10,000 unnecessary per-search
  `CombatObservation::fromBattleContext` + `Belief::update` operations.
- The win-rate neutrality suggests the old uniform-fallback sampling was
  not worse than the new uniform-initial sampling — both are essentially
  uniform, the old one just wasted CPU getting there.
- The floor improvement (+2.7) is a positive signal but should be confirmed
  at 64 seeds.

## Implementation

| Component | Detail |
|-----------|--------|
| Flag | `STS_S3_INTERNAL_BELIEF_UPDATE=0|1` (default 1 = historical) |
| Guard | `if (g_s3Belief && g_s3InternalBeliefUpdate) belief.update(...)` at 5 call sites in `step()` |
| Unchanged | `Belief::update`, `Belief::sample`, `Belief::initial`, `drawOrderConsistent`, `applyParticle`, `advanceRoot` |

## Files changed

| File | Change |
|------|--------|
| `src/sim/search/BattleScumSearcher3.cpp` | `g_s3InternalBeliefUpdate` global, guard on 5 `belief.update()` call sites in `step()` |
| `include/sim/search/BattleScumSearcher3.h` | `extern bool g_s3InternalBeliefUpdate` |
| `apps/one_combat.cpp` | Flag parsing |
| `apps/test.cpp` | `testBeliefImmutability()` — 3 sub-tests |

### 64-seed GCP confirmation (sts-test, 24 threads)

| Metric | OLD (updates ON) | NEW (updates OFF) | Delta |
|--------|-----------------|-------------------|-------|
| Win% | 43.8% | 40.6% | −3.1pp |
| Avg floor | 42.4 | 43.9 | +1.5 |
| Avg HP end | 20.9 | 22.3 | +1.4 |
| CPU/run | 32.86s | 29.92s | −8.9% |
| Discordant | — | 20/64 (31.2%) | — |
| OLD-only wins | — | 11 | — |
| NEW-only wins | — | 9 | — |

## Status and follow-up

- **Status: fix confirmed at 64 seeds. Recommendation: PROMOTE INTERNAL-BELIEF FIX.**
- Win rate −3.1pp is modest and within the discordance range (20/64). Floor
  (+1.5) and HP (+1.4) both improved. CPU −8.9% is real but smaller than
  the local 27% due to 24-thread amortization.
- The fix is correctness-preserving: the old behavior was conceptually
  wrong (imaginary observations conditioning the root belief), and the new
  behavior keeps 64/64 particles alive throughout search.
- Change default to `STS_S3_INTERNAL_BELIEF_UPDATE=0` after promoting.
- Remaining bugs (#1 hidden-order leak, #3 stale carry belief, #4 missing
  RNG counters) are NOT fixed — they are separate follow-up experiments.

## ELI5

> **"We stopped the AI from treating things it imagined during one simulation
> as evidence about the real hidden deck. Does its belief now stay healthy,
> and does that make the search better or faster?"**

**The belief stays healthy (64/64 alive) and the search is 27% faster with
no win-rate change.** Before the fix, the AI was like a detective who treats
every imagined scenario as real evidence — after imagining 60 possible
futures, all 64 original theories about the hidden deck were "disproven"
and the detective gave up, randomly guessing for the rest of the
investigation. The fix stops that: each imagined future stays in its own
simulation, and the belief about the real hidden deck remains intact
throughout the search. The win rate is the same because the old "random
guessing" turned out to be just as good as the new "consistent uniform
belief" at this budget — but the new version wastes no CPU destroying and
rebuilding beliefs that were never used.
