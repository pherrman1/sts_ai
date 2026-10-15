# Issue 44: token-pipeline hygiene — dead gather, GELU mismatch, NaN-loss zeroing

- **Status:** closed
- **Tier:** Medium
- **Last verified:** 2026-08-22
- **Source:** code review 2026-08-05

## Symptom

- `train_strategic_tok.py::fwd_rows` recomputes `bits/c/a/s/et/ei/gg/pr` from
  CPU arrays unconditionally after the GPU-resident gather, discarding the
  on-device tensors (dead path; **fixed 2026-08-05**).
- V3-family GELU mismatch: trainers used `nn.GELU()` (erf) while
  `export_strategic.py`'s reference/parity use `approximate="tanh"` — the
  deployed V3 artifact used a slightly different activation than the training
  forward (~1e-4) (**fixed 2026-08-22**).
- `train_strategic.py` and `train_strategic_tok.py` silently zeroed non-finite
  losses, masking NaN bugs in the distillation machinery (**fixed 2026-08-22**).

## Evidence

- `train_strategic_tok.py::fwd_rows` now retains the GPU-resident action
  tensors; the former CPU recompute was removed in the review change.
- `train_strategic.py::Net` and `export_strategic.py::Tmp` now both specify
  `nn.GELU(approximate="tanh")`.
- `train_strategic.py::train_batch_loss` and
  `train_strategic_tok.py::train_batch_loss` now diagnose and raise on a
  non-finite total loss.

## Why it matters

Masked NaN losses can hide real training failures; the V3 GELU mismatch means
parity checks validate tanh-vs-tanh, not the training activation.

## Candidate fix direction

Remove the dead recompute (done); switch the V3 trainers to
`nn.GELU(approximate="tanh")` and re-export any V3 artifact used going forward;
replace NaN-zeroing with a loud counter/warning.

## Relevant code

- `train_strategic_tok.py`, `train_strategic.py`, `export_strategic.py`

## Resolution

Closed in the implementation change for issue #44. The V3 trainer now uses
`nn.GELU(approximate="tanh")` throughout the exported/native network, and the
V3 and V4 trainers report loss components then raise `FloatingPointError` on a
non-finite loss instead of continuing with a zero. The dead token gather was
already fixed in the review working tree. No experiment rerun is required;
the activation change is within the existing parity tolerance, and the
non-finite path is a failure-mode correction rather than a model recipe
change.
