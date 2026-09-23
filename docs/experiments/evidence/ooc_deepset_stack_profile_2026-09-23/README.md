# One-seed OOC CTM DeepSets stack timing

## Question and scope

Measure one paired seed with the current standard near-full CTM artifact and
an explicit DeepSets stack. The candidate uses the Phase-1 DeepSets survival
checkpoint with TEST survival log loss `0.060430`, the shared DeepSets maxHP/HP
checkpoint, its retrained DeepSets downstream heads, and potion checkpoint B
from the offline-rejected DeepSets potion screen. Potion is deliberately forced
in because that is the requested diagnostic. Every candidate component is
marked unqualified; the production artifact and defaults remain unchanged.

This is runtime and functional-smoke evidence only. It is not a gameplay-quality
comparison or a component promotion.

## Provenance and execution

- Source baseline: `4e4da3b154e59f193c77f972e9b5e2338c52be3c`.
- Release executable SHA256:
  `2a0e9e5a3f2f2bf845bf432cc28c15100db70bcd9c735f55058fdfbcf6727ef7`.
- After profiling, a compatibility-only change restored acceptance of the
  previously supported strong-WD survival experiment metadata; the Phase-1
  DeepSets path used here is unchanged. That final Release rebuild is
  `c89583ea5bdd97a0998785bc89d486e3cdcacfd1d79de3309fa7d19d8e173dfd` and was
  not used for the captured timings.
- Current standard artifact SHA256:
  `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.
- Candidate artifact SHA256:
  `f691131ae82671bb1feb0f539bf8f93893a1f089ec3cabef56f7e2a197b06f0e`.
- Seed: `12002032`, Ironclad A0, project-fair, keys off, stop after Act 3,
  Silver 10k, OOC MCTS 2,048 sims, one thread, V4 continuation, zero leaf
  combats. Both arms used the same executable and configuration through
  `tools/seed_guard.sh` with `STS_OOC_CPU_PROFILE=1`.
- Each arm ran twice on this one unique seed: the first pair checked the
  experiment path; the second pair captured the full profiler JSON to files.
  The tabulated profile below is from the second pair. The two result rows per
  arm matched exactly. The first execution per arm was a functional repetition;
  only the second execution's timing and full profiler output are retained in
  `profile.json`.

The exporter reconstructs Phase-1 survival normalization from the frozen
TRAIN+VALIDATION rows (458,589 rows), verifies the exact `prepared.npz`,
`prepared_manifest.json`, and split manifest SHA256 identities, and embeds the
prepared-data and resulting mean/inverse-standard-deviation hashes in candidate
metadata. It also binds every checkpoint by SHA256. The rejected potion identity
is embedded in candidate metadata as `DEEPSET_POTION_REJECTED`.

After the captured timing run, the provenance-hardened exporter recreated the
candidate as SHA256
`3f6d174950f1e4a8b042cebc78bd8525c7e112a13e31865670a39df4b0f2f586`. Its tensor
payload matches the profiled candidate byte-for-byte; only the metadata header
differs. The timings above remain tied to the original measured artifact
`f691131ae82671bb1feb0f539bf8f93893a1f089ec3cabef56f7e2a197b06f0e`.

- Prepared array SHA256:
  `a642671d0956f36405b837755cdf3dfb3c4870cde4a1d6f251046ffc8205a1c9`.
- Prepared manifest SHA256:
  `fdf1ca760c971b212e60d9cb86beec78afae6b124958aa53c56a8aea5bb92f51`.
- Float32 TRAIN+VALIDATION scalar mean vector SHA256:
  `b210c9834974eb30c80362ae10fbdeb97d15a835915bbbb2239e2b2cc81e18d9`.
- Float32 inverse-standard-deviation vector SHA256:
  `48a4f84b2de751a5e49f157b980a3fbb33f31db330e580ecc4c258a3f424be55`.

## Run outcomes

| Arm | Floor / Act | MCTS CPU | Whole-process CPU | Wall | MCTS decisions | Simulations | CTM preparations | Real combats |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Current standard | 33 / 2 | 54.14 s | 75.78 s | 75.82 s | 93 | 73,218 | 11,102 | 16 |
| DeepSets stack | 48 / 3 | 83.77 s | 118.58 s | 118.63 s | 137 | 120,399 | 20,231 | 23 |

The candidate used `64.4%` more MCTS simulations and made `82.2%` more CTM
preparations, reaching a different point in the run. Thus the larger total
runtime cannot be attributed to encoder speed. Both runs died; this one seed
does not support a gameplay-quality conclusion. Whole-process wall time was
about `56%` higher for the candidate in the captured pair.

## Profiled code parts

Times are exclusive per-thread CPU from the repository OOC profiler. `us/call`
is `exclusiveCpuSec / calls`; the final percent compares candidate to control.
The preparation bucket covers predictor-input/support preparation and composed
CTM inference; it does not isolate an individual model head.

| Code part | Standard calls / CPU / us per call | DeepSets calls / CPU / us per call | Per-call change |
| --- | ---: | ---: | ---: |
| CTM preparation + composed inference | 11,102 / 26.614 s / 2,397 us | 20,231 / 11.962 s / 591 us | **−75.3%** |
| Combat sampling and resolution | 11,418 / 1.147 s / 100 us | 20,929 / 1.159 s / 55 us | **−44.9%** |
| Real Silver combat | 16 / 21.504 s / 1,344,006 us | 23 / 34.663 s / 1,507,073 us | +12.1% |
| Leaf evaluation, exclusive | 73,217 / 7.163 s / 98 us | 120,297 / 33.073 s / 275 us | +181.0% |
| Native leaf value | 73,216 / 2.740 s / 37.4 us | 120,283 / 4.453 s / 37.0 us | −1.1% |
| V4 state network | 93,579 / 6.154 s / 65.8 us | 166,431 / 12.958 s / 77.9 us | +18.4% |
| V4 action-value network | 194,508 / 3.015 s / 15.5 us | 408,701 / 6.431 s / 15.7 us | +1.5% |
| Policy prediction | 52,976 / 3.331 s / 62.9 us | 92,442 / 6.347 s / 68.7 us | +9.2% |
| Metadata construction | 69,966 / 1.657 s / 23.7 us | 117,635 / 3.185 s / 27.1 us | +14.3% |
| Successor work | 69,875 / 1.845 s / 26.4 us | 117,559 / 3.375 s / 28.7 us | +8.7% |

The strongest speed signal is the combined CTM-preparation/inference bucket:
about `4.05x` lower CPU per call, despite replacing all component paths with
DeepSets. Total MCTS CPU still rose because the changed predictions led to more
decisions, simulations, and preparations. Do not treat one seed's per-call
numbers as a stable production benchmark.

## Checks and limits

- Release `one_combat` configure/build: PASS. Existing Silver and LTO warnings
  were emitted; no build failure.
- Candidate runtime artifact loaded and completed the guarded seed: PASS.
- Candidate export identity, component hashes, exact tensor graph, and
  `qualified:false` metadata: PASS at native load.
- Review follow-up: exact prepared-array, manifest, and normalization hashes
  matched; a tampered prepared array was rejected; the hardened re-export had
  byte-identical tensor payload to the profiled candidate; native loader checks
  passed for both.
- The initial candidate export attempt failed closed on a stale tensor graph;
  the exporter was corrected to replace all attention tensors for the selected
  groups, and the corrected candidate completed.
- No separate Python-to-native numerical parity suite or gameplay-quality
  qualification was run.

Raw per-arm benchmark rows, MCTS rows, and complete component profiler JSON are
in this directory. `profile.json` records configuration, artifact/checkpoint
identities, per-arm counters, and the raw-file hashes.

Knowledge impact: one bounded runtime experiment; default model selection and
qualification status are unchanged.
