# Silver root-only c=35 128-seed online rerun

Date: 2026-08-29

## Decision

Record `ROOT_EXPLORATION_GAMEPLAY_INCONCLUSIVE`. Keep ordinary root c=25 as
the default. Do not promote c=35 or restore Sequential Halving/root pruning.

## Evidence and reasoning

The first 128-seed attempt was correctly identified as one-threaded and was
aborted before completion. Its partial rows are excluded. The fresh rerun used
24 threads on the designated 24-core GCP server. Treatment and control ran
sequentially to avoid 48-thread oversubscription, preserving the same-seed
paired comparison.

On fresh seeds 932401-932528, c=35 won 84/128 and control c=25 won 79/128.
The strict paired win delta was +3.9pp with 95% CI [-3.9,+11.7]pp; paired
floor delta was +0.9 with CI [-0.5,+2.3]. Runtime was 76.67 versus 72.62
seconds per run (1.056x). Both arms passed exact seed, budget, Silver
telemetry, and zero-failure checks. The point estimate is encouraging, but
the confidence intervals include zero, so this is not a promotion result.

This online result is separate from and does not reverse the earlier offline
`ROOT_EXPLORATION_REDUCTION_REJECTED` result. It also provides no basis to
restore Sequential Halving. Any next comparison requires a new preregistered
gate.

## Artifacts

- [24-thread c=35 evidence packet](../../experiments/evidence/silver-root-exploration-c35-128-gcp-2026-08-29.json)
- Ledger-06 section 195
- [Earlier online follow-up](../../experiments/evidence/silver-root-exploration-online-gcp-2026-08-29.json)

Reviewed source SHA: `1a9c6c3b26958b3638883e15e5f85539c451eca6`.
Baseline full `origin/main` SHA: `034830df6510f1ab37ad4f053c07333fca0970c7`.
