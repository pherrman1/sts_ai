# Issue 44: token-pipeline hygiene — dead gather, GELU mismatch, NaN-loss zeroing

- **Status:** open
- **Tier:** Medium
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05

## Symptom

- `train_strategic_tok.py::fwd_rows` recomputes `bits/c/a/s/et/ei/gg/pr` from
  CPU arrays unconditionally after the GPU-resident gather, discarding the
  on-device tensors (dead path; **fixed 2026-08-05**).
- V3-family GELU mismatch: trainers use `nn.GELU()` (erf) while
  `export_strategic.py`'s reference/parity use `approximate="tanh"` — the
  deployed V3 artifact uses a slightly different activation than the training
  forward (~1e-4) (**unfixed, documented**).
- `train_strategic.py:589-590` and `train_strategic_tok.py:494-495` silently
  zero non-finite losses, masking NaN bugs in the distillation machinery
  (**unfixed**).

## Evidence

- `train_strategic_tok.py:433-455` (dead recompute), `:494-495` (NaN zeroing).
- `train_strategic.py:374-378` vs `export_strategic.py:93-94,282` (GELU).

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

Open — minor batch from the 2026-08-05 code review; the dead recompute was
removed in the review working tree. No experiment rerun required (numerics
within parity tolerance).
