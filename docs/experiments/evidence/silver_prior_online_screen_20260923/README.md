# Frozen SilverPriorNetV1 online gameplay screen

This packet records the pre-review implementation evidence, two paired
runtime-only smoke seeds, and the completed 32-pair online gameplay screen.
The smoke outcomes remain excluded from the scientific screen.

The frozen offline root-mechanism result remains
`LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED`. This online question was explicitly
requested as a separate bounded gameplay check. The user waived the proposed
5 ms per-root inference stop threshold, so measured inference latency is
reported without blocking the screen.

The 32-seed gameplay screen used exactly seeds 24100000..24100031 after
independent implementation review and a fresh local artifact/history check.

## Frozen identities

- Branch: `codex/silver-prior-root-screen-20260923`
- Current main merged into the experiment branch: `4e4da3b154e59f193c77f972e9b5e2338c52be3c` (the earlier merge base was `3d28adfcf3c989e338eff9ef85e4a5c6d8794497`)
- Pre-merge experiment head: `9fe3cb05b4dfd367f9db1370d245cb8d1a4f978e`
- Frozen checkpoint: `b756c3e6576bdb53085f24aeb1102e4e2fe55fd7469c55546c99f068ccf40e24`
- Native artifact: `/home/philippherrmann/Documents/sts/silver-prior-model-v1/native/T2.native`
- Native artifact SHA-256: `b3a4c5e4bbe91b7f17dadf588408a95199ec5b8b25f732d99ef0966c0ff05fdb`
- Native parity and latency were rerun from clean source commit `57a824349fd99c917cf22d67e929a8630f001a9d` after merging current `main`: [`native-parity.json`](native-parity.json), [`native-latency.json`](native-latency.json). Parity executable SHA-256: `3abbe9b9249e4dc3398550e3ff1fb9f4e297219c089167d2134b1c146959ed2d`.
- Corrected all-combat smoke aggregation: [`smoke.json`](smoke.json), raw CSV/log files in this directory

The smoke parser sums every `[silver-combat]` record for each run. Across the
two LEARNED runs it found 901 prior evaluations, all matching root-PUCT calls,
and zero prior surface failures. Mean inference cost was 6.679 ms/call on seed
24109998 and 6.930 ms/call on seed 24109999. The legacy logs have no per-call
samples, so pooled median and p95 cannot be recovered. The four CSV metadata
files identify executable SHA `1dc14cef9f5b6602fe84bd2a266347757245d78c`, not
the then-current PR candidate `fb9e0cf9510ac612fdc3f521076ca093d1fb55b5`.
Treat these as historical working-tree integration evidence, not a smoke of
that candidate SHA; they were not rerun. The new screen runner validates each
combat record and metadata SHA, and enables raw per-call samples.

The post-merge native parity rerun from `57a824349fd99c917cf22d67e929a8630f001a9d` still passes all 64 roots / 411 actions:
maximum prior error `8.799900734768329e-07` and maximum logit error
`2.86102294921875e-06`. Warm latency was median `7,821.303 us`, p95
`11,657.502 us`, mean `7,520.073 us`; model load was `438,621.02 us`. The
rebuilt `one_combat` SHA-256 used by the completed screen is
`fc41e47d4a7d78f0922144d480a3dbeed674cf6fa1db21e97c568ff836a40197`.

The smoke comparison is paired by seed, Ascension 0, 1,000 simulations per
combat decision, project-fair play, native OOC, Silver combat, Act 3 stop,
keys off, one thread, fixed root budgets, adaptive off, 32,768 allocated reuse
cap, exact visit lock off, and rho racing off. The treatment differs only by
loading the frozen native prior; the existing policy prior remains unchanged.

For reproduction, invoke
`tools/silver_prior_online_screen.py run-pair` once per authorized seed with
that commit SHA, expected `one_combat` SHA-256, its `one_combat` binary, the
frozen artifact, and a fresh output directory. Each pair checks out a clean
exact SHA, verifies the executable and model hashes immediately before both
processes, pins `STS_EXECUTABLE_GIT_SHA`, clears inherited `STS_*` settings,
records the frozen flags, alternates arm order by seed, uses
`tools/seed_guard.sh`, and writes one validated JSON summary per arm. After all
pairs complete, `tools/silver_prior_online_screen.py summarize-screen
--expected-git-sha SHA --expected-binary-sha256 SHA <64 summary paths>` rejects
missing/duplicate seeds, mismatched source or binary SHA, mixed flags, artifact
drift, latency-sample omissions, simulation-budget errors, or any nonzero
runtime failure counter. Simulation accounting treats sequential-selection
transaction subdecisions as the searched decisions replacing their one outer
transaction decision: `decisions + transaction_subdecisions -
transaction_decisions`.

The summary applies the frozen paired decision rule: `net_discordant` is
LEARNED-only wins minus CONTROL-only wins; classify promising at `>= +4`,
unfavorable at `<= -4`, otherwise inconclusive. It reports the complete paired
win table, an exact two-sided binomial test over discordant pairs, and paired
secondary deltas for floor, end HP, fights lost, wall time, search time,
decisions, and simulations. All paired confidence intervals use a frozen
5,000-replicate paired bootstrap with seed `20260923` and SHA-256 counter-based
resampling (nearest-rank 2.5th/97.5th percentiles). Synthetic tests cover every
classification and all four paired table cells.

## Completed online screen

All 32 pairs completed at frozen executable source SHA
`57a824349fd99c917cf22d67e929a8630f001a9d`, `one_combat` SHA-256
`fc41e47d4a7d78f0922144d480a3dbeed674cf6fa1db21e97c568ff836a40197`, and
T2.native SHA-256
`b3a4c5e4bbe91b7f17dadf588408a95199ec5b8b25f732d99ef0966c0ff05fdb`. The
screen comprised 64 successful, seed-guarded A0 project-fair full runs, stopped
at Act 3, with 1,000 simulations per effective searched decision and the
frozen flags above. All runs completed with zero surface, transaction,
conversion, semantic-resolution, or knowledge failures; all learned calls had
matching root-PUCT decisions. The validator correction above was needed because
seed `24100009` exercised a GAMBLE transaction, whose two searched
subdecisions replace one outer decision. No raw output was changed or rerun.

CONTROL won 21/32 and LEARNED won 15/32. The paired table is 1 learned-only,
7 control-only, 14 both-win, and 10 both-lose; `net_discordant = -6`, so the
preregistered classification is **`ONLINE_LEARNED_PRIOR_UNFAVORABLE`**. The
paired win-rate delta is -18.75 percentage points (paired bootstrap 95% CI
[-34.375, -3.125] pp); the exact two-sided test over eight discordant pairs is
`p = 0.0703125`. This is an unfavorable result under the preregistered decision
rule, not a claim of conventional statistical significance. Mean treatment
inference latency was 7.247 ms/call (median 7.237 ms, p95 11.575 ms).

The deterministic aggregate and seed-level compact outcomes are
[`screen-summary.json`](screen-summary.json) and
[`screen-seed-outcomes.csv`](screen-seed-outcomes.csv). The 256 raw per-arm
CSV, metadata, log, and summary files, plus per-pair records, remain outside
the Git worktree at `/tmp/silver-prior-online-screen-57a824349fd99c91`; they
were not committed. There are 31 complete per-pair stdout records and one empty
failure stub for the corrected seed-9 accounting check; the authoritative
per-arm summaries include all 32 pairs. Freshness checks found no prior local run artifacts for
this exact block; the seed references found in the repository were the frozen
protocol itself. The user had separately reported no pushed-history matches.

## Interpretation boundary

The smoke outcomes remain runtime-contract evidence only. The separate online
screen is an unfavorable bounded gameplay result for this frozen model,
configuration, and seed block; it does not qualify or promote the model or
change a default. The offline result remains
`LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED` and is not revised by this
whole-run screen.

Knowledge impact: this online outcome is recorded in the experiment ledger and
current research status. No offline evidence, runtime default, or model
qualification was changed.
