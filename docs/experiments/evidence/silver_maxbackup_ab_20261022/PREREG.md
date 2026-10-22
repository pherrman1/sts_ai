# A/B: max backup + block-first playouts vs production Silver (A20, fight level) — DRAFT

Status: **draft, not authorized.** Written before any result of this A/B. Needs Philipp's typed go, a worker count
and a pre-launch review. Thread "Silver leaf and rollout bias". Ledger §TBD. Seeds: 111149400–111149463 (64 sources)
from this thread's block 111149100–111149599; smokes 111149380–111149389.

## Background

The exact combat solver (exact-combat research thread, `claude/project-thread-kgjoid`) scores every root Silver
searches. On A20 first fights, Silver's errors are almost all attacking where blocking is optimal. There are two
causes:

1. **The greedy playout never blocks because it is hit.**
2. **Mean backups are biased against the longer line.** At a wrong root, the less-visited Defend child's mean is
   5-10 points below its exact value, while Strike's mean is only about 4 below.

The candidate (`STS_SILVER_MAX_BACKUP=4` + `STS_SILVER_ROLLOUT_BLOCK_FIRST=3`) cut regret per fight a lot:

| encounter | fights | seeds | change in regret per fight |
|---|---|---|---|
| Jaw Worm | 100 | fresh, 111149250–349 | prod 1.57 → 0.74, live 1.54 → 0.67 |
| Two Louse | 100 | 111149600–699 | 0.35 → 0.12 |
| Cultist | 20 | | 6 → 0 wrong decisions |

Report: `/mnt/project-files/silver-rollout-bias/REPORT.md`. These fights are starter-deck first fights. This A/B
asks whether the gain carries over to whole A20 runs (later decks, elites, bosses).

## Design

- **Harness.** `one_combat ctmsilvergen` at Ascension 20, armset `maxbackup`, the §541 harness. Source runs come
  from student C (`eff2f74f…`), with the g7f_E root prior (`c45dcc0a…`) at weight 400 and the ADR-0046 root table on.
  Every 3rd hallway fight is replayed. R = 2 combat-RNG redraws. Keys are off, so runs stop after Act 3 unless the
  source collects Act 4 by itself. There is no OOC MCTS, so there are no imagined fights.
- **Arms.** All use the root prior and the tree prior (K = 8) under a rollout override, so none plays the ADR-0050
  boss prior playouts.
  - `base10000`: production search (mean backups, production playout), 10,000 simulations.
  - `base12000`: the same at 12,000. It is the CPU-matched control: in the smoke (source 111149380, 6 fights,
    R = 2) `fix10000` used 1.20x the CPU of `base10000` (15.97 vs 13.40 µs per simulation).
  - `fix10000`: max backup m = 4 + block-first playout (margin 3, lethal check, offset 4), 10,000.
- **Env.**
  - `STS_CTMSILVER_ARMSET=maxbackup`, `STS_CTMSILVER_SWEEP_SIMS=10000,12000`, `STS_CTMSILVER_FIX_SIMS=10000`,
    `STS_CTMSILVER_HALLWAY_EVERY=3`.
  - Otherwise as `../silver_prior_playout_ab_20261018/run_unit.sh`, with g7f_E instead of g6_E.
- **Campaign.** 64 units (one source seed each), 4 units at once per worker (`tools/cloud/worker.sh`). The worker
  count is Philipp's call (§541 used 8). Cost: the smoke source died
  at the Act 1 boss (6 fights, 2 min for two arms). A typical source has about 30-40 replayed fights, so a unit
  with three arms takes roughly 20-40 min on one core. 64 units on 8 workers x 4 is about 1-1.5 h wall
  (**estimate**, from §541's similar harness).

## Analysis and decision rule

`analyze.py` on the extracted worker tars. It is the §541 analyzer with these arms: per-arm fight score, win, HP
lost, CPU per fight and per simulation. Paired contrasts use a 95% seed bootstrap over all, boss, elite, normal and
Act-4 fights.

**Primary label: `fix10000 − base10000`, all fights.**
- Score: BETTER if the CI lower bound > 0, WORSE if the upper bound < 0, else NOT_SHOWN.
- HP lost: BETTER if the CI upper bound < 0, WORSE if the lower bound > 0, else NOT_SHOWN.

**Secondary label: `fix10000 − base12000`**, same rule (the CPU-matched comparison), **only if the arms are
CPU-matched**: the per-fight CPU ratio fix10000/base12000 (point estimate of the seed-pooled ratio in
`cpuRatios`) must be ≤ 1.10. Otherwise both secondary labels read NOT_MATCHED and support no claim. The 1.20x
smoke ratio rests on 6 fights; the REPORT's +30-50% per simulation came from the exact benchmarks, where the
learned stop also ran longer and per-root exact scoring was included. This harness uses flat exact budgets.
`base12000` covers a fix/base10000 ratio up to about 1.32. `base12000 − base10000` and the subsets are
descriptive.

No default change in this PR. A default proposal goes to Philipp with these numbers. The learned stop
(ADR-0051/0054) was trained on mean-backup trees and is not part of this A/B. If the candidate wins, the stop
needs its own check before any default.
