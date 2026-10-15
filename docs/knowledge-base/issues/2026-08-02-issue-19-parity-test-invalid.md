# Issue 19: `parity_test.py` cannot run as written

- **Status:** closed
- **Tier:** Medium
- **Last verified:** 2026-08-02
- **Source:** [`operations/build-and-debugging.md`](../operations/build-and-debugging.md), "Known limitations"; [`architecture/training-and-inference.md`](../architecture/training-and-inference.md)

## Symptom

`parity_test.py` expects an unbuilt binary (`build/parity_test.elf`, which CMake
does not produce) and an unavailable trained PyTorch checkpoint; it cannot
establish trained distribution-model parity as written.

## Evidence

- `apps/parity_test.cpp` has a `main` but no CMake target
  (`build-and-debugging.md`).
- `training-and-inference.md`: "`parity_test.py` does not load the trained
  PyTorch checkpoint and expects `build/parity_test.elf`, which CMake does not
  build."

## Why it matters

Training/native-inference parity is a documented invariant, but the only parity
utility is dead. Silent divergences between trainer output and native readers
would go undetected.

## Candidate fix direction

Wire `apps/parity_test.cpp` into CMake, fix the checkpoint path, or replace the
script with a producer/consumer parity harness (open question in
`training-and-inference.md`).

## Relevant code

- `parity_test.py`, `apps/parity_test.cpp`, `CMakeLists.txt`

## Resolution (2026-08-02)

Fixed: `parity_test` CMake target added; `parity_test.py` resolves `STS_PARITY_BIN` or `build/parity_test` and exits loudly when binary or checkpoint is missing. Real trainer/native parity still requires a produced checkpoint (open question).

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
