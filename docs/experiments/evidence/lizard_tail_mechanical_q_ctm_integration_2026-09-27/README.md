# Active Lizard correction in the DeepSets/Brew CTM stack

This packet records the bounded integration of the frozen PR #330 active
Lizard correction into the PR #351 DeepSets plus standard-Attention Brew
fallback stack. It does not repeat either qualification cohort.

## Baseline and frozen inputs

- Task's named baseline: `812ce0235e67aa9832142f69c6c8fc89d6875372` (PR #330
  merge).
- Checkout baseline used here: `be84fd934131395e87858195d74c169146a36ccf`,
  a later `main` descendant that includes the merged DeepSets/Brew
  confirmation work.
- DeepSets tensor payload SHA-256:
  `429f9dc018a6b9de231657df4aba787bddc2de2e4cecb2e7989e167c37813139`.
- Gate 1 integration-candidate artifact SHA-256:
  `40743022491de57d864dc911b3db1bd7bb7dceb9d60f2481c55145d66864aa25`.
  The exact binary is included as
  [`integration_candidate.native`](integration_candidate.native) so a clean
  checkout can replay Gate 1. Its metadata says
  `status=integration_candidate`, `qualified=false`, `defaultChanged=false`,
  and `defaultForOocMcts=false`; it is a non-production test input. It is a
  metadata re-export of the exact qualified tensors. Gate 3 would package the
  same payload with production metadata only after Gate 2 passes.
- Standard Attention Brew fallback SHA-256:
  `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.
- Frozen Lizard candidate manifest SHA-256:
  `15da76f4ab3d8bdf74f04f17176fcdc4f6a1fe5ea792497a2e3cf12b29964617`.
- Frozen q/r artifact SHA-256:
  `9f8fb965b24fbd8da1f9600fc9ca0f243e5e9069c47067123c88e36e9f5ebcf9`;
  frozen r-model SHA-256:
  `fbf29bf742e3c40b18a358386509a74ced54e97a2a7e760ff988de5c14a335a8`.

The digest in the pasted request for the standard fallback has 62 hex
characters and is not a SHA-256. The tracked artifact at the specified path
was rehashed and its valid 64-character digest above is used for the canary.

The candidate keeps `q = 1 - pOrdinaryWin` and the frozen learned
`r(pReserveWin)`. For a consumed-win sample, T2 sets both the stripped
pre-state and predictor input `curHp` to `floor(pre.maxHp/2)` before running
the existing conditional heads. The usual maxHP, signed-HP, potion, and relic
heads then sample the post-state. Gate 1 directly compares each forced T2
child against a native child prepared from the stripped state and predictor
with that transformed HP; the full serialized post-state and RNG engine must
match. The returned Tail remains present with `data=0` and its relic bit
preserved. Active Lizard plus Entropic Brew remains unsupported; Fairy Potion
and Mark of the Bloom retain their existing exact-path boundaries.

## Gate 1 — deterministic native parity

**PASS after correction.** The verifier covered all 320 frozen Stage-C rows
and checked native support, ordinary/reserve survival probabilities, q, r,
all three class probabilities, the Python-reference T2 head-input HP, Tail
state, HP legality, potion count, and RNG/state invariants on all three forced
outcome branches per row. The T2 branch is supported after transforming both
conditional-head inputs; its sampled post-HP is not forced to half the newly
sampled maxHP. Consumed wins retain Tail with `data=0` and the original relic
bit. There were zero support and semantic mismatches. Maximum absolute
probability errors were:

| Value | Maximum absolute error |
| --- | ---: |
| `pOrdinaryWin` | 5.364418029785156e-07 |
| `pReserveWin` | 3.5762786865234375e-07 |
| `qTailConsumed` | 5.364418029785156e-07 |
| `rWinGivenConsumed` | 3.884912700424792e-07 |
| three class probabilities | 5.364418029785156e-07 |

All are below the predeclared `1e-4` tolerance. The eight-row dispatch fixture
passed for ordinary DeepSets, Brew-to-Attention, active Lizard, active Lizard
with a later relic, spent Tail on the ordinary native path, Lizard plus Brew
fail-closed, Fairy's existing fail-closed boundary, and Mark of the Bloom
existing support. Dispatch metrics were 1 fallback preparation, 6 fast
preparations, 3 Lizard preparations, 2 Lizard samples, 2 Lizard support
failures, and 9 boundary exclusions; repeated calls to support, forecast,
prepare, and the prediction probe contribute to the exclusion/failure counters.

The existing DeepSets/Brew mechanism fixture passed all 31 rows, retaining
13 ordinary DeepSets and 18 standard Attention fallback routes, 26 fast
samples, and 36 fallback samples. Complete RAW/RNG and scalar/prepared
identity held on every row. Its input is
`tests/fixtures/combat_transition_near_full.jsonl` (SHA-256
`d464bcc043bd3f9964a2300696f05356a602eb3fb98f01070800cb025e9226ee`).
Focused CTest selection passed 5/5: near-full sampler self-test, native
fixture, active-Lizard fixture, OOC MCTS adapter, and runtime loader. The
runtime probe SHA-256 is
`1ed808cfa04b9dbdddbae256d410f664b252690613e5d656253c526ee69ec692` and
`one_combat` SHA-256 is
`63975e203b240f987a1b87fac8778fb25f434cfa5e23834bfda1cd5a7e6fc7ee`.
Python syntax checks and `git diff --check` passed.

Files `native_parity.json`, `deepsets_brew_fixture.jsonl`, and
`deepsets_brew_fixture.metrics.json` contain machine-readable outcomes. The
320 paired states, selection, manifest, candidate binary, and q/r artifact are
copied with their original hashes into this packet. The Gate 2 frozen manifest
records the original `/tmp` candidate path; its candidate hash matches the
tracked `integration_candidate.native` exactly. The frozen Python T2 reference
`tools/combat_transition_lizard_minimal.py` is pinned in the parity report at
SHA-256 `2465502731defca4ace9cfcd84eb222a8330b206297f50aaba55e1ad34e584eb`;
the q/r predictor `tools/combat_transition_lizard_mechanical_q.py` is pinned
at `fcee01d2319d40719cddcb6a6c81ff888ea2720b873d7223b7abe0683192bdbf`, and
the source assignment at
`752fd7cc3769a065478c0045593944a0822e24909db7cd374397a0f464ae964a`.

### Gate 1 revalidation after current-main advance

Before handoff, the branch was re-synced with fetched `origin/main`
`31571bbd406f7bc0435d3010fc14cfee6897ff33`, which includes the separate fresh
Stage-C Lizard qualification. The focused Release build succeeded:

```bash
cmake --build --preset linux-gcc-build --target combat_transition_runtime_probe one_combat --parallel 2
```

The rebuilt `combat_transition_runtime_probe` SHA-256 is
`1ed808cfa04b9dbdddbae256d410f664b252690613e5d656253c526ee69ec692`;
`one_combat` SHA-256 is
`8c4f87c4339690541dd7f0585ba235d9b419ae409e7dd0e8f63e80d9817cf845`. The
320-row parity verifier was rerun against the merged source:

```bash
python3 tools/verify/combat_transition_lizard_runtime_parity.py --probe build/linux-gcc-release/combat_transition_runtime_probe --fast docs/experiments/evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27/integration_candidate.native --standard selfplay/models/combat_transition_near_full_except_smoke_v2.native --output docs/experiments/evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27/post_merge_native_parity.json
```

It wrote
[`post_merge_native_parity.json`](post_merge_native_parity.json). It again
reported zero support or semantic mismatches, maximum errors below `1e-4`,
320/320 conditional T2 child identity checks, and all eight dispatch fixtures
passing. The existing 31-row Brew/DeepSets fixture was also rerun:

```bash
build/linux-gcc-release/combat_transition_runtime_probe --hybrid docs/experiments/evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27/integration_candidate.native selfplay/models/combat_transition_near_full_except_smoke_v2.native tests/fixtures/combat_transition_near_full.jsonl > /tmp/lizard-integration-postmerge-brew-rows.jsonl 2> /tmp/lizard-integration-postmerge-brew-metrics.json
```

All 31 rows passed, with 13 ordinary DeepSets and 18 standard-Attention
fallbacks. The rerun output was byte identical to the recorded
`deepsets_brew_fixture.jsonl`, and its counters matched the recorded metrics.

The focused regression command passed all 5 tests:

```bash
ctest --test-dir build/linux-gcc-release --output-on-failure -R '^(combat_transition_near_full_sampler_selftest|combat_transition_native_fixture|combat_transition_active_lizard_fixture|ooc_mcts_adapter|combat_transition_runtime_loader)$'
```

No gameplay seeds were rerun. This validates Gate 1 and the forced-relic test
fix on the re-synced source; it does not repair the spent Gate 2 canary.

## Gate 2 — forced-Lizard integration canary

**FAIL — the treatment did not exercise active Lizard.** The exact eight pairs
(`991000..991007`) completed in both arms, but Gate 2 requires nonzero treatment
Lizard preparations and samples. All eight treatment records had
`activeLizardEnabled=true` and both `lizardPreparations=0` and
`lizardSamples=0`. The canary cannot establish active-Lizard integration.

The frozen run manifest is
`gate2_failed_canary_2026-09-27/gate2_frozen_manifest_final.json` (SHA-256
`bb0e964bb2b19af1f18559c51b3d1b094c9f5bb538e47d2bdc0c089c9d8900b3`); it pins
the executable SHA-256 `63975e203b240f987a1b87fac8778fb25f434cfa5e23834bfda1cd5a7e6fc7ee`
and executable source SHA `bcdb92e66043483681b2cd3259c97edbefed23cb`. The 16
run result rows, sidecars, traces, process logs, preflight records, guard-only
checks, and a hash-indexed summary are preserved under
`gate2_failed_canary_2026-09-27/`.

| Seed | Control W/F/HP (s) | Treatment W/F/HP (s) | Treatment Lizard prep/sample |
| ---: | :--- | :--- | :--- |
| 991000 | 0 / 50 / 0 (89.962) | 0 / 50 / 0 (89.562) | 0 / 0 |
| 991001 | 0 / 25 / 0 (30.691) | 0 / 25 / 0 (30.683) | 0 / 0 |
| 991002 | 1 / 51 / 65 (135.632) | 1 / 51 / 65 (134.996) | 0 / 0 |
| 991003 | 1 / 51 / 43 (119.835) | 1 / 51 / 43 (120.532) | 0 / 0 |
| 991004 | 0 / 42 / 0 (68.858) | 0 / 42 / 0 (68.854) | 0 / 0 |
| 991005 | 1 / 51 / 41 (97.734) | 1 / 51 / 41 (86.563) | 0 / 0 |
| 991006 | 1 / 51 / 58 (145.593) | 1 / 51 / 58 (144.349) | 0 / 0 |
| 991007 | 1 / 51 / 13 (81.017) | 1 / 51 / 13 (80.420) | 0 / 0 |

`W/F/HP` means win flag, final floor, and ending HP; parentheses contain run
seconds. These outcomes are descriptive only and do not compare the active
Lizard correction because the forced relic was not active in either arm. All
16 commands returned zero and produced their result, sidecar, and trace files.
Across the runs, `unsupportedCombats`, `mctsSupportAborts`, hybrid fast and
fallback support failures, and Lizard support failures were zero. The standard
Brew fallback was prepared 712 times in each arm of seed `991002` and zero
times in the other runs. Control and treatment win/floor/HP outcomes matched on
all eight seeds.

### Gate 2 diagnosis and run history

`runFullRunOOC` inserted a forced relic with `data=0` for every relic. The
simulator instead initializes a newly acquired Lizard Tail with `data=1` in
`GameContext::obtainRelic`; battle setup copies that value into the player's
active-relic flag, and the CTM wrapper intentionally recognizes only
`LIZARD_TAIL` with `data=1`. Thus `STS_FORCE_RELIC=LIZARD_TAIL` logged as set but
did not create an active Tail. A narrow initialization helper now preserves
zero-initialized data for ordinary forced relics and uses `data=1` for forced
Lizard Tail. The active-Lizard CTest fixture now checks both the forced relic
record and its battle-start flag; the focused CTest set passed 5/5. The
post-correction `one_combat` SHA-256 is
`3e8eb01c41ec7615d99b87003ae71fe5068430f083b270ea41c9a974af269b22`. This
correction was made after collection; no gameplay seed was rerun.

Two setup-only preflights caught stale historical Silver variables before any
gameplay seed started: 16 attempts with removed `STS_SILVER_TELEMETRY=1`, then
16 attempts with the removed `STS_SILVER_REUSE_CAP=32768`. Both groups exited
before `bestbench` and produced no result rows or sidecars. The final manifest
uses telemetry `0` and leaves the native fixed reuse-cap override unset. The
corrected final cohort is the single set of eight fixed pairs above; no
replacements or extensions were run.

Gate 1 still passes. **Gate 3 was not run:** this Gate 2 failure blocks default
promotion, the production artifact package step, and the two default-plumbing
smokes. `STS_OOC_MCTS` remains off by default; the Lizard correction remains
opt-in and the standard Attention Brew fallback remains explicitly configured.

## Gate 3 — default plumbing

**Not run; blocked by Gate 2.** The exact DeepSets payload was not re-exported
as a production default, no default model-selection code changed, and the two
no-model-environment plumbing smokes were not run. OOC MCTS remains globally
off unless the caller sets `STS_OOC_MCTS=1`.

The exporter now emits only `integration_candidate` metadata, with qualification
and default flags false; its `--production` option was removed. Production
packaging and default wiring remain reserved for Gate 3 after a valid active-
Tail Gate 2 canary.

## Knowledge impact

The environment-variable reference records both forced-relic initialization
semantics and `STS_OOC_MCTS_ACTIVE_LIZARD`; the exporter is restricted to
non-production metadata until a valid Gate 2 canary. The current-research page
and experiment ledger record the failed integration canary. Current baselines
remain unchanged because Gate 3 did not qualify a default. Stable Lizard
sampling behavior is documented at the sampler and OOC adapter entry points.
The existing PR #330 and PR #351 evidence remains the scientific qualification;
this packet records deterministic integration correctness, the failed canary,
and its harness correction only.
