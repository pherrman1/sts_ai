# heart1 distillation: OOC MCTS tree-node capture (2026-10-15)

Philipp asked (2026-10-15 11:03Z) whether heart1 can be distilled into a fast OOC MCTS prior, and gave the go for
state collection with up to 8 workers (11:12Z). Investigation notes: `/mnt/project-files/heart1-distill/NOTES.md`.

- Code: `STS_OOC_HEART1_CAPTURE=<out.jsonl>` (with `STS_OOC_HEART1`, V4 tree prior). Every
  `STS_OOC_HEART1_CAPTURE_EVERY`-th (here 8) multi-source V4 prior build writes one JSON line: the node's heart1
  record, heart1 token logits/value and token action bits, the V4 source logits and source bits, and heart1's
  per-source logits (`h1`, null when a source has no heart1 token). Observation only; it uses no RNG.
- Units: the §486 `v4` arm (`../heart1_ooc_ab_486_20261015/arm_env.sh`, 4096 sims, rollout3) plus the capture.
- Seeds (coordinator block): A20 108000000–108000031, A0 108000032–108000063; 8 workers, 4 + 4 seeds each.
  Hook smokes used 74072100–74072101.
- Smoke (seed 74072100, A20): decision trace and `.mcts.csv.actions.jsonl` byte-identical with and without capture;
  CPU 309 s vs 137 s.
- Output: one `wNN.tar.gz` and `wNN.DONE.txt` per worker in `/mnt/project-files/heart1-distill/`.

Known: our reward source "skip this card reward" (`GameAction(CARD, group, 5)`) has no heart1 token, so `h1` is null
on most REWARDS nodes; the token logits are still recorded.
