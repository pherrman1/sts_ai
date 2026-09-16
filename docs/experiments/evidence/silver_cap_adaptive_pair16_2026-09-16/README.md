# Current #199 retained-adaptive Silver: 32k versus 128k cap

## Frozen comparison

Hypothesis: increasing the allocated Silver reuse cap from 32,768 to 131,072
may preserve more useful retained trees under the current #199 policy. The
comparison changed only `STS_SILVER_REUSE_CAP`; both arms used the same current
reviewed executable and explicit adaptive-policy settings.

Both arms used fresh paired seeds 256--271, Ironclad A0, project-fair Silver,
native OOC, Searcher2, ordinary boss budgeting, base budget 10,000, allocated
reuse, four OpenMP workers, CTM adaptive budgeting/convergence/OOC MCTS/keys
off, and exact visit-lock/rho racing off. The retained-only policy was pinned
explicitly as `STS_SILVER_ADAPTIVE=1`,
`STS_SILVER_ADAPTIVE_RETAINED_ONLY=1`, and
`STS_SILVER_ADAPTIVE_TOP_GAP=0.2932885906040268`: fresh and forced roots use
10,000 simulations; retained non-forced roots start at 500 and continue the
same tree to 10,000 unless the threshold permits stopping.

Cap-pressure exact candidates are rows with
`exact_candidate_found=1` and `allocated_nodes_before_root >= configured_cap`.
Pressure candidates rescued are those rows that also exact-rerooted; allocated
cap fallbacks are rows with `fallback_reason=allocated_cap`. This is the same
definition used by the prior cap-comparison analyzer.

## Results

| Metric | 32k | 128k |
|---|---:|---:|
| Wins | 11/16 (68.75%) | 11/16 (68.75%) |
| Mean final floor | 49.0000 | 49.1250 |
| Mean final HP | 40.2500 | 39.8125 |
| Mean seconds/run | 18.5613 | 17.7167 |
| External elapsed wall | 80.51s | 77.02s |
| Peak process RSS | 1,066,104 KiB (1.02 GiB) | 1,986,088 KiB (1.89 GiB) |
| Silver decisions | 7,681 | 7,691 |
| Silver simulations | 46,704,500 | 46,652,500 |
| Exact reroots / attempts | 5,021 / 7,262 | 5,033 / 7,272 |
| Exact reroot rate | 69.1407% | 69.2107% |
| Cap-pressure candidates | 398 | 0 |
| Pressure candidates rescued | 395 | 0 |
| Allocated-cap fallbacks | 3 | 0 |
| Valid 500-simulation stops | 3,169 | 3,185 |

Both arms had zero conversion, semantic-resolution, transaction, and knowledge
failures. Exact-lock and rho counters were zero. Every 500-simulation stop was
retained, non-forced, had inherited visits, and met the exact threshold; all
fresh roots reached 10,000. All forced/one-action roots also reached 10,000.

The 128k arm removed all three allocated-cap fallbacks and all observed
cap-pressure candidates. However, the 32k arm rescued 395 of its 398 pressure
candidates, and the arms had identical paired win outcomes: 11 both wins, 5
both losses, 0 32k-only wins, and 0 128k-only wins. The paired mean deltas
(128k minus 32k) were +0.125 floor, -0.4375 HP, and -0.8446 seconds/run.
The larger cap used 1.86x peak RSS (+919,984 KiB) while reducing simulations
by only 52,000 (0.11%) in this cohort.

## Decision

**Keep 32k for production; do not advance 128k to the next stage.** The larger
cap materially reduced cap-pressure diagnostics, but it did not materially
preserve useful trees in the outcome evidence: it changed no paired wins, did
not increase exact-reroot rate meaningfully, and 32k already rescued 99.2% of
its pressure candidates. The observed 1.89 GiB four-worker RSS is also a
substantial resource increase for no measured decision-quality gain.

This is a fresh N16 cap screen, not a general quality-equivalence proof. The
raw run logs contain `/usr/bin/time -v`, Silver telemetry, and startup
configuration; the sidecars bind the common seed block, source SHA, models,
and effective cap settings.

## Reproduction and packet

The two raw arms contain `results.csv`, its metadata sidecar, `scaling.csv`,
and `run.log`. `paired_analysis.txt` is the strict repository paired analysis;
`paired-seeds.csv`, `summary.json`, and `provenance.json` provide compact
machine-readable results and provenance.

Knowledge impact: maintained experiment evidence and current cap decision;
production remains at allocated 32,768 and 131,072 remains experimental.
