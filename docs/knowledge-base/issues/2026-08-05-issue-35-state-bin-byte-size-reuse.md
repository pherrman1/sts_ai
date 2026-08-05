# Issue 35: state.bin reuse keyed only on byte size

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `train_strategic.py`, `train_strategic_tok.py`

## Symptom

Both strategic trainers reuse a precomputed `_state.bin` iff
`os.path.getsize == nrows * NSTATE * 2` (resp. `NFILE * 2`). Any producer
change that preserves the row count (new label semantics, changed derived
features, changed normalization) silently reuses **stale** state. The dist
wave logs confirm active reuse (`*_train.log`: "reusing ..._state.bin"),
which is benign there only because the CSV family was unchanged.

## Evidence

- `train_strategic.py:268-273`, `train_strategic_tok.py:277-284` (byte-size-only check).
- `ooc_strategic_qwin_cal_dist_*_train.log` ("reusing" lines).

## Why it matters

The 2b fix (glob 44–49 stats) and any future schema change would otherwise
train on stale features without error. Also makes the trainer resilient to
unrelated CSV edits (e.g. the calibration remap) that keep nrows.

## Candidate fix direction

Sidecar fingerprint `.fp` over CSV identity (path/size/mtime), trainer script
identity, nrows, layout size, and (strategic) the mean/inv arrays; reuse only
on match.

## Relevant code

- `train_strategic.py`, `train_strategic_tok.py` (state-file block)

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree: both trainers now write and
check a `_state.bin.fp` sidecar (sha256 over CSV path/size/mtime_ns, script
path/size/mtime_ns, nrows, layout size, and mean/inv for the strategic
trainer). Existing `.fp` files are absent, so the next run regenerates the
state exactly once. Rerun ledger: verify-only row per logged reuse.
