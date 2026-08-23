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
at `e029dffb4c72449e8fc5b874391c49a27b2f6a81`. The existing CSV was retrieved
read-only from the recorded `sts-test` location and re-hashed locally before
training; it was not regenerated. The current production export was made at
training-code SHA `ac2a5bf860ce5728a8ecb4843970795a111db0f5`:

- `models/v_runwin_e2c_v2.txt`: SHA-256
  `4272039d80e9bf7493fd6af71dcd7a67e915a56dce36ff0f207544c79af0c14e`;
- `models/v_runwin_e2c_v2.manifest.json`: SHA-256
  `b1f08c6a765d1f7bb5c38bf81c0eace6fea3beb010442e26d0000bf0daa692ac`;
- `tests/data/v_runwin_e2c_v2_parity.csv`: SHA-256
  `02da2896380cf7ab20cb6949f3d1b4df7971194b4a49cab46d9004517b7f151f`.

The held-out all-RAW T-raw metrics are AUC `0.7357093849908911`, log loss
`0.5876621241286121`, Brier `0.20358731804525068`, and ECE
`0.0271840698715477` (`n=6300`). Its `best_iteration` is `225`; the compact
artifact contains exactly `226` trees (`0..225`). The ignored trainer Booster
SHA-256 is `fa7dc698ec00cb36d9242020157a43244b244749a8b9cfc60c87abb2b19e4475`.
Python/native parity over the committed 256-row production fixture had maximum
absolute error `2.255981821e-07` (threshold `1e-4`). The native CSV parser
accepts CRLF fixtures, so this Windows-produced fixture is exercised unchanged
by the Linux native path.

## Interfaces

- `one_combat runwinshadow <nSeeds> <sims> <asc> <out.csv> [seedOffset]`
  forces fair Searcher3 and refuses to run without `STS_RUNWIN_SHADOW_MODEL`.
  It writes the main replicate CSV, `.runs.csv`, `.roots.csv`, and provenance
  JSON.
- `STS_RUNWIN_SHADOW_R` (default `1`),
  `STS_RUNWIN_SHADOW_PER_STRATUM` (default `1`), and
  `STS_RUNWIN_SHADOW_MAX_GROUPS` (default `16`) bound diagnostic work.
- `tools/analyze_runwin_shadow.py` performs schema/range/duplicate/failure
  checks, coverage, root variance, and an explicitly caveated optional
  reference join. Its raw-row identity includes `replicate`, but it first
  collapses exactly complete, failure-free source leaves using the identity
  without `replicate`. The primary run-win score is the producer's verified
  `runwin_mean = mean_r Z_r(s)`, never an individual
  `runwin_probability` row. A reference requires that leaf identity and an
  explicit `--reference-target`; duplicate or many-to-many joins fail.
  Inconsistent source-leaf metadata/baseline/aggregate fields fail, while
  incomplete or failed diagnostic leaves are recorded as exclusions from
  primary ranking. It reports tie-aware within-root pairwise accuracy,
  Spearman, co-top-choice agreement, and source-seed bootstrap CIs for
  runwin-minus-baseline ranking deltas at the source-leaf level. It does not
  optimize a blend or assert policy improvement.

## Scope and evidence

This is implementation support only. Exact RAW projection parity passes at
1,192 canonical features with maximum error zero. It makes no gameplay or
scientific claim; within-root ranking remains a later preregistered question
with an independent stronger reference. No gameplay-quality experiment or
promotion is authorized by this record.
