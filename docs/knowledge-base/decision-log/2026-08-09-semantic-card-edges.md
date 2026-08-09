# 2026-08-09 — S3 semantic CARD edges (STS_S3_SEMANTIC_CARD_EDGES) implemented, falsified

Date: 2026-08-09
Session/task: Investigate and implement opt-in semantic card-edge identity for
Searcher3. `CombatObservation` canonicalizes the hand as a multiset (order
doesn't matter for `visibleHash`), but `Edge::action` stores a positional
`ActionType::CARD` referencing a hand index that can point to a different card
in a different particle determinization.

## Decision

**STOP — the semantic fix is falsified.** The implementation is complete,
diagnostics confirm the representation bug is real (40% mismatch rate in both
fresh and carried searches), but the fix produces a **−9.4pp win-rate loss at
+17% CPU** in the 64-seed paired gate. Do not run 128 seeds; do not promote.

The opt-in env flag `STS_S3_SEMANTIC_CARD_EDGES=0|1` stays in the tree for
diagnostic reproducibility (and as a potential building block for future
correctness-first approaches), but the default is `0` (current behavior) and
the experimental branch is closed.

## What was implemented

| Component | File | Detail |
|-----------|------|--------|
| Edge key fields | `include/sim/search/BattleScumSearcher3.h` | `CardActionKey cardKey` + `bool hasCardKey` on `Edge` (after `availabilityCount`, so existing `Edge{...}` aggregate init is ABI-compatible) |
| Resolution helper | `src/sim/search/BattleScumSearcher3.cpp` | `resolveSemanticCardEdge(edge, bc)` — scans current hand for a card matching `cardKey` (id, upgradeCount, costForTurn, freeToPlayOnce, specialData) and returns an `Action` with the correct hand index + target; returns `nullopt` when no match exists |
| Edge creation | `enumerateActionsForNode` | When flag is on, captures `cardActionKey(bc, action)` on every `ActionType::CARD` edge |
| step() internal-node | `step()` | Before `isValidAction` and before execution: resolve semantic key → use resolved `Action`. On resolution failure, treat edge as unavailable (fall to live-valid/rollout) |
| selectBestValidEdgePUCT | " | Resolve each edge before validity check; skip unavailable edges |
| advanceRoot matching | " | Fallback match by `cardKey` when raw `action == action` fails (handles index remapping across tree reuse) |
| reconcileRoot / union-expand | " | Use stored `cardKey` instead of re-extracting from stale positional index |
| Diagnostics | `step()`, `printReuseDiagnostics()` | `semanticCardEdgeVisits`, `rawIndexSemanticMismatches`, `semanticRebinds`, `semanticResolutionFailures`, `mismatchRate` |
| Flag parsing | `apps/one_combat.cpp` | `STS_S3_SEMANTIC_CARD_EDGES=1`, banner `S3-semCard=`, sidecar metadata |
| Regression tests | `apps/test.cpp` → `semantic_card_edges` | 9 tests: resolution across permutations, identical cards, upgrades, temp cost, targets, missing cards, observation identity |
| CTest | `CMakeLists.txt` | `semantic_card_edges` entry |

## Diagnostics — the bug is real

From 2 seeds @1000 sims/64p/A0 with semantic edges ON (B condition), aggregated
across all search decisions:

| Generation | CARD edge visits | Mismatches | Mismatch rate | Rebinds | Failures |
|-----------|-----------------|------------|---------------|---------|----------|
| Fresh (gen=0) | 9,887,852 | 3,889,075 | **39.3%** | 1,431,102 | 2,686,230 |
| Carried (gen≥1) | 13,406,566 | 5,436,344 | **40.5%** | 2,055,435 | 3,694,399 |
| **Total** | **23,294,418** | **9,325,419** | **40.0%** | 3,486,537 | 6,380,629 |

- A mismatch means the card at the edge's stored raw index is NOT the card
  whose `CardActionKey` was captured at edge creation.
- The ~40% mismatch rate in **fresh** searches (gen=0) proves this bug exists
  even without tree reuse — it's inherent in how different particle
  determinizations produce different hand permutations while the tree stores
  positional edges.
- Resolution failures (27.4% of visits) mean the semantic card is not in the
  current particle's hand at all; currently these fell through to rollout.

## Paired gate results

**64 seeds, A0, 1000 sims/decision, 64 particles, N=1 obs-stable reuse:**

| Arm | Win% | Floor | HP End | CPU/run |
|-----|------|-------|--------|---------|
| A: control (`sem=0`) | **43.8%** | 42.4 | 20.9 | 47.9s |
| B: semantic (`sem=1`) | 34.4% | 42.1 | 20.2 | 56.1s |
| **Δ** | **−9.4pp** | −0.3 | −0.7 | **+17%** |

- Discordant outcomes: 18/64 (28.1%)
- Win→Loss flips: 12, Loss→Win flips: 6
- Avg floor difference: 9.5 floors; avg HP difference: 31.8 HP

An 8-seed fresh-tree diagnostic (C: fresh+semOFF, D: fresh+semON) showed a
66% CPU increase in D, likely from the resolution overhead + increased rollout
fallback rate.

## Why the fix made things worse (Inference)

1. **Resolution failures cause excess rollout fallback.** 27% of semantic
   edge visits result in a resolution failure (card not in current particle's
   hand). Without semantic edges, many of these would pass `isValidAction`
   with the _wrong_ card at the stored index — a bug, but one that keeps the
   tree descent going instead of falling back to an expensive/noisy rollout.

2. **The live-valid framework (Phase 4) already mitigates the worst cases.**
   `selectBestValidEdgePUCT` re-selects among stored edges valid in the
   current particle world. When the raw-index card type is incompatible
   (e.g., Bash edge's index now holds Strike → Strike can't target →
   `isValidAction` fails), live-valid picks a different valid edge instead
   of the wrong card. So the positional-staleness damage is bounded.

3. **Stricter edge identity reduces PUCT exploration mass.** With semantic
   edges, an edge only accumulates visits from particles where the EXACT card
   is at the resolved index. This filtering removes "cross-contamination" but
   also reduces the sample count per edge, making exploration noisier.

4. **The resolution scan adds per-traversal overhead** (linear hand scan on
   every edge selection), though this is small relative to the rollout-cost
   increase.

## Alternatives considered

- **Expand scope to SINGLE_CARD_SELECT / MULTI_CARD_SELECT** — rejected: task
  explicitly limited scope to `ActionType::CARD`; no evidence the
  CARD_SELECT case suffers from the same positional problem.
- **Global Action redesign** — rejected by task spec; the experiment was
  Searcher3-only.
- **Different resolution strategy (e.g., resolve once per node per particle,
  cache results)** — not explored; the regression magnitude (−9.4pp) suggests
  the problem is fundamental (too many resolution failures → too many
  rollouts), not an optimization issue.
- **Rerun at higher sim budget (3k) to see if stricter identity pays off with
  more tree depth** — not run; per the pre-registered rule the 1k gate result
  is sufficient to stop.

## Evidence

- Implementation: `include/sim/search/BattleScumSearcher3.h`
  (`CardActionKey` moved before `Edge`, `cardKey`/`hasCardKey` fields, diag
  counters, `g_s3SemanticCardEdges`, `resolveSemanticCardEdge` declaration);
  `src/sim/search/BattleScumSearcher3.cpp` (full implementation);
  `apps/one_combat.cpp` (flag parse + banner + sidecar);
  `apps/test.cpp` (`testSemanticCardEdges` — 9 tests passing);
  `CMakeLists.txt` (CTest entry);
  `include/sim/util/BestBenchMeta.h` (`s3SemanticCardEdges` metadata).
- Tests: `./build/test semantic_card_edges` → PASS; `ctest --test-dir build`
  → 16/16 pass.
- Diagnostic data: `build/semantic_exp/B_diag.txt` (2 seeds, full per-search
  counters).
- Paired gate CSVs: `build/semantic_exp/A64.csv` (control, 43.8%),
  `build/semantic_exp/B64.csv` (semantic, 34.4%).

## Status and follow-up

- **Status: falsified.** Implementation stays in-tree behind the off-by-default
  flag for diagnostic reproducibility.
- **Closed.** No further gates planned unless a future change alters the
  rollout-fallback cost dynamics (e.g., a learned rollout policy that makes
  fallback less harmful, or a resolution-caching scheme that avoids the
  failure-rate penalty).
- Knowledge base: the representation mismatch between `CombatObservation`
  (multiset hand) and `Edge::action` (positional index) is a documented
  limitation; the live-valid framework is the recommended mitigation.
