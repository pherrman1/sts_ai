# Heads audit 2026-11-27 (offline, CPU, no seeds)

Checkpoint `ckpt_1805354.pt` (amber_scratch, step 1,805,354, saved 2026-11-27 00:01 CET; sha256 in the data branch
`claude/heads-20261126-data` commit 87a046cf, SHA256SUMS). Slices: 501 SEEN runs / 65,580 samples, 455 UNSEEN runs /
65,595 samples (`info.json`), cut by the stage-1 thread's `slice_heads.py` (format of the 2026-11-25 `slice_runs.py`).

- `gate0_probe.py` -> `gate0.json`: the net as trained vs all encounter gates 0 vs encounter tokens removed, UNSEEN runs.
- `softpol_probe.py` -> `softpol.json`: (a) per-head gradients on the shared parameters, 16 steps of ~1,024 SEEN samples;
  (b) 200-step fine-tunes with `--w-soft-policy` 8 / 2 / 0 from the checkpoint's optimizer state and LR, eval on UNSEEN.
- `netload.py`: builds the training net from a checkpoint's args (from the 2026-11-25 half-life test).

Run: `python3 -I gate0_probe.py REPO CKPT SLICE_DIR OUT [MAX_RUNS] [THREADS]`,
`python3 -I softpol_probe.py REPO CKPT SLICE_DIR OUT 200 50 16 4 455` (cloud, 4 cores, torch 2.15 CPU, repo b12edfe).
