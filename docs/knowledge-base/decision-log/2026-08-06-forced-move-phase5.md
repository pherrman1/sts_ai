# 2026-08-06 — STS_FORCED_MOVE: Phase 5 forced-action contraction — decision-neutral at −16% cpu, promotion candidate

Date: 2026-08-06
Session/task: Execute plan T6 Phase 5 (`plan-searchdiag-adaptive-continuation.md`):
strictly-forced-only forced-action contraction, isolated from the falsified
STS_CONV_ROOT arm (§118) and measured on its own paired gate.

## Decisions

1. **Scope: strictly-forced-only.** When the live root state has exactly one
   legal action (canonical enumeration via
   `BattleScumSearcher2::onlyLegalAction`), commit it directly without
   searching. Narrower than Searcher3's deterministic chain compression
   (net-negative, §106) — no multi-step contraction, no dominance reasoning,
   only the single-action case. TT re-measure left optional/not done.

2. **Standalone env gate `STS_FORCED_MOVE=1`, default off.** The mechanism
   previously ran only inside the `g_convRootStop` branch, so §118's −2.3pp
   was confounded. Phase 5 hoists the check to fire on
   `g_forcedMoveSkip || g_convRootStop` in both `playoutBattleFair` (skip +
   takeAction, fresh searcher anyway) and `playoutBattle` (skip +
   takeAction + advanceRoot so the reused subtree survives). Default-off so
   no behavior change when unset.

3. **Promotion rule: env-only until two independent gates agree** (plan T5
   convention). The 256-seed gate shows exact per-seed outcome equality
   (0/256 diffs) at −15.9% cpu — but the fair gate covers only the fair
   path; the non-fair `advanceRoot` variant is wired but untested at scale,
   and a second gate is required before flipping the built-in default.

## Alternatives considered

- Make `STS_FORCED_MOVE` default-on immediately — rejected: the §118 lesson
  (single 64-seed signals did not survive) plus the untested non-fair path
  argues for one more gate before a default flip, even though this arm is
  decision-neutral by construction.
- Include action-dominance pruning (skip a searched action because another
  strictly dominates it) — rejected: the plan names strictly-forced-only;
  dominance is a policy change requiring its own gate, and S3 compression's
  net-negative (§106) warns against bundling.
- TT re-measure (§5 note) — optional per plan; not done (TT is orthogonal to
  forced moves and was not touched by this diff).

## Evidence

- 256 paired seeds @1k fair (GCP, 24 threads): flat 22.3% / floor 36.0 /
  hp 12.6 / cpu 8.96 vs forced 22.3% / floor 36.0 / hp 12.6 / cpu 7.54
  (−15.9%). **Per-seed equality on won/floor/act/hpEnd/fightsLost/
  deathCombat/deathEncounter: 0 diffs across all 256 seeds** (total sec
  2295.0 → 1929.7). CSVs `build/fm_{flat,forced}_256.csv`.
- Local 8-seed smoke identical (12.5%/35.8/9.9 both arms; cpu 4.17 → 3.57).

## Status

**Promoted to built-in default ON (fair path only), 2026-08-06 (§121).**
The confirmation gate (seeds 126700–126955, fixed binary) reproduced exact
per-seed outcome equality (0/256 diffs) at −18.0% cpu, and the known-RNG
non-fair run found and fixed a real hang (stale `bestActions`/
`bestOutcomePlayerHp` after a forced skip → `stepThroughSolution` on an
empty list forever) plus a real non-fair divergence (3/8 seeds, persistent
tree reuse + shared RNG). Resolution: `STS_FORCED_MOVE` is **fair-only**
(the standalone flag is a no-op in the non-fair path, whose forced shortcut
remains scoped to the falsified `g_convRootStop` arm, now hang-free);
`g_forcedMoveSkip` defaults true with `STS_FORCED_MOVE=0` to disable. Two
independent 256-seed fair gates agree (§120 seeds 0–255, §121 seeds
126700–126955); all historical fair numbers stay valid (decision-neutral);
current-baselines.md notes the deployed-config change.
