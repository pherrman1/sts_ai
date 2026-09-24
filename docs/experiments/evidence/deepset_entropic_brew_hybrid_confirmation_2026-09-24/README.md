# DeepSets CTM independent 512-pair confirmation

Status: `PREPARATION_COMPLETE_RUN_BLOCKED`. The frozen manifests, exact local
artifact hashes, analyzer, and local runtime-mechanism receipts are ready. No
canary or confirmation game seed was run. The designated GCP instance
`sts-test` does not exist in project `sts-ai-502709`, zone `europe-west3-c`.

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

These local checks do not substitute for the GCP canary or gameplay-quality
cohort.

## GCP blocker and preserved-data boundary

On 2026-09-24, `python3 tools/agent/gcp_benchmark.py status` returned exit 1:
GCP reported that
`projects/sts-ai-502709/zones/europe-west3-c/instances/sts-test` was not found.
The project instance list was also empty when checked. Since no VM exists,
there was no remote filesystem on which to inspect preserved outputs or run
`probe`; no remote files were modified and no replacement VM was created.
See [remote-inventory.json](remote-inventory.json).

Do not run the 512-pair block locally. The repository guard caps local
automated game execution at 128 seeds. Resume on the designated `sts-test`
resource after it is restored, and inspect the remote root before copying or
creating anything.

## Resume sequence when `sts-test` is available

1. Run `status` and `probe`; inventory the existing checkout and all paths in
   both manifests. Preserve any existing files. If an experiment output path
   exists, stop and resolve it without appending or overwriting.
2. Ensure the dedicated remote checkout is clean at c9 and its Release CMake
   cache points to that checkout. Transfer the frozen executable and fast
   artifact with `copy-to --expect-sha256`; do not alter the standard, V4,
   floor, or win models. Re-run both manifest checks and the confirmation
   `exact-sha-preflight` before seeds. Run the canary manifest through
   `--foreground --guard-only` for both arms before launching either canary.
3. Run both canary arms sequentially with
   `run-manifest run-manifest-canary.json C --foreground`, then H. Validate
   each result with `tools/agent/check_benchmark_canary.py` using Silver,
   10,000 combat simulations, seed 989999, A0, 24 threads, fair play,
   Searcher3 disabled, frozen Git SHA, binary SHA, and allocated Silver cap.
   Also verify each one-row result, metadata, MCTS trace, support receipt,
   action receipt, loaded CTM/V4/floor/win paths, and effective MCTS settings.
   For H, require the pinned Brew fallback path, reconciled hybrid preparation
   counters, positive preparation count, and no escaped
   `entropic_brew_requires_standard_ctm` support reason. Any canary failure
   blocks the full cohort.
   After copying their six outputs into `raw/canary/standard` and
   `raw/canary/hybrid` with the basenames documented below, run:

```bash
python3 tools/agent/check_deepset_entropic_brew_hybrid_canary.py \
  --manifest run-manifest-canary.json \
  --standard raw/canary/standard \
  --hybrid raw/canary/hybrid \
  --binary <build/linux-gcc-release/one_combat> \
  --standard-ctm <selfplay/models/combat_transition_near_full_except_smoke_v2.native> \
  --fast-ctm </tmp/deepset-entropic-hybrid-specialist.native> \
  --v4-policy <selfplay/models/ooc_strategic_tok_final.native> \
  --floor-model <models/v_rich_trees.txt> \
  --win-model <models/v_win_trees.txt>
```

4. Only after both canaries pass, run all C confirmation seeds and then all H
   seeds with `run-manifest run-manifest-confirmation.json`; do not inspect
   aggregate wins before both complete. Run the confirmation manifest through
   `--foreground --guard-only` for both arms before the cohort. The manifest
   launcher rejects stale result, metadata, log, trace, support, or action
   output paths.
5. Copy each arm’s six outputs into separate local folders named `standard`
   and `hybrid`, using these basenames: `results.csv`,
   `results.csv.meta.json`, `run.log`, `mcts.csv`,
   `mcts.csv.support.jsonl`, and `mcts.csv.actions.jsonl`. Then run the strict
   analyzer below. Keep canary outputs separate from these 512-seed folders.

```bash
python3 tools/analyze_deepset_entropic_brew_hybrid_confirmation.py \
  --standard <raw/standard> \
  --hybrid <raw/hybrid> \
  --manifest run-manifest-confirmation.json \
  --binary <build/linux-gcc-release/one_combat> \
  --standard-ctm <selfplay/models/combat_transition_near_full_except_smoke_v2.native> \
  --fast-ctm </tmp/deepset-entropic-hybrid-specialist.native> \
  --v4-policy <selfplay/models/ooc_strategic_tok_final.native> \
  --floor-model <models/v_rich_trees.txt> \
  --win-model <models/v_win_trees.txt> \
  --summary <summary.json> \
  --per-seed <per-seed.csv>
```

The analyzer emits the predeclared classification and diagnostics only after
all 512 pairs and receipts pass validation. A canary loss is never pooled into
the primary analysis.

## Preparation checks

- `tools/analyze_deepset_entropic_brew_hybrid_confirmation.py --self-test`:
  synthetic quality classifications and provenance/integrity checks, including
  binary pinning, action-receipt reconciliation, and the MCTS simulation bound.
- `tools/agent/check_deepset_entropic_brew_hybrid_canary.py --self-test`:
  synthetic single-seed provenance/mechanism case and wrong-fallback rejection.
- `tools/agent/test_gcp_benchmark_manifest.py`: schema-v2 clean environment,
  fresh output paths, dangling-symlink rejection, and schema-v1 compatibility
  (6 tests).
- No remote manifest preflight, canary, or decision-bearing cohort has run.

Knowledge impact: the GCP manifest workflow now documents clean environments
and fresh trace outputs in the maintained
[`build-and-debugging.md`](../../../knowledge-base/operations/build-and-debugging.md).
