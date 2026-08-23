# E2c RAW run-win critic: deployment/shadow phase

## Decision

Add an opt-in, strictly shadow-only producer for the E2c-v2 RAW post-combat
run-win critic.  Baseline is `f2879ad7d0444b4d3edad87ba62f6181580c48d8`;
the implementation SHA is recorded by the branch commit and each shadow
provenance sidecar records the executing SHA.

The semantic boundary is exact: a sampled nonterminal Searcher3 leaf is first
continued in an isolated `BattleContext` copy using diagnostic-only RNG. A
combat loss receives run-win value exactly zero. A victory is transferred into
a copied battle-entry `GameContext` through the canonical `exitBattle` path;
the projection is captured after persistent transfer and before
`regainControl()`/reward generation, precisely the E2c RAW boundary. It is
invalid to score arbitrary in-combat leaf HP, gold, potions, or counters as a
RAW state because T-raw was trained only on survived terminal transfers.

`runwinshadow` never supplies a value to leaf evaluation, terminal evaluation,
backpropagation, PUCT, root selection, beliefs, particles, reuse, live RNG, or
out-of-combat policy.  Its callback only copies reservoir-accepted leaves;
after search completion it performs isolated continuations with a stable seed
derived from seed/fight/decision/leaf hash/replicate/fixed salt.  All hooks are
explicitly disarmed after each run.  `STS_TERM_WIN` is untouched.

## Model bundle and artifact status

`tools/analyze_postcombat_raw_terminal.py --export-bundle DIR` now retains the
all-RAW T-raw Booster and explicitly exports trees `0..best_iteration`, using
the shared `export_win_model.py` compact logistic serializer.  The manifest
records ordered features, full families, split, parameters, versions, held-out
metrics, and dataset/model/export hashes; a deterministic Python parity CSV is
written beside it.  The native loader rejects unknown/duplicate features and
invalid tree indices.

The designated production CSV SHA is
`da692d5979f9df3cad70ee6d76bd34fcf174ac74f557b942fb662e3d8c6a89e2`, produced
at `e029dffb4c72449e8fc5b874391c49a27b2f6a81`. It was not present in bounded
local artifact locations for this implementation. Therefore no production
`models/v_runwin_e2c_v2.*` artifact is committed and no dataset was
regenerated. A tiny separately named synthetic compact model exists only for
native-format/parity and smoke verification.

## Interfaces

- `one_combat runwinshadow <nSeeds> <sims> <asc> <out.csv> [seedOffset]`
  forces fair Searcher3 and refuses to run without `STS_RUNWIN_SHADOW_MODEL`.
  It writes the main replicate CSV, `.runs.csv`, `.roots.csv`, and provenance
  JSON.
- `STS_RUNWIN_SHADOW_R` (default `1`),
  `STS_RUNWIN_SHADOW_PER_STRATUM` (default `1`), and
  `STS_RUNWIN_SHADOW_MAX_GROUPS` (default `16`) bound diagnostic work.
- `tools/analyze_runwin_shadow.py` performs schema/range/duplicate/failure
  checks, coverage, root variance, seed-level bootstrap summaries, and an
  explicitly caveated optional reference join. It does not optimize a blend or
  assert policy improvement.

## Scope and evidence

This is implementation support only. It makes no gameplay or scientific claim;
within-root ranking remains a later preregistered question with an independent
stronger reference. Missing production-artifact training/export evidence and
any verification unavailable in the local environment must remain explicit in
the draft PR evidence packet.
