# Exact 10k Silver: 32k versus experimental 128k lazy GC

## Accepted comparison and frozen configuration

Hypothesis: retaining more orphan transposition history may improve decisions;
stale history may also hurt. One variable: node cap 32768 versus 131072, both with
lazy GC and dynamic dedup at frozen code
`2b29e9723a00b9dc6fcea45507e4dcf86c968cde` (Linux GCC CI passed).
Same release executable/hash and native model artifacts, seeds 0–15 paired,
A0, project-fair RNG, keysOFF, ordinary exact 10000 simulations at every root
(including bosses), allocated reuse, adaptiveOFF, learned leafOFF, OOC MCTS OFF,
four OpenMP workers. Neither frozen teacher/model generation nor live OOC MCTS
is used. Only the cap and output paths differ; sidecar equality is verified
with those two fields excluded. No code change or cap promotion in this run.
Earlier preserved flat1k parity and forced-END_TURN stress fixtures do not meet
this exact 10k whole-run cap-comparison configuration, so new data was needed.
Seeds0–15 were also used by the earlier 1k checks: this is an exploratory cohort,
not fresh prospective validation. The sample and decision rule were fixed
before launch. No additional seeds/arms were run after seeing outcomes.

## Results

| Metric | 32k lazy GC | 128k lazy GC |
|---|---:|---:|
| Wins |11/16 (68.75%)|13/16 (81.25%)|
| Mean final floor |48.625|50.1875|
| Mean final HP |36.5|34.0|
| Mean seconds per run |30.5031|30.8804|
| Decisions |7,392|7,814|
| Exact reroots |4,823|5,354|
| Cap-pressure exact candidates |1,740|3|
| Pressure candidates rescued |1,526|3|
| ALLOCATED_CAP fallback |214|0|
| Maximum allocated nodes |47,390|138,829|
| Peak process RSS (KiB) |1,130,460|2,622,576|
| Peak process RSS (GiB) |1.0781|2.5011|

Both producer exits 0. Both arms have zero conversion, semantic-resolution,
transaction and knowledge failures in all 414/427 per-combat telemetry records.
All15,206 diagnostic rows confirm configured cap/mode and exact 10000 added
simulations. Every seed's diagnostic prefix is identical (excluding configured
cap) until a 32k pressure decision; all first differences occur at allocated
count >=32768. Diagnostics are not a complete action/state trajectory trace.
Four seeds have identical complete non-timing result rows (1,7,9,13).

Paired wins: both win 11, both lose 3,32k-only 0,128k-only 2 (seeds2 and8).
Seed 2 goes floor 50 loss→floor 51 win; seed 8 floor 27 loss→floor 51 win.
Point estimate +12.5pp. Existing deterministic paired-bootstrap 95% interval
[0,+31.25]pp; exact two-sided discordant-pair test p=0.5. With only two
discordant observations, the bootstrap boundary at zero is not evidence of
established superiority. Floor difference +1.5625, bootstrap CI[0,+4.5625].
Mean final HP decreases 2.5; final HP mixes winners and losses and is not a
matched surviving-state quality or regret measurement.

RSS is for the whole four-worker process, not one searcher. The128k arm uses
about 2.32 times peak process memory (+1.423GiB). Search batches may overshoot
the configured cap before reroot. Resource figures are observed Linux process
peaks, not universal memory limits. Wall time145.26s versus142.65s is
scheduler/trajectory dependent; run-average time differs+0.3773s and the arms
complete different numbers of combat decisions, so this is not a fixed-work
speed claim. Sequential32k first execution is an order/thermal limitation.

## Decision

Exploratory positive outcome signal and clearly fewer cap fallbacks, with a
substantial memory cost. No demonstrated win-rate superiority from 16 paired
seeds, no root-regret measurement and no cap promotion. Keep production 32k
and experimental 128k opt-in. A promotion decision needs fresh matched evidence,
practical concurrency/RAM assessment and qualification of the frozen 32k
teacher/model dependencies; this packet does not requalify them.

## Reproduction / packet

`provenance.json` records exact commands, clean-source SHA, identical binary
hash, explicit environments, model hashes, seeds and raw exit codes.
`run.py` records the original guarded runner (its fixed build destination is
non-overwriting; do not rerun into existing outputs). `analyze.py` is seed-free:
`python3 docs/experiments/evidence/silver_cap_pair10k_16_2026-09-15/analyze.py`.
It validates seed/schema/configuration/budget/health and diagnostic prefixes.
Paired analysis is repository-root `paired_analysis.py`, with32k asA/128k asB.
Raw CSV, sidecars, compressed decision CSV/logs and external time-v observations are
preserved. Artifact hashes bind the packet; code and models remain frozen.

Knowledge impact: exploratory cap-quality/resource status and ledger evidence;
production/default/model/support contracts remain unchanged.
