# Test B: EMA outcome-target halflife 10 vs 20 (head probe), 2026-11-25

Scripts as run on the PC (read-only on the live amber_scratch run; CPU, nice/ionice):
- `slice_runs.py`: whole runs from a saved replay window (mmap). PC edits during the run: run boundaries from
  `Replay.hp_ref` (the window has no `meta.run`), empty range returns `[]`; the unseen pull used PER_FILE 20 and a
  fixed h1 = 551710201.
- `head_probe.py`: frozen trunk of ckpt_bench_1635474, features c (input of `net.outcome`), fresh / warm outcome heads
  trained on stored h20 targets vs exact per-run remix to h10; eval on held-out seen runs and unseen runs.
- `netload.py`: builds the training net from a checkpoint (copied from the 2026-11-25 gradnoise job).
Data (not in the repo): PC ~/Documents/sts/halflife_b_20261125/out/ and Drive sts_live_claude/halflife-b-20261125/
(seen_*.npz, unseen_*.npz, head_probe.json, logs).
