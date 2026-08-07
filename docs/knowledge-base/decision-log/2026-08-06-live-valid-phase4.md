# 2026-08-06 — STS_LIVE_VALID: Phase 4 fair-tree structural fix (live-valid-biased edge selection) — promotion candidate, S3 direction positive at both budgets, cpu-positive

Date: 2026-08-06
Session/task: Execute Phase 4 of the adaptive-budget program for BOTH
searchers: instrument Searcher3's rollout usage (never measured before),
implement the live-valid-biased edge selection fix in Searcher2 and
Searcher3, and gate each arm.

## Decisions

1. **Fix design: live-valid-biased edge selection.** When the PUCT-chosen
   stored edge is illegal in the current determinization (the §117
   illegal-stored fallback, ~48-68% of fair rollouts), re-select among the
   stored edges that ARE valid in this world using the same UCB/PUCT scoring
   (`selectBestValidEdgeToSearch` / `selectBestValidEdgePUCT`), and continue
   tree descent. Only when NO stored edge is valid does the sim fall back to
   a random rollout. Narrower than obs-keyed descent (falsified, §114) — the
   tree structure and observation identity are untouched; only the descent
   choice changes. Default off (`STS_LIVE_VALID=1`).

2. **S3 instrumentation is the prerequisite.** `SearchDiagnostics` moved to a
   shared header (`include/sim/search/SearchDiagnostics.h`); S3 gains the
   same counters (rollout-cause split, treeActions, maxTreeDepth,
   simSeconds); `searchdiag` accepts S3 with rowtype A only (B probes are S2
   machinery, probeEvery forced 0). The S2 → S3 measurement comparison is
   now apples-to-apples on the same schema.

3. **Promotion rule (plan T3-style): win ≥ flat with CI excluding a
   meaningful loss AND cpu ≤ flat.** The S3 @3k result (+5.5pp, hp +4.1,
   CI barely excludes zero) is directionally strong but cpu-positive
   (+7.9%); the AND clause fails, so no promotion on this first gate.

## Alternatives considered

- S3-style root filtering instead of in-tree re-selection — rejected for
  this pass: the root filter only fixes the agent's pick, not the sim
  descent where the measured share lives; in-tree re-selection is the
  direct fix and works for both searchers.
- Re-selection biased by live validity only (uniform among valid) — rejected:
  reuse the existing UCB/PUCT scoring so exploration behavior is preserved
  within the valid subset.
- Counting re-selected descents as rollouts for invariant continuity —
  rejected: they are tree actions by construction; the diag invariants hold
  on both searchers with the correct counting (verified 0 violations).

## Evidence

- **S3 illegal-stored share (first measurement, fair @3k, 6 seeds):** S3
  default 59.5% (MONSTER 70%, ELITE 54%, BOSS 54%); S3−belief−chain 58.4%.
  Higher than S2's 48% (§117) — particle worlds diverge more.
- **Fix effect (fair @500 smoke):** S2 0.26 → 0.00; S3 0.38 → 0.10.
- **Gates (256 seeds, block 126700+, fair):** S2 @1k +0.4pp (SE 2.2, cpu
  +5.6%); S3−bc @1k +3.5pp (SE 2.4, CI includes 0, cpu +15.1%); **S3−bc @3k
  +5.5pp (SE 2.6, 95% CI +5.5 ± 5.1, flips 35/21, hp 7.4→11.5, cpu +7.9%)**.

## Status

**Promotion candidate, first gate only.** S3's direction is positive and
consistent at both budgets; the diagnosis is confirmed (share 0.58 → 0.10).
Not promoted: all arms are cpu-positive. Remaining before any default flip:
a second independent S3 @3k gate to firm the CI, and an explicit cpu-cost
decision (the +5.5pp / +7.9% trade is arguably worth it at the operating
point — that is a policy call, not an automatic promotion). S2's @3k pair
is not run (S2 is not the recommended operating point, §113). Recorded as
EXPERIMENTS.md §122. Env gate stays default off.
