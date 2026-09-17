# Strong-WD DeepSets survival: Stage-B speed screen

**DEEPSET_ONLINE_TRADEOFF_STOP**: median end-to-end CPU/run improved only
**1.1596%**, below the predeclared 10% continuation threshold. No 16-seed smoke
or 64-pair gameplay-quality gate ran. This is not a finding of quality regression.

## Frozen provenance

- Baseline main: `589a7a73c40e5b89e96df1ffec6a00b08c2ea9ba`.
- Independently user-reviewed, frozen execution SHA:
  `471ba9a119de2a4f6ae691329467acae1b0f70a0`.
- Linux GCC passed before freezing: run `35278049583`, job `105393291526`.
- Re-export from that clean SHA reproduced candidate SHA256
  `c870e4c10f05abbb672c2ccf9d15def046b4b9c9a2bf591b5205ef0ecaab8b7b`.
- Control SHA256: `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.
- Checkpoint SHA256: `3689593db85974f13b6313c495e7fde4ec4b4fa7d87f3442c8604a47f5e0f05b`.
- one_combat SHA256: `c0275f4ded393a6bb59aa8fec77d8f26226c95ceb629b9207c03d22e2dc7c11a`.
- Probe SHA256: `9b6da7cd4806ed51e068a3156bd74d083eb6cbfcd9d78cc67e52f9c4b2673802`.
- Original Stage-A receipt remains unchanged at
  `/tmp/deepset-online-stage-a-02/parity.json`, SHA256
  `8fc4cc9f311c9266a47c1ce87b93e066bf9da4bcab889c11c5c938ace516f5f1`.

Stage A was not rerun. Runtime/export/probe source and binary hashes stayed fixed
through all measurements. This evidence/report commit is not the execution SHA.

## Design and controls

`stage-b-plan.json` was written before the matched repetitions. `run_stage_b.py`
is the preserved external orchestration script, not a change to reviewed runtime
source. Every invocation checks frozen Git/source and artifact hashes and uses
`tools/seed_guard.sh`. No training or TEST inference occurred.

Inference uses the first 12 supported TRAIN/VALIDATION Stage-A fixtures, four
repetitions per arm, alternating AB/BA order. The unchanged native probe reports
survival, full reference sample, preparation, and prepared-sample timing; its
prior preparation/sample loops warm the path before ten component calls per row.
The pooled 48 fixture/repetition medians include state complexity variation;
raw observations and per-repetition results remain available.

Full-run timing replays PR #187's first two historical seeds, `12002032` and
`12002033`, twice per arm: **8 full-run invocations, 2 unique seeds**. Order is
AB/BA for repetition zero and BA/AB for repetition one. Both arms use the same
binary, exact 10,000-Silver combat budget, A0 Ironclad, project-fair RNG,
Searcher2 configuration (effective Silver backend), keys off, Act-3 stop,
2,048-simulation OOC MCTS, policy prior, temperature 1, cPuct 1.5,
widening 2/0.5, depth 32, visits, early stop, native leaf value, zero leaf
combats, V4 leaf policy, and the same strategic gates/model hashes as #187.
Metadata and actual loader banners pass the reused #187 validators.

Deviation: `OMP_NUM_THREADS=1` isolates individual CPU/run measurement, instead
of #187's 12-way outer parallelism. This is identical across arms and does not
change search budget; it is not throughput evidence for 12-way contention.
`/usr/bin/time` user+system seconds measures CPU, not the misleading historical
`bestbench` cpu_sec/run label, which is elapsed time. Process startup is included.

Current main includes boss-leaf implementation fixes after #187. The experiment
preserves those current-main changes, selects native leaf value in both arms,
and does not reconstruct an old runtime. Prior #187 wall-time evidence and
Stage-A correctness evidence cannot substitute for current CPU measurements.

## Results

| Metric | Attention control | DeepSets | Candidate/control |
|---|---:|---:|---:|
| Native survival median | 1.143383 ms | 0.128041 ms | 0.111985 |
| Native reference sample median | 4.435917 ms | 3.168253 ms | 0.714227 |
| Native preparation median | 4.524256 ms | 3.551819 ms | 0.785061 |
| Native prepared sample median | 0.023364 ms | 0.023288 ms | 0.996748 |
| Full-run CPU median | 50.8800 s | 50.2900 s | **0.988404** |
| Full-run CPU mean | 51.1250 s | 50.1525 s | 0.980978 |
| Full-run wall median | 50.8900 s | 50.3050 s | 0.988504 |

| Seed | Repeat | Control CPU s | Candidate CPU s |
|---|---:|---:|---:|
| 12002032 | 0 | 40.85 | 40.56 |
| 12002033 | 0 | 60.83 | 60.02 |
| 12002032 | 1 | 40.93 | 39.86 |
| 12002033 | 1 | 61.89 | 60.17 |

Native survival medians per repetition are control 1.145421, 1.144134,
1.138082, 1.143383 ms versus candidate 0.129026, 0.129192, 0.126634,
0.126757 ms. Full-run repeated CPU differences are far below the 10% threshold.
Native medians are not end-to-end speed estimates.

All eight full runs exited zero and passed exact metadata/load checks. Repeated
non-time outcome fields match within each arm/seed. Both historical seeds were
won in both arms; on seed 12002033 ending HP is 46 control versus 49 candidate.
This is timing-only descriptive information, not a quality gate or a win-rate
estimate. No bootstrap quality interval was computed.

Support telemetry matches by seed: one Smoke fallback on seed 12002032, none
on seed 12002033, zero continuation-limit aborts in all runs. Actual MCTS
visits/samples differ as allowed by differing survival predictions; configured
budgets are identical. All native prepared/reference state/RNG comparisons pass.

The timed probe's historical V1 smoke validator reports 68 copy-through flags
per repetition **in each arm**, with all six other invalid counters zero.
Its copy-through whitelist omits V2 gold/deck changes, so these are not evidence
of a candidate-only regression or a new full V2 validity qualification. The
existing warning is disclosed rather than silently repaired after freeze.

## Decision and limitations

Stop at the speed gate. The two-seed repeated screen is small, but its observed
median CPU reduction is 1.1596%, not the required 10%. No new fresh gameplay
cohort was declared or launched because that gate stayed closed. The two reused
historical timing seeds must never be relabelled as the fresh 16/64 quality cohort.
No claim of gameplay equivalence, non-inferiority, or default promotion follows.

Inference: making only survival cheaper saves little in this full-run profile;
prepared sampling and real combat still consume time. The measured savings do
not justify proceeding under this contract. This does not prove there can be no
benefit under other profiles, hardware, or workloads.

## Raw evidence

Original directory:
`/home/philippherrmann/sts_sweep/runs/deepset-survival-online-471ba9a-stage-b`.
`manifest.json` hashes every original file and names byte-identical tracked
copies. Candidate binary remains external. Full ambient-environment command
receipts remain local; the public-to-repository plan, runner, logs, model-load
metadata, CSVs, support telemetry, time outputs, and per-run receipts retain the
explicit experimental configuration without copying unrelated environment values.

Raw result SHA256: `a2f78e724189bc700c56558b3b13113fcc8d2334a916b331ff0500bb26abeb19`.
The result receipt retains `gameplayGateRun:false` and the unrounded CPU ratio.
Final evidence commit is recorded separately in PR #220. Knowledge impact:
negative bounded online speed result and current research status; no default,
support, model, or runtime-code change after review.
