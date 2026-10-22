# AZ gen-3 exploration self-play block (plan, draft)

Status: draft, nothing run. Launch needs Philipp's typed go + worker count, a seed block from the coordinator, freeze,
smoke and an independent pre-launch review, like the gen-2 A/B (`../az_gen2_ab_20261021/`).

## Why
Every OOC game so far is played greedily on the most-visited root action with no root noise, including the paired A/B
blocks whose games become training data. The nets are very sharp: the live canary (2026-10-21, runs 495/498,
`/mnt/project-files/engine-parity/overnight-20261019/ISSUES.md` "LOW-HP CHECK 495/498") saw student_sel put ~1.00 prior on
one child at early map forks, so alternatives got one visit each although their Q was equal or higher. Without exploration
the loop never sees what those branches lead to, and z never labels them.

## What
One arm of self-play capture, same stack as the gen-2 A/B (`run_unit.sh` there, X2-B leaf, learned Silver stop, fast-root
cap 1024, boss-only prior playouts, x86-64-v3 build), plus the two #741 switches (both default off, data runs only; the
live advisor refuses them):
- `STS_OOC_MCTS_ROOT_NOISE=0.25:0.3`: PUCT at every searched root uses 0.75·prior + 0.25·Dirichlet(0.3). Recorded priors
  stay clean, so π' targets are computed from the clean prior (az_targets uses the recorded `prior`).
- `STS_OOC_MCTS_PLAY_SAMPLE=6:1`: on floors 0-6 the played root action is sampled ∝ visits (T = 1) instead of the most-visited;
  rows carry `playSampled`. Later floors stay greedy, so the run's z still reflects strong play after the opening.
- Net: the gen-2 A/B winner (gen 2 on WIN, else student_sel). The n-step prior candidate (a70736fd, offline KL 0.0526) is
  not used here: never change search and net in the same arm.

## Size and cost
1,024 runs (one arm, half an A/B), ~2.5-3 h on 32 workers at the gen-2 A/B's per-run wall.

## Checks (descriptive, no gate; this block is training data, not an evaluation)
- Smoke: banners `root_noise=0.25:0.3` and `play_sample=6:1`; fraction of floor-0..6 decisions with `playSampled`.
- Report: Heart-kill / Act-4 rate vs the greedy A/B arm with the same net (expected somewhat lower), floor-0..6 path
  diversity (distinct first-act paths per seed class), and how often a sampled move had higher Q than the greedy one.
- Learned OOC stop: it was trained without root noise. Full-budget roots (the policy targets) never early-stop, so targets
  are unaffected; report the early-stop rate on fast roots vs the A/B arm.

## Training use
Gen-3 window = gen 0 + gen-1b A/B + gen-2 A/B (both arms) + this block. Policy rows from all; value rows from all, with an
`explored` flag so the value fit can down-weight or drop runs where sampling took a clearly worse move.
