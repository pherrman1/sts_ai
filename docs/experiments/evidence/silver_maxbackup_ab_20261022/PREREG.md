# A/B: max backup + block-first playouts vs production Silver (A20, fight level)

Status: **authorized** by Philipp, 2026-10-22 08:05Z ("do 32 workers"), after a CPU check he asked for first
(below). Written before any result of this A/B. Needs a pre-launch review. Thread "Silver leaf and rollout bias". Ledger §624. Seeds: 111149400–111149463 (64 sources)
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
  - `base12000` and `base15000`: the same at 12,000 and 15,000, the CPU-matched controls. The extra cost of the
    candidate comes from its behavior (longer block-first playouts, longer fights; CPU check below), so it varies
    by fight: 1.18x per fight on sources 111149390-393, 1.73x on the frozen smoke 111149381 (7 fights; 2.1x on
    The Guardian). base15000 was added after that smoke, before launch.
  - `fix10000`: max backup m = 4 + block-first playout (margin 3, lethal check, offset 4), 10,000.
- **Env.**
  - `STS_CTMSILVER_ARMSET=maxbackup`, `STS_CTMSILVER_SWEEP_SIMS=10000,12000,15000`, `STS_CTMSILVER_FIX_SIMS=10000`,
    `STS_CTMSILVER_HALLWAY_EVERY=3`.
  - Otherwise as `../silver_prior_playout_ab_20261018/run_unit.sh`, with g7f_E instead of g6_E.
- **Campaign.** 64 units (one source seed each), `campaign.manifest`: 32 workers (Philipp), 4 lanes each,
  `schedule queue`, code commit c4dcb43c (main), v3 preset. Cost: in the CPU check below, one source with five
  arms took 4-21 min on one core, so a unit (four arms plus the control) takes about 4-25 min; the campaign is bounded by the
  slowest unit (**estimate**, under 1 h).
- **CPU check (2026-10-22, before launch; sources 111149390-393, reused 391-392 for a code check).** With split
  arms (max backup only, block-first only), fix10000 used 1.18x the CPU of base10000 per fight: 1.12x per
  simulation and 1.05x more decisions. A gdb profile shows the max-backup bookkeeping costs no measurable time
  (search self-time 50 vs 52 of 150 samples); the extra cost comes from the new behavior (block-first playouts
  about 8% longer, longer fights). A bit-identical speed-up of the backup pass gave no gain and was dropped.

## Analysis and decision rule

`analyze.py` on the extracted worker tars. It is the §541 analyzer with these arms: per-arm fight score, win, HP
lost, CPU per fight and per simulation. Paired contrasts use a 95% seed bootstrap over all, boss, elite, normal and
Act-4 fights.

**Primary label: `fix10000 − base10000`, all fights.**
- Score: BETTER if the CI lower bound > 0, WORSE if the upper bound < 0, else NOT_SHOWN.
- HP lost: BETTER if the CI upper bound < 0, WORSE if the lower bound > 0, else NOT_SHOWN.

**Secondary label: `fix10000 − matched`**, same rule (the CPU-matched comparison). `matched` is the smaller of
`base12000` and `base15000` whose per-fight CPU ratio fix10000/base (point estimate of the seed-pooled ratio in
`cpuRatios`) is ≤ 1.10, chosen by CPU alone. If neither is, both secondary labels read NOT_MATCHED and support
no claim. The other base contrasts and the subsets are descriptive.

No default change. A default proposal goes to Philipp with these numbers. The learned stop
(ADR-0051/0054) was trained on mean-backup trees and is not part of this A/B. If the candidate wins, the stop
needs its own check before any default.
