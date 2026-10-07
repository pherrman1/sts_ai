# #347 boss-entry budget rescue on #417 sources (2026-10-07)

Frozen plan: [PLAN.md](PLAN.md). Sources: [selection.json](selection.json)
(`select.py` over the #417 rows at evidence ref `10e56bd8`). Status: awaiting
independent pre-run review; the main comparison has not run.

- Diagnostic build source `e6b6122a` (research change `dbf6f573` applied to the
  #417 baseline `5e9583cc`). Binary SHA-256
  `5b83c7ae3d2e6e28693638ac97759b30a19b5067facbb070a1739204d4693f68`
  (`linux-gcc-release`, `one_combat`, GCC 13.3).
- Selftest `bossrescue347selftest 1 48009000 1000` (flat10k arm, current-main
  build): all eight checks PASS.
- Smoke ([smoke/](smoke/), never pooled): `smokeR-48000117-a3` (mcts) and
  `smokeC-48000109-a3` (flat10k) both `VALID`: historical rows reproduced
  exactly, control parity on outcome, HP, full trace and post-exit digest,
  repeats identical, every root searched exactly 10,000 or 40,000 steps. The
  mcts log shows `[live OOC MCTS ON sims=2048 ... leaf_value=screengbm`.
