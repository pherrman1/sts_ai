# Repaired Silver grouped visit-policy online screen: negative

## Outcome

The repaired, reviewed 32-seed paired online screen is valid and **negative**. Ordinary Silver UCT won 17/32 games; grouped normalized visit-PUCT won 11/32. The grouped arm therefore lost six net wins, crossing the predeclared negative boundary of at most -3.

The paired win-rate difference was -18.75 percentage points, with a shared 10,000-resample paired-bootstrap 95% interval of [-34.375, -6.25] percentage points. Mean floor changed by -1.28125, interval [-4.71875, +1.62578], and mean ending HP changed by -11.875, interval [-19.68828, -4.59375].

## Frozen implementation and validity

- Frozen SHA `0a8ec2087d5af7e9fec53323e84e5dc36a003f44`; repair commit `fb6af48b1c8d783abf7a4021a35ab29993b0d963`; base `034830df6510f1ab37ad4f053c07333fca0970c7`.
- Release executable SHA-256 `45305dfc93cf3261ff3d0ccc60ef2c87521a7b02253db93ee923d1938e4439ba`.
- Runtime model SHA-256 `bf16ecf38cd90c1deed494df1c8d16647e61cad7e57a13e7ef44d4bfe205c984`; source NPZ SHA-256 `a9f4ba81b200ec7ac7510970e7279ba7b46b1a0f53af521e5bebb98eba3986cf`.
- Fresh paired seeds `976032..976063`; Ascension 0; explicit Act-3 horizon; project-fair RNG; exact 1,000 Silver simulations per decision; exact-root-budget mode; allocated reuse cap 32768; one thread per process.
- Balanced waves ran 12, 12, and 8 seed pairs using 24, 24, and 16 processes. Their descriptive wall times were 7, 6, and 7 seconds.
- All 64 processes exited zero. All 64 CSV rows and 64 sidecars were present and unique. Sidecar selectors, model paths, implementation SHA, budgets, fair mode, and seed identities matched the manifest. Every treatment correctness counter was zero.

Two preserved setup namespaces and one failed driver-log redirection executed no `one_combat` process and produced no scientific rows. They did not inspect any candidate seed outcome. Attempt 3 is the sole scientific block.

## Gameplay and compute

| Metric | A: off | B: grouped | B-A |
| --- | ---: | ---: | ---: |
| Wins | 17 | 11 | -6 |
| Win rate | 53.125% | 34.375% | -18.750 pp |
| Mean floor | 43.15625 | 41.87500 | -1.28125 |
| Median floor | 51 | 50 | -1 |
| Mean ending HP | 30.625 | 18.750 | -11.875 |
| Mean CPU seconds/run | 3.810451 | 3.663513 | -0.146938 |
| CPU seconds / 1,000 Silver simulations | 0.008628 | 0.008645 | — |

The predeclared normalized CPU ratio was 1.001994. Grouped policy inference consumed 401,256 microseconds across 13,560 scored roots and 84,585 actions, or 0.3423% of grouped CPU. Priors were applied to 4,764 fresh roots and 8,796 reused roots.

## Scientific interpretation

This valid block satisfies `wins_B - wins_A <= -3`, so the classification is `GROUPED_VISIT_POLICY_ONLINE_SCREEN_NEGATIVE`. It does not advance to a 128-seed confirmation. The result is evidence about this frozen grouped normalized visit prior, runtime, budget, and repeatedly developed Silver stack; it does not establish that every learned prior or PUCT configuration is harmful.

No `c_puct`, temperature, model, feature, search-budget, or seed tuning is authorized. Rank-4 gameplay was not run. The complete 32 paired rows and shared-bootstrap results are in `build/silver_visit_prior_online_screen_repair_20260830/paired_analysis.json`; raw CSVs, sidecars, logs, timings, and wave statuses are preserved in the adjacent raw archive.
