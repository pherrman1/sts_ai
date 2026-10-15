# Issue 40: check_vwin_calibration has no map-encoder (V6) support

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `check_vwin_calibration.py`

## Symptom

The `--ckpt` predictor's `Net` has no `map_enc`/`map_adapter`. A map-trained
checkpoint crashes the strict `load_state_dict` (loud but cryptic), and if it
were loaded non-strictly, MAP-screen Q_win predictions (which depend on the
adapter at `train_strategic.py:412-415`) would be silently wrong — the checker
cannot tell the two cases apart and does not pass map features.

## Evidence

- `check_vwin_calibration.py:51-80` (Net without map modules, strict load).
- `train_strategic.py:192,415-420,431` (map-encoder architecture).

## Why it matters

Tooling gap: no way to truth-check V6 (map-DAG encoder) checkpoints; a future
non-strict change would silently misreport calibration.

## Candidate fix direction

Detect `maps=True` in the checkpoint and error with a clear message; support
map checkpoints only with a full map-feature plumbing change.

## Relevant code

- `check_vwin_calibration.py::net_predictor`

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree: explicit `raise SystemExit`
on `ckpt.get("maps", False)` with guidance to use the plain V5 checkpoint.
The V6 artifact is opt-in/undeployed, so nothing to rerun.
