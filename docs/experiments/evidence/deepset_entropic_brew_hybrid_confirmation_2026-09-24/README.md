# DeepSets CTM independent 512-pair confirmation

Status: `OOC_HYBRID_QUALITY_CONFIRMED`. The frozen 512-pair confirmation and
both mechanism/provenance canaries completed on 2026-09-25 using the local
seed-guarded four-by-128 transport. The designated GCP instance `sts-test` was
unavailable during preparation; the local run changed transport only.

## Frozen protocol

- Source SHA: `c9ecfb2041f8061d89bd728b8dccded2e8e12adf` (PR #307 merge).
- Canary: one seed, `989999`, both arms, mechanism and provenance only.
- Confirmation: paired seeds `990000..990511`, 512 rows per arm.
- Both use Ascension 0, 10,000 Silver combat simulations, Act 3 stop, no
  keys, 24 threads, and 2,048 V4-policy OOC MCTS simulations.
- Arm C loads standard Attention CTM. Arm H loads DeepSets and pins the
  standard artifact as its Entropic Brew fallback. The clean process
  environment makes their model path and trace path the only shared-variable
  differences; H has the one additional fallback path.
- The `980000..980063` screening block is excluded from every confirmation
  statistic.
- Gate: paired whole-run win difference H minus C; 500,000 paired bootstrap
  resamples with NumPy PCG64 seed `20260924`; two-sided percentile 95% CI;
  non-inferiority margin `-5.0 pp`. Runtime metrics remain descriptive.

The machine-readable protocol is in [confirmation-plan.json](confirmation-plan.json).
Exact manifests are [run-manifest-canary.json](run-manifest-canary.json) and
[run-manifest-confirmation.json](run-manifest-confirmation.json). Hashes and
build details are in [artifact-sha256.txt](artifact-sha256.txt) and
[build-provenance.json](build-provenance.json).

## Evidence already prepared

- Local Release `one_combat` was built at frozen source SHA c9; binary SHA256
  is recorded in the manifest. C and H are configured to use that same binary.
- Local standard, fast, V4, floor, win, and checkpoint artifact hashes were
  rechecked against the plan. No export or retraining was performed.
- The exact standard fallback pin check passed.
- The hybrid runtime mechanism probe passed all 31 fixtures (13 ordinary,
  18 Brew), including selected-child/RNG/RAW-state behavior and fail-closed
  direct fast-artifact Brew support.
- Release CTests `ooc_mcts_adapter`,
  `combat_transition_runtime_loader`, and
  `combat_transition_near_full_artifact` passed 3/3.
- No C++ behavior was changed.

The source and executable used for gameplay remain the frozen c9 source and
binary. No gameplay source/binary, arm, model, seed, clean-environment
treatment variable, or statistical setting changed. `OMP_NUM_THREADS=24`
remained pinned for both arms.

## Execution result

The previously retained C/H canary outputs for seed `989999` passed the
mechanism/provenance validator after the metadata correction. The local
four-by-128 runner uses a fresh output root and also executed a new C/H pair at
`989999` before chunk C1; those run-local outputs passed the same gates and
are the canary files retained in the run directory. This repeated canary was
outside the 512-pair cohort and none of its outcomes entered the analysis. The
c9 metadata expectation was corrected so `models.policyNet="off"` is
accepted; independent V4 policy-load and effective `leafPolicy="v4"` checks
remain enforced.

The 512-pair run used seeds `990000..990511`, OMP 24, and the unchanged
500,000-replicate paired bootstrap and −5 pp non-inferiority gate. It ran in
eight normal guarded invocations, in order `C1,H1,C2,H2,C3,H3,C4,H4`; each
invocation covered 128 seeds. The launcher externally limited the run to CPUs
0–7; per-chunk receipts do not encode CPU affinity. This run-level detail is
preserved in [local-runtime-provenance.json](run-evidence/local-runtime-provenance.json).
Both arms retained `OMP_NUM_THREADS=24`. Every invocation used the frozen c9
`tools/seed_guard.sh`; no guard bypass or seed count increase was used.

Results: C won 277/512 and H won 292/512. The paired H−C win difference was
`+2.9297 pp`, with paired bootstrap 95% CI `[-1.7578,+7.6172] pp`. The lower
bound is strictly above the frozen `−5.0 pp` margin, so the predeclared result
is **`OOC_HYBRID_QUALITY_CONFIRMED`**. There were 208 both-win, 151 both-loss,
84 H-only, and 69 C-only pairs; the exact two-sided discordant-binomial
`p=0.2576`. This confirms the predeclared non-inferiority gate for this cohort;
it does not claim superiority or change the default.

The full chunk outputs, logs, transport receipts, and merged arm files remain
in the ignored workspace path
`build/local_deepset_hybrid_confirmation_7069518/`. The compact
decision-bearing artifacts are committed under [`run-evidence/`](run-evidence/):

- [summary.json](run-evidence/summary.json) — SHA256
  `0afa5319c21706ef380b76825035514c76dbe694bbafa4ed6293a75ce48b98ce`.
- [per-seed.csv](run-evidence/per-seed.csv) — SHA256
  `4ac503913f7db42bc7783440fc7a743cf348a1880dcb346a9ba8ac9069c29100`.
- [merge-report.json](run-evidence/merge-report.json) — SHA256
  `fef01e97b6eba1b0a8fa4394676c2081c913f35780a12c14747abe1dc8cdb282`.
- [canary-validation.json](run-evidence/canary-validation.json) — SHA256
  `886dae715b04df441c06ee160d36778647929d3e4958553bef7a3e7bef19f60d`.
- [transport-completion.json](run-evidence/transport-completion.json) — SHA256
  `f92a045e456836a85f1a3b0e2ed86964d850134278e523544a76368da8441a22`.
- [local-runtime-provenance.json](run-evidence/local-runtime-provenance.json) — SHA256
  `978b00a6a30e8b847397ff4dd935a292acc08de146f353288254112f46ac396b`.

`confirmation-plan.json` and both run manifests remain the frozen preparation
snapshot; their recorded GCP blocker describes the preparation-time status.

The run's `transportToolGitSha` value `7069518b5da3b38f4bac562a9b724de158814583`
is the repository base HEAD recorded at launch; it does not identify the
uncommitted local transport helper contents. The analyzer, merger, and runner
SHA256 values as used for the run were respectively
`d2d8731b5dc146b9288c92959b232ce38245906640396c83d6ab9a7f755c9e27`,
`7783a7505956be8d39a1b51dbd9d8629d9463be3189b1c90dc5f0e6844d64ecf`, and
`b75fc06d8bd2d20b87098218066e4878143b8111ea706c6027c425311d5ce409`. The
PR changes the merger/runner guard lookup to read the pinned c9 guard directly,
so their current source hashes are now
`d3153c98bb48026a865501afaa71008ba8383bbca45876166913c9721d653d23` and
`3a38ff3d2dadd45c6342d49fcd5ee0e943cb9d60e7dbe7d71c6d8ef1bbfbff15`.
This compatibility-only correction lets the helpers validate the frozen c9
guard even when the current-main guard has advanced; the experiment itself
used the same pinned c9 guard. The analyzer hash and working-tree diff hash are
also in the local runtime provenance record; per-chunk receipts bind the
launch base SHA, not helper-file contents.

## Preparation checks

- `tools/analyze_deepset_entropic_brew_hybrid_confirmation.py --self-test`:
  synthetic quality classifications and provenance/integrity checks, including
  binary pinning, action-receipt reconciliation, the MCTS simulation bound, and
  a mixed paired-win contingency table with both concordant and discordant rows.
- `tools/agent/check_deepset_entropic_brew_hybrid_canary.py --self-test`:
  synthetic single-seed provenance/mechanism case and wrong-fallback rejection.
- `tools/agent/test_gcp_benchmark_manifest.py`: schema-v2 clean environment,
  fresh output paths, dangling-symlink rejection, and schema-v1 compatibility
  (8 tests), including exact-checkout guard binding and preserved generic-run
  behavior.
- Analyzer self-test and canary-validator self-test both passed after the
  metadata correction. Both preserved canaries passed validation, all eight
  guarded chunks exited zero, the strict merger passed, and the frozen paired
  analyzer completed.

Knowledge impact: the independent confirmation result is recorded in the
experiment ledger; the experimental hybrid remains opt-in and no runtime
default changed.
