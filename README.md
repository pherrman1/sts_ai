# heart1 distillation data (never merge)

Captured OOC MCTS tree-node states labelled by heart1, for distilling heart1 into a fast OOC MCTS prior
(project thread "Distill heart1 into fast prior", Philipp 2026-10-15).

- Producer: `STS_OOC_HEART1_CAPTURE` on run commit beffbacbd48d6a29fccfec170eacb4a32f90d76d (branch
  claude/project-thread-7sc8xv), binary sha256 88f0c4b6…, heart1.bin sha256 1e92f2a6…; §486 `v4` arm env (4096 sims,
  rollout3, V4 prior) plus capture every 8th multi-source prior build.
- Seeds: A20 108000000–108000031, A0 108000032–108000063 (8 workers). All 64 units rc=0; 1,009,708 rows.
  Worker DONE files in `provenance/`; tars verified from another container (tar sha256 = DONE).
- Row: `record` (silverbot Choice dict), `logits` (heart1 per choice token), `value`, `token_bits`, `src_bits`, `v4`
  (V4 source logits), `h1` (heart1 per source, null when a source has no token), `screen`, `act`, `floor`, `node`.
- Train: `PY=<python with CUDA torch> bash tools/run_gpu.sh`. Validation = held-out seeds (seed % 8 == 7).
