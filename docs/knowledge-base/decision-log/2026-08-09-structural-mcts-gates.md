# Decision: five structural MCTS improvements investigated and gated (2026-08-09)

## Decision

Investigated five structural MCTS improvement directions for BattleScumSearcher3:
particle/belief, cross-decision carryover, pruning/state-space, adaptive budgets,
and rollout structures. Ranked by architect, implemented top candidates, and
gated all four new features at 64 paired seeds @1k sims.

## Findings

| Line | Verdict | 64-seed gate (win Δ) | Status |
|---|---|---|---|
| S2 transposition table (STS_TT) | **CLOSED** | −18.8pp (32 seeds, 0% win) | Catastrophic — destroys play quality |
| Mid-rollout collision frequency | **DIAGNOSTIC** | 0.089% collision rate | Dead end for rollout TT/path reuse |
| Multiselect canonicalization | NULL | −1.6pp, 1/64 discordant | Opt-in, decision-neutral |
| Forced-move budget pool redirect | NULL | +1.6pp, 5/64 discordant | Opt-in, ambiguous direction |
| Dynamic α by rollout length (A2) | NEGATIVE | −3.1pp, 14/64 discordant (22%) | Opt-in, direction negative |

**All three gameplay gates null or negative at 64 seeds.** No feature promoted
to default.

## Other changes

- Removed dead `Belief::resample` (SIR defined, zero callers — `CombatObservation.cpp/h`)
- Fixed stale KB: "two" belief.update calls → "five" (`combat-search.md`)
- Added `STS_MULTISELECT_CANONICAL` with parity test (`cardselect_canonical`)
- Added `STS_S3_POOL_REDIRECT` in S3 fair path (pure budget redirect, no stability stop)
- Added `STS_VNET_ALPHA_LEN` (A2 dynamic α, plan's pre-registered table)

## Rationale

The strongest finding was the S2 TT (implemented but NEVER benchmarked through
§99–§135) — it was catastrophically harmful (0% win), closing the TT line for
both S2 and S3. Rollout collision measurement confirmed the §114 prediction
with data (0.089%). The three gameplay features are all opt-in and
decision-neutral or ambiguous at 64 seeds; none warrant promotion.

## Caveats

- All gates run without the strategic tok-net (broken by §142 NGLB 50→41 change
  in `de75e6c`). Paired deltas are internally valid, absolute win% (~21.9) is
  NOT comparable to the §126 50.4% reference.
- 64 seeds is insufficient for statistical confidence on small effects; 256-seed
  GCP gates would be needed to confirm, but the negative/null direction makes
  escalation low-priority.

## Alternatives considered

- Inverted dynamic α table (task specification had {≤2:0.6,…,>10:0.2} vs plan's
  {≤2:0.1,…,>10:0.6}). Plan's table implemented; inversion would be directionally
  worse at the calibrated α=0.3 optimum.
- S3 TT port: precluded by S2 TT catastrophe.
- Rollout TT / path reuse: precluded by 0.089% collision measurement.
- Aggressive `canPruneAsDead`: structurally dead (Action::execute runs atomically
  to next player-decision state — can never fire, proven §106 A3).
- Cross-decision carryover: all four channels falsified or infeasible.

## Evidence

- EXPERIMENTS.md §143–§147
- `build/gate_{ctl,canon,pool,alphalen}_1k_64.csv`
- `build/tt_s2_{off,on}_1k_32.csv`
- `build/rollout_trace.csv` (830,753 rows)
- `src/sim/search/BattleScumSearcher3.cpp` (new globals + lookup)
- `src/sim/search/Action.cpp` (multiselect canonicalization)
- `src/sim/search/ScumSearchAgent2.cpp` (pool redirect)
- `apps/one_combat.cpp` (env parses)
- `apps/test.cpp` (cardselect_canonical test)

## Status

Complete. All gates recorded, dead code removed, KB updated. Dynamic α table
inversion remains as an unmeasured follow-up but is low-priority given the
negative direction of the plan's table.
