# 2026-08-07 — STS_LIVE_VALID promoted: default ON in the fair-S3 path; recorded cpu-trade call (+8-15% cpu for +5-6pp win)

## Decision

Promote the Phase 4 fair-tree structural fix (`STS_LIVE_VALID`, live-valid
edge re-selection) to **default ON for the Searcher3 fair-play regime**
(`apps/one_combat.cpp::main`, computed after the `STS_FAIR`/`STS_SEARCHER3`
env parse; `STS_LIVE_VALID=0` explicitly disables). S2 fair stays opt-in;
non-fair paths and the `fairgen` datagen mode are unchanged unless the env
flag is set explicitly.

## Rationale

**Evidence:** two independent 256-seed paired fair gates (S3−bc @3k, 24
threads, GCP) agree on a win-rate gain with CI excluding a meaningful loss:

- §122 (block 126700+): +5.5pp (95% CI +5.5 ± 5.1pp), hp +4.1, floor +0.6,
  cpu +7.9%.
- §123 (block 250000+): +5.9pp (95% CI +5.9 ± 1.8pp), hp +3.1, floor +1.1,
  cpu +14.6%; flips 34 up / 19 down.

**The cpu-trade call (recorded, per the plan's T3-style rule which the §122
AND clause failed):** accept ~+8 to +15% cpu for a reproducible ~+5 to +6pp
win with +3 to +4 end-HP — the strongest win-rate result of the
adaptive-budget program, and within the plan's stated envelope ("~+8-10% cpu
for a ~+3pp+ win"). The diagnosis behind it is structural (illegal-stored
share 0.58 → 0.10 in S3), so the gain is a tree-reuse fix, not a
tuning artifact.

## Alternatives considered

- Keep env-only (default off): rejected — two independent gates satisfy the
  win clause; deferring costs a reproducible +5-6pp.
- Default ON for S2 too: rejected — S2 @1k is neutral (+0.4pp) at +5.6% cpu
  and S2 is not the recommended searcher (§113); an S2 @3k pair is needed
  before any S2 flip.
- Default ON in non-fair paths: rejected — unmeasured; non-fair S3 still
  determinizes via particles, and §121 showed non-fair tree-reuse changes
  can diverge; env flag remains available.
- Cover `fairgen` datagen with the default: deferred — datagen forces the
  regime after the env parse; flipping it would silently change the
  policy-target training distribution measured pre-fix. Open question:
  re-run fairgen datagen with the fix to align the distribution.

## Evidence

- Gates: EXPERIMENTS.md §122 (block 126700+) and §123 (block 250000+);
  per-seed CSVs `build/lv_s3_3k_{flat,fix}.csv`, `build/lv2_s3_{ctl,fix}_256.csv`.
- Smoke (local): fair-S3 default now prints
  `[live-valid edge re-selection ON (fair S3 default, §123)]` and is
  per-seed identical to explicit `STS_LIVE_VALID=1` (3 seeds); S2 fair
  prints nothing (0 lines); explicit `STS_LIVE_VALID=0` disables (0 lines).
- Code: default block in `apps/one_combat.cpp::main`; consumption
  `BattleScumSearcher2.cpp:412`, `BattleScumSearcher3.cpp:356`.

## Status

Deployed in commit after `588fd6e`. Open follow-ups: S2 @3k live-valid pair
if S2 deployment is ever considered; full-stack (§113 headline config)
re-measurement with the new default; fairgen datagen alignment question.
