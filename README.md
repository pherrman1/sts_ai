# Heads analysis data, 2026-11-26/27 (data branch, not for merge)

- `ckpt_1805354.pt`: live training checkpoint, step 1805354, saved 2026-11-27 00:01 CET (30 min after a resume on an empty 10M
  window; 256/32 sims, root-target policy, rt_repo a7698c2ef; net 128x4 with its input flags in `args`).
- `seen_*.npz`: 501 whole runs / 65,580 samples ending before H1 = 873,885 (the replay position at the checkpoint's save time):
  trained on by the checkpoint's training window.
- `unseen_*.npz`: 455 whole runs / 65,595 samples starting at or after H1 (played after the checkpoint, never trained on by it).
- Window: replay saved at step 1808284 (tail 0, head 2,373,986). Format = slice_runs.py (2026-11-25 half-life B): per run
  `r{i}.<field>` gathered rows (Replay._gather, unpacked layout), `r{i}.abs`, `r{i}.run_id`; `info.json` describes the cut.
  Script: `slice_heads.py`.
- `analysis_1594969.json`: gradient-noise analysis of ckpt 1594969 (2026-11-25).
- `SHA256SUMS`: sha256 of every file.
