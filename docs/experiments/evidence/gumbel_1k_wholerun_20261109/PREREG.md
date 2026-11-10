# Gumbel 1k in whole runs: G16 + mb4 at 1,000 simulations against combat B (pre-registration)

**Authorization.** Philipp, 2026-11-09 23:35 CET: "Kannst du mal schnell gumbel mit 1k sims anstatt 16k sims auf 512
seeds auf 40 workern laufen lassen?", and 23:41 CET: "baller da jetzt 40 worker durch und mach hinne". 512 seeds, 40
workers. Prelaunch review by J runs in parallel with the launch (Philipp's "mach hinne"); a blocking finding stops the
queue.

## Question

§775's teacher G16 + mb4 (Gumbel root k 16, max backup 4, 16,000 simulations in every fight) costs about 25× combat B
per run, the combat net-0420 was trained with. Does the same Gumbel root at combat B's budget of 1,000 simulations,
Act 4 included, kill the Heart more often than combat B itself?

## Design

- Seeds: the first 512 of §775's frozen block, 111378256-111378767 (no new seeds). One unit per seed holds both arms,
  in an order rotated by seed (`run_unit.sh`, `units.txt`).
- Out of combat: LONG_C's net-0420 (temperature 0, no OOC MCTS), as §775 and §777.
- Arms (`run_unit.sh`):
  - **B1** = combat B (`../ppo_long_c_20261106/actors_frozen.env`, as §760's evaluation): flat Silver 1,000, learned
    stop off, Act 4 strong off, g7f_E root table and prior weight 400, tree prior K = 8, boss-only prior playouts.
  - **G1** = B1 plus `STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4`. The two arms differ only in
    these two variables. G1 is §775's G16 + mb4 at 1,000 simulations with Act 4 at 1,000 as well (in §775 the learned
    stop's flag kept Act 4 strong on, so Act 4 ran at 10k / 40k; under the Gumbel root the learned stop itself is
    off in every fight in both).
- Binary b5090b16 (code 13bb97ec, §777's), from the share's binary cache. Timeout 1 h per game.
- Smoke (local, 2026-11-09 23:45 CET): seeds 111378256 and 111378257, 4 of 4 games rc 0, 3-14 s per game; G1 logs
  the Gumbel banner, roots and tree reuse at cap 32,768; B1 logs the flat budget and no Gumbel line.

## Primary

Heart kill rate G1 − B1, paired by seed, mean difference with a 95% seed bootstrap (10,000 resamples, seed 20261109).
**G1_BETTER** if the interval's lower end > 0, **G1_WORSE** if its upper end < 0, else **NO_DIFFERENCE_SHOWN**. No
SPRT: every seed runs (512 seeds give a half-width of about 3.5 pp). A game with rc ≠ 0, a wrong environment or a
missing BEST line is a drop; seeds with a drop in either arm are left out and counted. More than 10 dropped seeds:
**NOT_EVALUABLE**.

## Secondary (not gates)

- G1 and B1 against §775's D (A20 default combat, 10,000 with learned stop) and G16 + mb4 on the same 512 seeds
  (§775's games, binary 0eabb014; §777's 32/32 sentinel showed this binary replays §775's G16 games exactly).
- Act-4 reach (floor ≥ 52), mean final floor, CPU per run and per floor reached; G1's Gumbel roots and simulations.
- Combat stalls (abort lines) per arm.

## Decision

No default change. This measures whether the Gumbel root helps at the PPO training budget. G1_BETTER would make the
Gumbel root at 1,000 a candidate for the PPO actors' combat (a training run needs Philipp's go); otherwise the gain
of §775 needs the larger budget.
