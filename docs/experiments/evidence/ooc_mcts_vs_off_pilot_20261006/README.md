# OOC MCTS on vs off pilot (2026-10-06)

Frozen plan: [PLAN.md](PLAN.md), with independent pre-run review (one blocking
smoke-check bug, fixed in `614007a4`; re-check clean). Philipp authorized the
run on 4 cloud cores.

- Binary: built from `aa000e8a` (source identical to `5e9583cc`), SHA-256
  `fcaeec61840b88d8f0449c118a553291a8ae0339f4616509d1fd6f1a6bec51ab`.
- Seeds `48000000..48000127`, 4 shards × 32 seeds, one CPU each, every arm in
  each shard. All 12 invocations exit 0; no failed seeds. Smoke seed
  `48009000` (not pooled) passed all plan checks: `smoke/`.
- `analyze.py run --out report.json` reproduces `report.json`.

| 128 pairs | learned | flat10k | mcts |
|---|---:|---:|---:|
| win rate | 73.4% | 78.1% | 56.3% |
| mean floor | 48.93 | 48.42 | 46.96 |
| CPU s per run | 24.1 | 57.6 | 114.1 |
| losses on a boss floor | 26/34 | 24/28 | 44/56 |
| mean HP after winning | 43.1 | 44.5 | 32.2 |

Paired differences (95% bootstrap CI):
- **mcts − flat10k: wins −21.9 pp [−32.0, −11.7]**; floor −1.46 [−3.16, +0.27];
  discordant 12 vs 40. Verdict **`MCTS_WORSE`**.
- flat10k − learned: wins +4.7 pp [−4.7, +14.1]; floor −0.51 [−2.0, +0.93];
  2.4x time.
- mcts − learned: wins −17.2 pp [−28.9, −4.7]; floor −1.97 [−3.64, −0.32];
  4.7x time.

The boss-floor and HP rows are descriptive and were not pre-registered.

**Restart note:** a first launch was attached to a background timeout shorter
than the run. It was stopped about a minute in, before any results were
inspected, and its output (one partial row) was set aside. The run was then
relaunched from scratch, detached, with identical arguments.
