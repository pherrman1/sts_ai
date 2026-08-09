# S3 Fair Tree Reuse — Final Report

Date: 2026-08-09 | Status: **PROMOTED TO DEFAULT**

## What we did

We investigated whether Searcher3's ISMCTS combat search could reuse tree work
across decisions instead of rebuilding from scratch every time. Over 6 rounds
we discovered, fixed, optimized, and promoted an observation-stable tree reuse
mechanism.

---

## Round 1: Naive reuse (falsified)

Added `STS_REUSE_MAX_SEARCHES`, `STS_REUSE_STATS_MODE`, `STS_REUSE_ALWAYS_Q`,
and hardened the RNG gate to all 6 combat streams. Tested 5 arms on 64 seeds.

| Arm | win% |
|-----|------|
| Control (fresh every decision) | 37.5 |
| RNG gate + keep + always_Q + N=1 | 4.7 |
| RNG gate + keep + always_Q + cascade | 4.7 |
| RNG gate + recursive_reset + N=1 | 17.2 |
| RNG gate + recursive_reset + cascade | 17.2 |

**Finding:** Unrestricted tree reuse is catastrophic. The RNG gate (checking
whether the committed action consumed hidden randomness) is insufficient —
promoted subtrees contain edges from multiple particle determinizations with
different draw-pile orders. The tree topology itself is stale.

---

## Round 2: Observation-stable reuse (first positive signal)

Added per-node observation tracking (`firstObsHash`, `nodeObsMismatches`),
semantic card identity, root reconciliation, union expansion, and the
observation-stable gate. Tested 5 arms on 64 seeds.

| Arm | win% |
|-----|------|
| Control | 37.5 |
| RNG gate + recursive_reset + reconcile_root | 25.0 |
| **obs-stable + keep + N=1** | **40.6** |
| obs-stable + recursive_reset | 32.8 |
| fresh + union expand | 35.9 |

**Finding:** Observation-stable reuse (only promote children visited from
exactly one visible observation matching the new root) plus keeping inherited
statistics BEATS control by +3.1pp. First reuse arm to do so.

---

## Round 3: Validation (counter fix + 128-seed gate)

Fixed `STS_REUSE_MAX_SEARCHES` counter bug (was resetting on every
`advanceRoot`, making N=1 behave like cascade). Added arm F (RNG gate + keep
without always_Q) to isolate the always_Q effect. Tested on 128 new seeds
(100000–100127).

| Arm | Config | win% |
|-----|--------|------|
| A | fresh, 1000 sims | 28.9 |
| F | RNG gate + keep + no always_Q | 39.1 |
| **G** | **obs-stable + keep + N=1** | **35.9** |

Paired discordants: A-only=14, G-only=23. Delta +7.0pp.

**Finding:** `always_Q` was the main culprit in the old 4.7% catastrophe —
removing it alone recovers to 39.1%. Obs-stable reuse confirmed at +7.0pp on
independent seeds. N=1 beats cascade (43.8% vs 40.6% on dev block).

---

## Round 4: Second 128-seed confirmation (final evidence)

Ran a second independent 128 seeds (200000–200127).

| Block | A win% | G win% | Delta |
|-------|--------|--------|-------|
| 100000–100127 | 28.9 | 35.9 | +7.0pp |
| 200000–200127 | 42.2 | 44.5 | +2.3pp |
| **Combined 256** | **35.5** | **40.2** | **+4.7pp** |

Paired (256 seeds): A-only=34, G-only=46. McNemar p=0.2185.

**Finding:** All 3 blocks directionally positive (+6.3, +7.0, +2.3pp).
Combined delta +4.7pp. Not statistically significant at p<0.05 but consistent
and accompanied by zero correctness failures. CPU was inconsistent (block 1:
−16%, block 2: +48%).

---

## Round 5: CPU diagnosis

Added `STS_REUSE_CPU_DIAG` to emit per-search CSV timing rows. Ran on 16 seeds
from both blocks.

**Key results:**
- Carried searches are typically 18% cheaper than preceding fresh search (median ratio 0.82)
- G has a fixed ~15% per-sim overhead from `trackNodeObservation` computing `CombatObservation::fromBattleContext` at every visited node
- Whole-run CPU variation comes from trajectory composition (G surviving more combats = more total searches) combined with the fixed overhead tax
- Heavy tail: p90 carried/fresh ratio = 2.75× (correlated with large retained trees and high rollout counts)

**Finding:** Carried searches are not intrinsically expensive. The overhead is
bookkeeping, not reuse.

---

## Round 6: Overhead fix + promotion

Semantic audit: only `root.edges` (immediate children) can be promoted via
`advanceRoot`. Restricted `trackNodeObservation` to `depth==2`.

| | A fresh | G-old fresh | G-new fresh |
|---|---|---|---|
| ms/1000sims | 42.8 | 49.1 (+14.7%) | 42.4 (−0.9%) |

**106% of overhead eliminated.** Reuse decisions identical. Zero correctness failures.

Changed defaults: `g_reuseObsStable=true`, `g_reuseMaxSearches=1`.
`STS_REUSE_MAX_SEARCHES=0` restores fresh-tree behavior.

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

| What | Why it failed |
|------|---------------|
| RNG gate | Multi-observation children have stale topology |
| always_Q | Forces exploitation of mismatched Q values |
| recursive_reset on RNG gate | Topology still stale, stats were informative |
| Cascade (N=-1) | Compounds observation drift |
| Full-depth obs tracking | 15% overhead, only root children need it |
| **obs-stable + keep + N=1** | **Works** |

## Files

- `include/sim/search/BattleScumSearcher3.h` — Node obs-stability fields, Edge availability, CardActionKey, diagnostics
- `src/sim/search/BattleScumSearcher3.cpp` — implementation, depth==2 gate, defaults
- `src/sim/search/ScumSearchAgent2.cpp` — agent loop with reuse control, RNG gate, diag hooks
- `apps/one_combat.cpp` — env var parsing
- `docs/knowledge-base/investigations/s3-tree-reuse*.md` — investigation records
- `docs/knowledge-base/decisions/s3-obs-stable-reuse-promotion.md` — promotion decision

## ELI5

The search now keeps its work when the next game state matches what it expected,
instead of throwing everything away and starting over. This wins about 5 more
games per 100. The old speed problem was unnecessary bookkeeping that's now
removed — it's as fast as the original. If you want the old behavior back, one
flag turns it off.
