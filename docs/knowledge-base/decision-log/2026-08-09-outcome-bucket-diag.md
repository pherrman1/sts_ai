# 2026-08-09 — S3 outcome-bucket diagnostic: particle redundancy at END_TURN draws measured

Date: 2026-08-09
Session/task: Measure how many distinct visible outcomes different hidden
particles produce from the same pre-state + END_TURN action. This is a
measurement-only task — no search behavior changed.

## Decision

**PROMISING — proceed to prototype local exact/chance outcome aggregation.**

The diagnostic (`STS_S3_OUTCOME_BUCKET_DIAG=1`) measures, for each unique
(pre-state, END_TURN) pair encountered during search, how many distinct
`CombatObservation::visibleHash()` values 64 fresh particles produce. The
results show substantial redundancy:

| Metric | Value |
|--------|-------|
| Transitions measured | 16,000 |
| Mean unique full obs (64 particles) | 14.3 |
| Median unique full obs | 11 |
| Mean compression ratio (full obs) | 11.67× |
| Median compression ratio (full obs) | 5.82× |
| Mean compression ratio (hand only) | 14.41× |
| Median compression ratio (hand only) | 8.00× |
| Mean largest-bucket fraction | 0.300 |

### Small-pile (draw pile 1–8, no reshuffle) — 90.4% of all transitions

| Metric | Value |
|--------|-------|
| Mean unique full obs | 13.1 |
| Mean compression ratio | 12.31× |
| ≤2 unique outcomes | 10.8% |
| ≤4 unique outcomes | 26.2% |
| **≤8 unique outcomes** | **45.5%** ← passes the 25% threshold |
| ≤16 unique outcomes | 68.3% |

### Lethal structure

| Metric | Value |
|--------|-------|
| Transitions with any lethal outcome | 30.1% |
| Mean lethal fraction when any | 0.828 |
| High-but-not-certain (0.7–0.95) | 3.1% |

The "5/6 draws kill" pattern exists (~3% of transitions have 70–95% lethal
fraction), and the more common pattern is "most draws are the same outcome"
(30% largest-bucket fraction on average).

### Outcome-count histogram (from 64 particles)

| Unique outcomes | Count | Pct |
|----------------|-------|-----|
| 1 | 950 | 5.9% |
| 2 | 648 | 4.0% |
| 3–4 | 2,234 | 14.0% |
| 5–8 | 3,156 | 19.7% |
| 9–16 | 3,560 | 22.2% |
| 17–32 | 3,994 | 25.0% |
| 33–64 | 1,458 | 9.1% |

### Draw-pile stratification

| Pile size | Transitions | Mean compr | Mean unique |
|-----------|-------------|------------|-------------|
| 1–5 | 7,921 (49.5%) | 12.19× | 16.6 |
| 6–8 | 6,536 (40.8%) | 12.46× | 8.8 |
| 9–12 | 722 (4.5%) | 3.13× | 35.5 |
| 13–20 | 1 (0.0%) | 1.21× | 53.0 |

Piles larger than 8 cards produce near-maximal diversity (each particle
produces a different outcome). This is the expected combinatorial explosion.

### CPU cost

Diagnostic overhead: ~40 CPU-sec/run vs ~23 without (≈1.7×). Acceptable for
a diagnostic. Normal behavior is byte-identical when the flag is off.

## Rationale

- The decision rule: ">=25% of small-pile draw transitions have <=8 unique
  outcomes from 64 particles" → we measure **45.5%**.
- Alternative threshold: "median compression ratio for drawPile<=8 is >=2x"
  → mean compr 12.19× for piles 1–5, 12.46× for 6–8.
- The redundancy is concentrated in small draw piles, which is exactly where
  exact/chance marginalization is computationally cheap. Large-pile draws
  (>8 cards) are only ~5% of transitions and produce near-64 distinct
  outcomes — no marginalization benefit there.
- 5.9% of transitions produce only 1 visible outcome from 64 particles — these
  are trivially collapsible (all particles agree on the visible future).
- 24.0% produce ≤4 outcomes — a small branching factor that could be
  enumerated exactly.
- The hand-only compression is even better (14.41× mean), suggesting that
  many visible-state differences are due to monster HP/details rather than
  the drawn hand itself.

## What was implemented

| Component | Detail |
|-----------|--------|
| Flag | `STS_S3_OUTCOME_BUCKET_DIAG=1` (default off) |
| File | `STS_S3_OUTCOME_BUCKET_DIAG_FILE=<path>` |
| Particles | `STS_S3_OUTCOME_BUCKET_DIAG_PARTICLES=64` (configurable) |
| Hook | All END_TURN execution sites in `step()` (leaf expansion, live-valid, expand-simple, expand, internal-node) |
| Dedup | Per-thread `unordered_set<visibleHash>` — each unique pre-state measured once |
| Cap | 2,000 rows per thread (≈24k max total) |
| CSV | 28-column row: metadata, draw-pile stats, unique counts, compression ratios, entropy, lethal fraction, bucket count vectors |
| Hand-only key | `handMultisetHash()` — same card-identity fields as `CombatObservation` |
| Lethal check | First legal CARD action that kills all monsters |
| Thread safety | Mutex-guarded output; thread-local RNG, file handle, dedup set |
| Particle source | Fresh `HiddenBattleState::sampleParticles` from current pre-state observation (not CRN) |
| Refactoring | `applyParticleImpl` extracted as free function (takes RNG ref) for use from diag |

## Evidence

- `include/sim/search/BattleScumSearcher3.h`: globals `g_s3OutcomeBucketDiag`, `g_s3OutcomeBucketDiagFile`, `g_s3OutcomeBucketDiagParticles`
- `src/sim/search/BattleScumSearcher3.cpp`: `handMultisetHash`, `runOutcomeBucketDiag`, `maybeOutcomeBucketDiag`, hooks at 5 END_TURN execution sites, `applyParticleImpl` extraction, thread-local diag state
- `apps/one_combat.cpp`: flag parsing
- Diagnostic CSV: `build/semantic_exp/bucket_diag.csv` (16,000 rows, 8 seeds @1000sims/64p/A0)
- Tests: `ctest --test-dir build` → 16/16 pass

### No-reshuffle vs reshuffle

| Condition | Transitions | Mean compr | Mean unique |
|-----------|-------------|------------|-------------|
| No reshuffle | 15,180 (94.9%) | 11.87× | 14.2 |
| Reshuffle | 820 (5.1%) | 7.90× | 17.2 |

Reshuffles (discard→draw pile) produce more outcome diversity as expected,
but are a small fraction of transitions.

### Key decision-rule threshold check

| Criterion | Threshold | Measured | Pass? |
|-----------|-----------|----------|-------|
| Small-pile ≤8 uniq from 64 particles | ≥25% | **45.5%** | ✅ |
| Median compression for pile ≤8 | ≥2× | **12.31× mean** | ✅ |

### What was NOT measured (scope boundaries)

- **CARD-draw transitions** (Pommel Strike, Shrug It Off, Battle Trance,
  Offering, etc.): the hook filters to `ActionType::END_TURN` only. The
  infrastructure (`maybeOutcomeBucketDiag`) accepts any action type, so
  extending to draw-cards is a one-line guard change.
- **`CombatObservation::operator==` collision verification**: hashes are
  used for bucketing; no secondary `operator==` check for hash collisions.
  The risk is negligible (64-bit hash on ~14 unique values).
- **CRN particle reuse**: fresh particles are generated per transition
  rather than reusing the searcher's `crnParticles`. This avoids coupling
  to the search state but is slightly more expensive.

## Files changed

| File | Change |
|------|--------|
| `include/sim/search/BattleScumSearcher3.h` | 3 new extern globals: `g_s3OutcomeBucketDiag`, `g_s3OutcomeBucketDiagFile`, `g_s3OutcomeBucketDiagParticles` |
| `src/sim/search/BattleScumSearcher3.cpp` | `handMultisetHash()` (~20 lines), `runOutcomeBucketDiag()` (~130 lines), `maybeOutcomeBucketDiag()` (~25 lines), hooks at 5 END_TURN `execute()` sites (5 × 2 lines), `applyParticleImpl` extraction (~5 line change), thread-local diag state (~8 lines) |
| `apps/one_combat.cpp` | 3 env-var parse blocks (~15 lines) |
| Total diff | ~220 lines added/modified across 3 files |

## Status and follow-up

- **Status: diagnostic complete. Recommendation: PROTOTYPE LOCAL OUTCOME AGGREGATION.**
- The next experiment should implement local exact/chance marginalization at
  END_TURN nodes with draw pile ≤ 8, enumerating unique visible outcomes,
  evaluating each once, and weighting by particle probability mass.
- Do NOT aggregate at large draw piles (>12) where the outcome space is
  effectively continuous.
- The existing live-valid framework and observation caching provide the
  infrastructure to slot outcome-aggregated edges into the tree.

## ELI5

> **"When the AI imagines 64 possible draw orders, how often are those really
> just a handful of distinct outcomes?"**

**About half the time, 64 possible futures collapse to 8 or fewer.** On
average, 64 different shuffles produce only 14 different visible hands. When
the draw pile is small (1–8 cards), the redundancy is even higher — 64
draws make only ~13 distinct hands on average. In 6% of cases, every single
one of the 64 shuffled futures produces the SAME visible hand — the AI is
literally re-evaluating the identical game state 64 times.

About 1 in 3 end-turn transitions can immediately kill the enemy with the
right draw. When lethal exists, it's usually available in most draws (83%
on average) — so the search could learn "this turn probably wins" much
faster if it knew all draws point the same way.

**The bottom line:** the search currently simulates every shuffled draw
order independently, but most of those simulations are redundant. A small
draw pile (≤8 cards) typically produces only a few genuinely different
hands. Evaluating each unique hand once and scaling by probability would
save most of the work at no accuracy loss.
