# Issue 27: No dependency lock for Python packages

- **Status:** closed
- **Tier:** Low
- **Last verified:** 2026-09-07
- **Source:** [`architecture/training-and-inference.md`](../architecture/training-and-inference.md), "Known limitations"; [`operations/build-and-debugging.md`](../operations/build-and-debugging.md)

## Symptom

No repository dependency lock describes Python packages. Scripts import NumPy,
pandas, XGBoost, scikit-learn, and sometimes PyTorch; versions are unpinned, so
training, export, and server behavior can change between environments.

## Evidence

- `training-and-inference.md`: "No dependency lock or environment definition
  exists."
- `build-and-debugging.md`: "No repository dependency lock describes Python
  packages."

## Why it matters

Model artifacts are version-sensitive; a trainer/XGBoost version drift can
change export formats or tree behavior without any tracked change, weakening
reproducibility claims.

## Candidate fix direction

Add a pinned environment definition (e.g., `requirements.txt` with exact
versions or a lockfile) and record the versions in experiment provenance.

## Relevant code

- Root `train_*.py`, `export_*.py`, `v_server.py` imports
- `EXPERIMENTS.md` artifact provenance conventions

## Resolution (2026-09-07)

`pyproject.toml` and `uv.lock` define the maintained dependency groups, CI
checks the lock and installs the analysis group, and
`tools/agent/bootstrap_python.sh` reuses that locked analysis environment
across sibling worktrees.

## Closed by

Shared lock-keyed Python environment bootstrap change.
