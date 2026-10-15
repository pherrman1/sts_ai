# Issue 76: Silent CPU fallback in PVNet trainer

- **Status:** closed (2026-08-10)
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `train_combat_pvnet.py:50-54`

## Symptom

`train_combat_pvnet.py` silently switches DEVICE to "cpu" when CUDA is
unavailable — the only canonical trainer with no device message. Violates
the AGENTS.md convention "check the startup device: line." A 3M-row PVNet
run would silently take hours on CPU.

## Evidence

- `train_combat_pvnet.py:50-54`: `else: DEVICE = "cpu"` with no print.
- `train_strategic.py:85`: prints `device:` (correct pattern).
- `train_value_combat.py:118`: prints `training on {DEVICE}` (correct pattern).

## Candidate fix directions

Add `print(f"device: {DEVICE}")` after device selection.

## Relevant code

- `train_combat_pvnet.py:50-54`
