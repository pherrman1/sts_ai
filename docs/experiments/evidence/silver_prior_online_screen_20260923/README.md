# Frozen SilverPriorNetV1 online gameplay screen

This packet records the pre-review implementation evidence and two paired
end-to-end smoke seeds. The smoke runs validate runtime integration only; their
win/loss outcomes are excluded from the scientific screen.

The frozen offline root-mechanism result remains
`LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED`. This online question was explicitly
requested as a separate bounded gameplay check. The user waived the proposed
5 ms per-root inference stop threshold, so measured inference latency is
reported without blocking the smoke runs.

The 32-seed gameplay screen is not included here and must not run until
independent implementation review. After review, use exactly seeds
24100000..24100031, after first checking that this block has never been used.

## Frozen identities

- Branch: `codex/silver-prior-root-screen-20260923`
- Main merged into the experiment branch: `3d28adfcf3c989e338eff9ef85e4a5c6d8794497`
- Pre-merge experiment head: `9fe3cb05b4dfd367f9db1370d245cb8d1a4f978e`
- Frozen checkpoint: `b756c3e6576bdb53085f24aeb1102e4e2fe55fd7469c55546c99f068ccf40e24`
- Native artifact: `/home/philippherrmann/Documents/sts/silver-prior-model-v1/native/T2.native`
- Native artifact SHA-256: `b3a4c5e4bbe91b7f17dadf588408a95199ec5b8b25f732d99ef0966c0ff05fdb`
- Native parity: [`native-parity.json`](native-parity.json)
- Native latency: [`native-latency.json`](native-latency.json)
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

The smoke comparison is paired by seed, Ascension 0, 1,000 simulations per
combat decision, project-fair play, native OOC, Silver combat, Act 3 stop,
keys off, one thread, fixed root budgets, adaptive off, 32,768 allocated reuse
cap, exact visit lock off, and rho racing off. The treatment differs only by
loading the frozen native prior; the existing policy prior remains unchanged.

For the later screen, build and review one exact commit, then invoke
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
runtime failure counter.

The summary applies the frozen paired decision rule: `net_discordant` is
LEARNED-only wins minus CONTROL-only wins; classify promising at `>= +4`,
unfavorable at `<= -4`, otherwise inconclusive. It reports the complete paired
win table, an exact two-sided binomial test over discordant pairs, and paired
secondary deltas for floor, end HP, fights lost, wall time, search time,
decisions, and simulations. All paired confidence intervals use a frozen
5,000-replicate paired bootstrap with seed `20260923` and SHA-256 counter-based
resampling (nearest-rank 2.5th/97.5th percentiles). Synthetic tests cover every
classification and all four paired table cells. This packet contains no 32-seed
run results.

## Interpretation boundary

The two smoke outcomes are not evidence that the model improves gameplay.
They establish whether the runtime contract works: completed arms, correct
simulation counts, prior calls only in eligible ordinary decisions, zero
surface failures, matching PUCT/evaluation counts, and retained-root reuse.
The offline negative result remains visible and unchanged.

Knowledge impact: current model and integration contract are documented by the
implementation and this experiment evidence packet; no offline evidence was
changed.
