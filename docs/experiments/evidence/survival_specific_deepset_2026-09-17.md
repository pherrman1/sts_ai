# Survival-specific DeepSets: pre-fit implementation handoff

Status: **SMOKE_PASSED_NOT_QUALIFIED**. The full fit has **not run**.
Baseline: `be5b6ac2c9914b0a56244f2522b7573f81360067` after reconciling the
original `fe45572499d7fe5145b1c4f8bc30521cbcdca41e` handoff with current
`origin/main` on 2026-09-17. The merge did not alter the experiment contract.

## Accepted experiment

Test whether the corrected PR #205 DeepSets encoder, warm-started and trained
on all survival TRAIN combats including deaths, can match the TRAIN-only
Attention survival specialist. Reuse exactly the existing 94,424-parameter
encoder and its bound scalar normalization; attach only a fresh 65-parameter
`Linear(64,1)` survival head. No auxiliary heads or losses enter the model.

The fixed recipe is FP32 AdamW, batch 512, seed 20260912, encoder LR 1e-4,
head LR 1e-3, weight decay 1e-4, gradient clip 1.0, plain unweighted binary
cross-entropy with logits. Run at least 12 and at most 40 epochs, stopping
after six completed epochs without a new strict VALIDATION NLL minimum.
Select the earliest strict minimum. Do not rescue-tune or extend the cap.

Relative acceptance limits are overall NLL +2%, Brier +5%, observed-death
NLL +10%, and low-pre-HP NLL +10%. Finite logits/probabilities, probabilities
in [0,1], exact population binding, and zero TEST inference are mandatory.
AUC is diagnostic. Only a quality GO permits the 512-row CPU speed screen.
That screen measures Python encoder and complete survival forward latency,
not native/OOC speedup. No runtime promotion is authorized.

## Verified preflight and smoke

- Existing Codex-app-managed worktree, initially clean and detached; no new
  worktree created. Worktree preflight/check and environment doctor passed.
- CUDA available: RTX 3060 Ti, PyTorch 2.5.1+cu121; TF32 disabled, FP32 fit.
- PR #205 checkpoint and result-receipt SHA256 match the accepted hashes.
- The frozen corpus, original source split, prepared arrays/manifest/spec,
  survival cache, and TRAIN-only Attention checkpoint were hash-verified.
- TRAIN: 408,183 rows / 19,986 sources. VALIDATION: 50,406 / 2,496.
  Original source memberships match exactly; splits are disjoint.
- TEST: 0 newly encoded, 0 inferred, 0 scored. Existing TEST metadata and
  labels are loaded only for integrity/split binding, not model evaluation.
- Attention VALIDATION NLL reproduces as **0.05949442461133003**, versus
  historical **0.05949442833662033** (absolute error about 3.73e-9).
- Exact initial encoder state and normalization hashes are in the JSON
  receipt. No scalar statistics are recomputed.
- 32-real-TRAIN-row backward smoke: BCE **0.7401845455169678**;
  encoder gradient norm **2.8184878826141357**, head **2.1365160942077637**.
  Both are finite/nonzero. Optimizer scope is exactly encoder plus head.
- Two further TRAIN batches of 512 and a 512-row VALIDATION evaluation
  succeed. Candidate state is restored exactly after smoke; fit creates a
  fresh optimizer. These smoke updates are not a trained candidate.

Raw receipt:
`/home/philippherrmann/sts_sweep/runs/survival-specific-deepset-20260917-smoke-final/results.json`.
The compact [JSON evidence](survival_specific_deepset_2026-09-17.json) records
input hashes, population IDs, normalization provenance, optimizer parameter
names, full reference metrics, and smoke results.

## Checks and completion boundary

Run the focused suites:

```sh
python3 -m unittest tools.test_combat_transition_survival_deepset_train tools.test_combat_transition_deepset_survival tools.test_combat_transition_deepset_distill -v
python3 tools/combat_transition_survival_deepset_train.py smoke --output /absolute/new/external/smoke-directory
```

The trainer suite covers a synthetic update/metrics path, the real encoder's
gradient and normalization contract, optimizer scope, explicit TEST/mixed
split rejection, strict checkpoint ties, the stopping floor/patience, and
quality rejection. It is registered with CTest for Linux GCC CI.

Final focused outcome: 17 tests passed; focused CTest passed 1/1 (1.73 s)
at the original implementation SHA. Post-merge focused checks and CI remain
required before the frozen fit SHA is finalized.
`cmake --preset linux-gcc-debug-ccache`, worktree checks, environment doctor,
and `git diff --check` passed. Repository health reports two pre-existing
broken documentation links: `combat_budget_diag_2026-09-15/README.md` and
`deepset_survival_lbfgs_2026-09-17.md`. Both links and absent targets exist
at the baseline; they are not repaired in this scoped change.

Initial synthetic tests failed because fixtures omitted required `ids`;
the fixtures were corrected and tests rerun. Direct inspection also found
that explicitly requesting split 2 could evade the generic batch guard;
it now rejects every split except TRAIN/VALIDATION, with a regression test.

**Blocker:** independent implementation review has not passed. Native
reviewer delegation failed with `Provide either message or items, but not
both`; no reviewer was created. The implementation does not bypass the
repository's pre-expensive-run review boundary. This draft PR is therefore
an implementation/preflight handoff, not completed scientific qualification.

After independent review passes, freeze the reviewed implementation SHA
and run from its clean worktree:

```sh
python3 tools/combat_transition_survival_deepset_train.py fit --experiment-sha "$(git rev-parse HEAD)" --output /absolute/new/external/fit-directory
```

Not run: full fit, selected-checkpoint evaluation, Stage B, TEST, native
export, C++ changes, OOC/gameplay/MCTS, runtime replacement, or promotion.
Selected epoch, stopping reason, final checkpoint hash, full validation
history, final scientific decision, and timings remain unavailable. No
GO/REJECTED conclusion is inferred from smoke. Full local C++ build/CTest
is not needed to prove Python smoke; Linux GCC remains the authoritative
repository check before any eventual merge.

**Knowledge impact:** the narrow offline trainer and fixed experimental
contract are documented; current research status notes pre-fit readiness.
No trained-model result or runtime default changes.
