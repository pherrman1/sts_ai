# S3 Fair Tree Reuse — Final Report

Date: 2026-08-09 | Status: **ARCHIVED final investigation report; PROMOTED TO DEFAULT**

## What we did

We investigated whether Searcher3's ISMCTS combat search could reuse tree work
across decisions instead of rebuilding from scratch every time. Over 7 rounds
we discovered, fixed, optimized, and promoted an observation-stable tree reuse
mechanism.

---

## Round 1: Naive RNG-gated reuse (falsified)

Added `STS_REUSE_MAX_SEARCHES`, `STS_REUSE_STATS_MODE`, `STS_REUSE_ALWAYS_Q`,
and hardened the RNG gate to all 6 combat streams. Tested 5 arms on 64 seeds.

| Arm | win% |
|-----|------|
| Control (fresh every decision) | 37.5 |
| RNG gate + keep + always_Q + N=1 | 4.7 |
| RNG gate + keep + always_Q + cascade | 4.7 |
| RNG gate + recursive_reset + N=1 | 17.2 |
| RNG gate + recursive_reset + cascade | 17.2 |

**Finding:** Unrestricted tree reuse is catastrophic. At this stage the two
failure mechanisms (stale topology from multiple determinizations, and forced
Q exploitation via `always_Q`) were confounded. The RNG gate alone is
insufficient — RNG counters unchanged does not imply observation/topology
compatibility.

---

## Round 2: Observation-stable experiments (first positive signal, but counter was broken)

Added per-node observation tracking (`firstObsHash`, `nodeObsMismatches`),
semantic card identity, root reconciliation, union expansion, and the
observation-stable gate. Tested 5 arms on 64 seeds.

| Arm | win% |
|-----|------|
| Control | 37.5 |
| RNG gate + recursive_reset + reconcile_root | 25.0 |
| **obs-stable + keep, intended N=1** | **40.6** |
| obs-stable + recursive_reset, intended N=1 | 32.8 |
| fresh + union expand | 35.9 |

**Important:** The `STS_REUSE_MAX_SEARCHES` counter was broken at this stage —
`advanceRoot()` reset the reuse-search counter after every promotion, so
configured N=1 actually behaved like cascade. The 40.6% and 32.8% results
above were therefore effectively cascading reuse, not single-use. This was
discovered and fixed in Round 3.

**Finding:** This was the first positive reuse signal — observation-stable
reuse plus keeping inherited statistics beat control. But its reuse-depth
semantics were later found to be invalid because of the counter bug. The
measured 40.6% was achieved with effectively cascading reuse, which the
corrected experiments would later show is worse than true N=1.

---

## Round 3: Counter fix + corrected 64-seed validation gate

Fixed `STS_REUSE_MAX_SEARCHES` counter bug (was resetting on every
`advanceRoot`, making any N≥1 behave like cascade). Added arm F (RNG gate +
keep without always_Q) to isolate the always_Q effect. Tested arms A, F, G, H
on the original 64-seed development block (0–63).

| Arm | Config | win% |
|-----|--------|------|
| A | fresh, 1000 sims | 37.5 |
| F | RNG gate + keep + no always_Q + true N=1 | 39.1 |
| **G** | **obs-stable + keep + true N=1** | **43.8** |
| H | obs-stable + keep + true N=-1 cascade | 40.6 |

**Finding:** F recovering from 4.7% to 39.1% showed that `always_Q` was the
largest contributor to the catastrophic old result — keeping statistics
passively is fine, but forcing their exploitation before a winning line is
found destroys the search. True N=1 G (43.8%) beat cascade H (40.6%),
establishing G as the candidate for independent confirmation.

---

## Round 4: First independent 128-seed confirmation

New seed block: 100000–100127 (128 seeds). Only arms A and G.

| Arm | Config | win% |
|-----|--------|------|
| A | fresh, 1000 sims | 28.9 |
| G | obs-stable + keep + true N=1 | 35.9 |

Paired outcomes:
```
         G win  G loss
A win      23      14
A loss     23      68
```
A-only wins = 14, G-only wins = 23. Net = +9 wins, +7.0pp.

McNemar exact p = 0.1877. Bootstrap 95% CI: [−2.3pp, +16.4pp].
Floor delta: +2.02. HP delta: +1.80.
CPU: A = 38.10s/run, G = 31.91s/run.

---

## Round 5: Second independent 128-seed confirmation

New seed block: 200000–200127 (128 seeds). Only arms A and G.

| Arm | Config | win% |
|-----|--------|------|
| A | fresh, 1000 sims | 42.2 |
| G | obs-stable + keep + true N=1 | 44.5 |

Paired outcomes:
```
         G win  G loss
A win      34      20
A loss     23      51
```
A-only wins = 20, G-only wins = 23. Net = +3 wins, +2.3pp.

McNemar exact p = 0.7608. Bootstrap 95% CI: [−7.8pp, +12.5pp].
CPU: A = 31.08s/run, G = 46.01s/run.

The CPU increase in this block (+48%) motivated the CPU investigation in
Round 6.

---

### Combined independent confirmation (Rounds 4+5 only)

Seeds 100000–100127 and 200000–200127. Total n = 256.
Development seeds 0–63 are NOT included.

| | A (fresh) | G (obs-stable + keep + N=1) | Delta |
|---|---|---|---|
| Wins | 91 (35.5%) | 103 (40.2%) | +4.7pp |

Combined paired:
```
         G win  G loss
A win      57      34
A loss     46     119
```
A-only = 34, G-only = 46. Net = +12 discordant wins.

**McNemar exact p = 0.2185.** Bootstrap 95% CI: [−2.0pp, +11.7pp].
Floor delta: +1.08. HP delta: +0.49.

The independent evidence consistently favors G — both blocks are
directionally positive, discordants 46 vs 34 — but the win-rate superiority
is not statistically established at the conventional 5% level.

---

## Round 6: CPU diagnosis

Added `STS_REUSE_CPU_DIAG` to emit per-search CSV timing rows. Ran on 16 seeds
from both confirmation blocks.

**Key results:**
- Carried searches are typically 18% cheaper than their preceding fresh search
  (median within-lifecycle carried/fresh ratio = 0.82, 59% cheaper)
- G had a fixed ~15% per-sim overhead from `trackNodeObservation` computing
  `CombatObservation::fromBattleContext` at every visited tree node — this
  affected ALL G searches, not just carried ones
- Whole-run CPU variation came from trajectory composition (G surviving more
  combats = more total searches) combined with the fixed overhead tax
- Heavy tail: p90 carried/fresh ratio = 2.75× (correlated with large retained
  trees and high rollout counts)

**Finding:** Carried searches are not intrinsically expensive. The overhead
was bookkeeping, not reuse.

---

## Round 7: Depth==2 optimization + promotion

Semantic audit: only `root.edges` (immediate children, depth==2) can be
promoted via `advanceRoot`. Restricted `trackNodeObservation` to `depth==2`
for reuse correctness, keeping full-depth tracking only for the experimental
union-expand and diagnostic carry-diag flags.

Per-search cost on 16-seed diagnostic sample:

| | A fresh | G-old fresh | G-new fresh |
|---|---|---|---|
| ms/1000sims | 42.8 | 49.1 | 42.4 |

The measured ~14.7% fresh-search overhead was fully eliminated in the
diagnostic sample; optimized G was ~0.9% faster than baseline A in that
comparison. Reuse decisions identical to before optimization. Zero
correctness failures.

Changed defaults: `g_reuseObsStable=true`, `g_reuseMaxSearches=1`.
`STS_REUSE_MAX_SEARCHES=0` restores fresh-tree behavior.

---

## Promotion rationale

Promoted as an evidence-backed engineering default, not as a statistically
proven +4.7pp improvement.

Reasons:
- Both independent confirmation blocks favored reuse
- Combined point estimate = +4.7pp
- Paired discordants favor reuse 46 vs 34
- Zero observed correctness failures
- Observation-stable condition has a clear correctness rationale (only
  promote children visited from exactly one visible observation matching
  the new root)
- Measured observation-tracking overhead was removed
- Fresh-tree behavior remains available as a simple opt-out

---

## Final deployed configuration

| Parameter | Value |
|-----------|-------|
| obs-stable gate | ON |
| max carried searches | 1 |
| stats mode | keep |
| always_Q | OFF |
| reconcile root | OFF |
| union expand | OFF |
| cascade | OFF |

## Fresh-tree opt-out

```bash
STS_REUSE_MAX_SEARCHES=0 ./build/one_combat bestbench ...
```

## Lessons learned

| Mechanism | Conclusion |
|-----------|------------|
| RNG gate alone | Insufficient; RNG unchanged does not imply observation/topology compatibility |
| keep + always_Q | Catastrophic; forcing inherited Q exploitation too early was the largest identified failure |
| keep without always_Q | Recovered strongly (4.7% → 39.1%) |
| recursive_reset | Removes useful inherited statistics and still cannot repair stale topology |
| intended N=1 before counter fix | Actually cascaded; results cannot be interpreted as single-use |
| true cascade | Worse than true N=1 in corrected development gate |
| obs-stable + keep + true N=1 | Selected configuration |
| full-depth obs tracking | Semantically unnecessary for reuse and ~15% slower in diagnostic |
| depth==2 obs tracking | Equivalent reuse decisions with measured overhead removed |

## Files

- `include/sim/search/BattleScumSearcher3.h` — Node obs-stability fields, Edge availability, CardActionKey, diagnostics
- `src/sim/search/BattleScumSearcher3.cpp` — implementation, depth==2 gate, defaults
- `src/sim/search/ScumSearchAgent2.cpp` — agent loop with reuse control, RNG gate, diag hooks
- `apps/one_combat.cpp` — env var parsing
- `docs/archive/research/s3-reuse/s3-tree-reuse*.md` — investigation records
- `docs/knowledge-base/decisions/s3-obs-stable-reuse-promotion.md` — promotion decision

## ELI5

The search now keeps useful tree work when the next visible game state matches
what the search expected, instead of always starting from zero.

Across 256 new confirmation games, this version won about 4.7 percentage
points more often than fresh search, and both test blocks favored reuse.
That is a consistent positive signal, although the experiment was not large
enough to prove the improvement statistically.

The original speed penalty turned out to be unnecessary bookkeeping.
Restricting observation tracking to the only nodes that can actually be
reused removed that measured overhead without changing reuse decisions.

The optimized one-step reuse is now the default, while
`STS_REUSE_MAX_SEARCHES=0` restores fresh-tree behavior.
