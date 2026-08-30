# Silver rank-4 visit-policy online screen: inconclusive

## Outcome

The valid fresh 32-seed screen is **`RANK4_VISIT_POLICY_ONLINE_SCREEN_INCONCLUSIVE`**. Ordinary UCT won 19/32; rank4 visit-PUCT won 17/32, a -2 net-win / -6.25 percentage-point difference. Rank4 did not gain the required three wins, but it also did not lose the three wins required for a negative classification.

The paired 10,000-resample bootstrap win-delta interval was [-18.75,+6.25] pp. Mean-floor delta was -1.96875, interval [-5.6875,+1.9375]; ending-HP delta was +0.21875, interval [-5.84375,+6.59375].

## Validity and provenance

- Frozen implementation `0a8ec2087d5af7e9fec53323e84e5dc36a003f44`; executable SHA-256 `45305dfc93cf3261ff3d0ccc60ef2c87521a7b02253db93ee923d1938e4439ba`.
- Runtime model SHA-256 `bf16ecf38cd90c1deed494df1c8d16647e61cad7e57a13e7ef44d4bfe205c984`; source NPZ SHA-256 `a9f4ba81b200ec7ac7510970e7279ba7b46b1a0f53af521e5bebb98eba3986cf`.
- Fresh seeds `976064..976095`; Ascension 0; explicit Act-3 horizon; fair RNG; exact 1,000 simulations/decision; exact root budgets; allocated reuse cap 32768; one thread/process.
- Balanced 12/12/8-pair waves used 24/24/16 processes and took descriptively 11/4/6 seconds.
- All 64 processes exited zero; all 64 unique rows and sidecars matched seed, selector, frozen SHA, budget, model path, and fair mode. Every correctness counter was zero.

## Results

| Metric | A: off | B: rank4 | B-A |
| --- | ---: | ---: | ---: |
| Wins | 19 | 17 | -2 |
| Win rate | 59.375% | 53.125% | -6.250 pp |
| Mean floor | 44.31250 | 42.34375 | -1.96875 |
| Median floor | 51 | 51 | 0 |
| Mean ending HP | 32.9375 | 33.15625 | +0.21875 |
| Mean CPU seconds/run | 3.681836 | 3.714810 | +0.032974 |
| CPU seconds/1,000 simulations | 0.008523 | 0.008451 | — |

The normalized CPU ratio was 0.991455. Rank4 scored 14,067 roots / 89,832 actions, applied 5,071 fresh and 8,996 reused priors, and used 609,351 inference microseconds, 0.5126% of treatment CPU.

## Interpretation

This bounded screen does not establish a gameplay improvement and does not meet the negative threshold. No rank/checkpoint/temperature/`c_puct`/budget tuning or automatic follow-up is authorized. The complete 32 paired rows are in `build/silver_visit_prior_online_screen_rank4_20260830/paired_analysis.json`.
