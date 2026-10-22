# AZ gen-3 exploration self-play block: pre-registration (2026-10-22)

Authorization: Philipp 2026-10-22 10:45Z, "Go with 32 workers" (message cmsg_01Gm4mB9c3iJfz3vtwJcJzmnGZz8KeXh6aRB3ZguvNEdaX),
after the plan in `PLAN.md` (order: exploration block, then gen-3 training, then an A/B; 10:33Z). Seeds reserved by the
coordinator 10:34Z.

## Purpose
Training data, not an evaluation. Every OOC game so far was played greedily (most-visited root action, no root noise).
This block adds root exploration so the gen-3 training window covers branches the sharp prior never visits. There is no
gate and no verdict; the numbers below are descriptive.

## Config (`run_unit.sh`)
- One arm, E: the gen-2 A/B's arm A (student_sel `cf6bf7fb…` as OOC prior and rollout net, X2-B rollout3 end value,
  OOC MCTS 4096 sims, learned OOC stop, 25% full-budget roots, fast-root cap 1024, learned Silver stop
  gbt-0cac7cc64364 in real combats with exact root budgets, boss-only prior playouts set explicitly, Wing Boots counter
  on, flexible keys), plus the two #741 switches:
  - `STS_OOC_MCTS_ROOT_NOISE=0.25:0.3`: PUCT at every searched root uses 0.75·prior + 0.25·Dirichlet(0.3). Recorded
    priors stay clean, so π' targets use the clean prior.
  - `STS_OOC_MCTS_PLAY_SAMPLE=6:1`: on floors 0-6 the played root action is sampled ∝ visits (T = 1); rows carry
    `playSampled`. Later floors play the most-visited action.
- Banner checks (rc 93/92 if missing): `root_noise=0.25`, `play_sample=6:`, on top of gen 2's four.
- Code: main `165b5060` (later than gen 2's `844bd923`; it adds default-on engine fixes merged 10-21/22), so this block's
  rows are not config-identical to the gen-2 A/B. Recorded per row via the `.env` files.

## Seeds, budget
- 1,024 seeds, 111300000–111301023 (coordinator 2026-10-22 10:34Z). Smoke seeds 111301990–991 (outside the block).
- 32 workers × 4 lanes, `schedule queue` (lease 30). One run per unit; gen-2 A/B runs averaged ~775 s, so ≈ 220 core-h,
  about 2–3 h wall.

## Descriptive report (`analyze.py` on the `verify_campaign.py --extract` dir)
- Heart kills, Act 4, mean floor, wall. Reference (different seeds, not paired): gen-2 A/B arm A, same net, greedy:
  20.9% Heart, 39.0% Act 4.
- Floors 0-6: share of searched roots where the played action differs from the most-visited one, and how often its Q
  was higher/lower (mean Q delta).
- Distinct floor-0..6 trajectories (all 1,024 seeds differ in maps, so this is a sanity count, not a diversity metric).
- Fast-root early-stop rate (the learned OOC stop was trained without noise) and prior-override rate vs gen 2 arm A
  (6.6%).

## Use
Gen-3 window = gen 0 + gen-1b A/B + gen-2 A/B (both arms) + this block. Rows keep `playSampled`; the gen-3 training
plan decides whether to down-weight value rows of runs whose early play was sampled.
