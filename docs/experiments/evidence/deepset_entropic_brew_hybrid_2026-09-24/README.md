# Experimental DeepSets CTM with Entropic Brew fallback

Status: implementation, mechanism, fixed-fixture timing, and paired OOC MCTS
engineering screen completed. The hybrid remains experimental and no default
changed.

## Provenance

- Baseline: `41c0f5af5711c452b6e133e6dc66c7756f50874c` (merged PR #303).
- Required specialist checkpoint: `W.pt`, SHA256
  `71d88a71cf7579e1092c3b3c27e000538a6aafe35bbf5228c10c15fa0edd4ace`,
  selected epoch 27. The checkpoint was already present at
  `/tmp/deepset-potion-specialist-20260923/W.pt` and was reused unchanged.
- Exported experimental native artifact SHA256:
  `a23c0f86593fef2380c3efee3cf75783bf2b5e714395ec93237fac19376bfd1a`.
- Current standard fallback artifact SHA256:
  `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.
- The exported artifact remains unqualified and does not change the default.

## Mechanism and parity

Specialist Python/native parity passed on all 31 frozen predictor fixtures at
absolute tolerance `1e-4`: maximum encoder error `7.75e-7`, maximum probability
error `4.77e-7`, and zero legal-mask mismatches. The fixtures cover acts 1/2/3,
capacities 3/5, boss/non-boss states, occupied potion counts 0/1/2/3/5, 18
Brew-labeled rows, and one Smoke row. This is numerical parity evidence, not an
offline Brew qualification.

The hybrid mechanism probe passed all 31 fixtures. Hybrid support, scalar and
prepared samples, complete RAW state, and RNG state matched the selected direct
child; routing consumed no planner RNG. Direct use of the specialist on a
pre-combat Brew input failed closed. The hybrid routed all 18 such fixture rows
to the standard sampler and 13 ordinary rows to DeepSets. Across repeated
probe calls it observed 14 unique Brew predictor states, 18 fallback
preparations, 36 fallback samples, 13 fast preparations, and 26 fast samples.
These fixture counts are deliberately not an estimate of live OOC frequency.

Why dispatch uses pre-combat inventory: the known recursive Brew trajectory
starts with Entropic Brew already visible in the initial inventory. Therefore
the wrapper routes that whole transition to standard CTM; it never switches
models after seeing generated trajectory outcomes.

## Fixed-input timing

Release benchmark command:

```sh
build/linux-gcc-release/combat_transition_runtime_probe --benchmark \
  /tmp/deepset-entropic-hybrid-specialist.native \
  selfplay/models/combat_transition_near_full_except_smoke_v2.native \
  tests/fixtures/combat_transition_near_full.jsonl 100
```

It used 10 warmups and 100 repetitions per input on the same 31-row fixture
file. The comparison now times standard and fast on the same 10 non-Brew rows
supported by fast DeepSets. Median preparation was 3,715 us for standard and
491 us for fast (7.57x); hybrid fast was 487 us on those same rows. Median
prepared sampling on those rows was 39.5 us standard and 35.0 us fast. On 18
supported Brew rows, standard preparation was 3,315 us and hybrid fallback
was 3,419 us; sampling was 41.7 and 44.4 us. Encoder calls per preparation
were 4 for standard/fallback and 3 for fast. The file's 18/31 Brew mix is
fixture-driven and heavily overrepresents the stated ~0.6% offline frequency;
neither its dispatch fraction nor a weighted runtime estimate represents OOC
search. The matched non-Brew subset shows a fixed-input preparation advantage,
while Brew preparations pay approximately standard cost.

## Checks and remaining evidence

- Release targets `combat_transition_runtime_probe` and `one_combat` built.
- Focused CTest selection `ooc_mcts_adapter|combat_transition_runtime_loader`:
  2/2 passed.
- Exporter and parity verifier Python compilation passed; `git diff --check`
  passed.
- The initial implementation review confirmed fallback metadata identity but
  did not bind the actual standard artifact bytes. Follow-up review identified
  that gap. The rebased implementation now requires the actual fallback file
  SHA256 to equal the standard artifact used by the experiment:
  `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.
- After review, source was frozen at commit
  `9ce11fdbe50f32b4b2646dd8a0803c6dc0c3f351`. Both arms then ran the canonical
  paired seeds `980000..980063` with 10,000 combat simulations, 2,048 OOC MCTS
  simulations, Ascension 0, fair play, Silver continuation, 24 threads, V4
  policy, no keys, and the same executable. Arm configurations are preserved
  under `raw/{control,hybrid}/config.json`; full per-seed game and search
  metrics are in `per-seed.csv`.
- Standard won 40/64; hybrid won 39/64. There were 7 hybrid-only and 8
  standard-only wins. The paired win-rate change was `-1.56 pp` (bootstrap
  95% CI `[-14.06, +10.94] pp`; exact discordant-binomial p `1.0`), classified
  **`OOC_HYBRID_WINRATE_INCONCLUSIVE`**. This 64-pair screen does not establish
  equivalence or justify default promotion.
- Mean whole-run elapsed time (`bestbench` `sec`) was 641.4 s standard and
  439.7 s hybrid per seed (paired change `-201.7 s`, 95% CI `[-254.8,
  -141.3]`). Mean MCTS CPU time was 139.35 s and 94.85 s respectively (change
  `-44.50 s`, 95% CI `[-69.61, -5.93]`); MCTS wall time was 462.83 s and
  276.65 s. Whole-process CPU was not separately recorded. The arms made
  slightly different numbers of decisions, simulations, imagined combats, and
  preparations, so aggregate time is runtime evidence only and is not a
  matched-work causal estimate.
- Across the hybrid's 1,135,061 preparation calls, 4,219 used standard Brew
  fallback: **0.372%**. This is the observed OOC search preparation frequency
  in this screen, in the same low-frequency range as the offline estimate;
  the seed cohort does not prove broader workload representativeness. The
  profiler summed 401 per-seed unique Brew predictor states. The children
  recorded 21 fast-path and 1 fallback support-failure queries. MCTS support
  aborts were 20 standard and 22 hybrid; every recorded reason in both arms
  was the existing `smoke_bomb` exclusion, with no new unsupported reason.
- Release targets built; focused adapter/runtime-loader CTest passed 2/2;
  Python compilation and `git diff --check` passed. Full repository CI was not
  run. No live-game test or default promotion was performed. A follow-up
  confirmation cohort should be considered separately before any promotion.

## Rebased-source verification

The task branch was rebased onto the then-current `origin/main` commit
`bb2379e844464f9bff35a6ca61e1eeaa8dbb0090` (which had advanced beyond the
previously reported `def8ffe75ca48cdc6d3b256a7e93b503ff82a40c`). The SHA guard
and focused checks below are from source commit
`9a1335a243e08ad57c59a36c95b48778fdba8b76` (`Pin exact CTM Brew fallback
artifact identity`). These checks do not replace or relabel the 64-seed
experiment above, whose executable remains frozen at
`9ce11fdbe50f32b4b2646dd8a0803c6dc0c3f351`.

- Release build passed for `one_combat`, `combat_transition_runtime_probe`,
  `one_combat_advisor`, `live_ooc_parity_test`, `test_live_ooc_policy`, and
  `live_ctm_importer_test` with OpenSSL 3.0.13.
- Focused CTest `ooc_mcts_adapter|combat_transition_runtime_loader`: 2/2
  passed. The loader check accepted the exact pinned standard fallback and
  rejected a one-byte-modified copy whose metadata was unchanged.
- Potion specialist Python/native parity passed again on the same 31 fixtures;
  maximum encoder/probability errors were `7.75e-7`/`4.77e-7`, with zero legal
  mask mismatches.
- Hybrid mechanism probe passed all 31 fixture routes and identities: 18 Brew
  fallback rows and 13 ordinary fast rows; complete RAW state and RNG identity
  were preserved.
- Fixed-fixture Release timing on the same 10 non-Brew rows: standard median
  preparation `3,977 us`, fast `520 us` (7.65x), hybrid fast `556 us`. On the
  18 Brew rows, standard preparation was `4,587 us` and hybrid fallback
  `4,470 us`. These are fixed-input measurements; timing variation from the
  earlier run does not change the paired seed evidence or its interpretation.
- Raw rebased parity, mechanism, and timing outputs are under `rebased-source/`.
  Full GitHub Actions CI was not yet available when these local checks were
  recorded.

The branch was subsequently rebased again onto current `origin/main`
`c0937d8a3756b4849ab22c1dc8caf6badeda445f` after PR #308 merged. Focused
Release checks were rerun on source commit
`74a8c8edf83e2f55633af43232ef19540850eb2b`; outputs and exact commands are in
`latest-main-source/`. All six runtime-linked Release targets built and the
focused CTest selection passed 2/2. Parity and the mechanism probe again passed
all 31 fixtures with zero legal-mask mismatches and complete state/RNG identity.
On the same 10 matched ordinary rows, standard preparation was `3,558 us` and
fast preparation `501 us` (7.10x); hybrid fast was `546 us`. On 18 Brew rows,
standard preparation was `4,780 us` and hybrid fallback `4,185 us`. These
fixed-input timings are noisy across runs but preserve the substantial
preparation advantage.

GitHub Actions could not start the `Linux GCC` job for head
`89e2089ef67d511340d0988fab8389dbdae7ee80`: GitHub reported failed account
payments or an insufficient spending limit, and recorded zero runner steps.
This is an external billing block, not a code failure. The PR is ready for
review; rerun CI after repository Actions billing is restored.

## Silver-only latest-main rebase

After PR #309, the branch was rebased onto exact `main` baseline
`7a181b3fa296fda4122033b70767fc2c0f03618c`. The adapter preserves the new
Silver-only path while retaining opt-in hybrid routing and profiler output;
the CMake changes link Crypto only to CTM-runtime targets. Release configure
and all six runtime-linked Release targets passed on this source. The focused
`ooc_mcts_adapter|combat_transition_runtime_loader` CTest selection passed
2/2. Specialist Python/native parity passed on all 31 fixtures (maximum
encoder/probability errors `7.75e-7`/`4.77e-7`, zero legal-mask mismatches),
and the hybrid mechanism probe preserved selected-child support, RAW state,
and RNG identity with 18 Brew fallback and 13 fast fixture routes.

On the 10 ordinary fixture rows supported by the fast model, standard median
preparation was `4,732 us`, fast was `534 us` (8.86x), and hybrid fast was
`661 us` (7.16x). Median prepared-sample time was `45.6 us` standard and
`37.6 us` fast. On 18 Brew fixture rows, standard preparation was `3,687 us`
and hybrid fallback `3,726 us`; sample medians were `45.4 us` and `47.5 us`.
These remain fixture timings, not an OOC workload estimate. The 64-pair
gameplay result was not rerun or relabeled.

The project-wide OpenSSL configure requirement was narrowed: CMake now allows
configuration without Crypto, and an OpenSSL-disabled Release configuration
successfully built the non-CTM `main` target. CTM runtime targets link
`OpenSSL::Crypto` when found and require its headers/library when built.
Commands and raw outputs are under `silver-only-main-source/`.

Raw machine-readable outputs are `parity.json`, `mechanism.jsonl`,
`mechanism-summary.json`, `fixed-fixture-benchmark-release.json`,
`summary.json`, and `per-seed.csv`. Compressed arm logs, action traces, support
receipts, and source/config metadata are preserved under `raw/`. Reproduce the
paired analysis with:

```sh
python3 tools/analyze_deepset_entropic_brew_hybrid.py \
  docs/experiments/evidence/deepset_entropic_brew_hybrid_2026-09-24/raw/control \
  docs/experiments/evidence/deepset_entropic_brew_hybrid_2026-09-24/raw/hybrid \
  /tmp/hybrid-summary.json /tmp/hybrid-per-seed.csv
```
