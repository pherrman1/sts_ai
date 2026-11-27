# Amber 1.2M net on Baalorlord's A20 elite and boss states (§TBD)

Question (Philipp, 2026-11-27): on the Baalorlord benchmark used before for the Silver combat stack (§770), is the
frozen 1.2M Amber net (amber_scratch `ckpt_1828683.pt`, sha256 `1b2c02e8…`) weak in combat or out of combat?

## Method

- **States:** `dump_unit.sh` = §770's `run_unit.sh` environment with no research arms and
  `STS_EXPERT_FIGHTS_DUMP=1` on §770's arm rooms 1E,1B,2E,2B,3E,3B. one_combat expertfights replays the 329
  expert runs (`units.txt`, `expert_runs.tar` sha256 `895eac8f…`, `student_sel.bin` `cf6bf7fb…`), production
  Silver plays the 4 copies of every arm fight (§770's reference side) and every copy's start state is written
  (`include/game/GameContextBinary.h`). Code 9bc1d3eb, one_combat in `results/provenance.txt`. PC, 2-5 processes,
  ~5 h wall with the live run beside it.
- **Amber:** `selfplay.py --fight-roots` plays each dumped copy start once with the fixed-seed bench's search
  (`--full-prob 0 --fast-sims 128 --fast-candidates 8`, the 1000-seed bench flags in `results/provenance.txt`), GPU
  beside the live run. Arm 1024 = the same with `--fast-sims 1024`, on copies 0-1 only (GPU/RAM budget).
- **Metric:** §770's `analyze.py` rules (`analyze_matched.py`): HP lost = entry HP − exit HP (entry HP on a loss),
  mean over copies, floor-51 Act-4 heal inverted, same drops; Amber fights need every copy finished. 95% CIs:
  run-clustered bootstrap, 10,000 resamples.
- **Seeds:** none new (§694's external expert seeds, replayed). The side bench (below) replayed the fixed-seed
  benchmark 160200000-160200999.

## Results

**Check:** the dump's production side reproduces §770: 11.60 HP per fight (§770 11.60), expert 8.76 (§770 8.74),
1,874 fights (§770 1,878; 3 dropped here because one Amber copy stalled, 1 by the drop rules).

**128 sims, 4 copies, 1,874 fights** (`results/amber128_matched.json`):

| | HP lost per fight | death per fight | potions per fight |
|---|---|---|---|
| Baalorlord | 8.76 | 0.026 | |
| Silver production | 11.60 | 0.057 | 0.55 |
| Amber 1.2M, 128 sims | 20.46 | 0.057 | 0.82 |

Amber − production **+8.86 [+7.89, +9.86]**; by act and room: 1E +6.3, 1B +9.0, 2E +7.1, 2B +14.7, 3E +9.8,
3B +20.7 (all CIs above 0); every encounter with n ≥ 20 is worse (Time Eater +24.5, Donu and Deca +20.1,
Champ +17.5, Awakened One +17.1). Deaths per fight equal to production in every cell.

**1024 sims, copies 0-1, 1,596 fights** (`results/amber1024_c01_matched.json`; the run was stopped by its RAM
watchdog at 3,200 of 3,754 copies when the student bench started; 278 fights missing): expert 8.62, production
11.64, Amber 128 20.76, **Amber 1024 20.50**; Amber 1024 − production +8.86 [+7.71, +10.07]; deaths 0.055 / 0.055 /
0.044 (production / 128 / 1024), lower mainly at act-1 and act-2 bosses.

**Side bench (the net's own runs, `results/bench1000_701.json`, §701's cells):** 1000 fixed seeds at A20, 38.5 %
wins (the distill thread's bench of the same checkpoint: 34.9 %). Net HP per won fight vs Baalorlord's §701
cells: act-1 elites 16.5 vs 9.5, act-1 boss 24.7 vs 11.3, act-2 elites 11.9 vs 5.6, act-2 boss 20.2 vs 11.2
(the act-3 boss cell includes the Act-4 transition heal and is not comparable). Heart death per fight 0.13 vs
expert 0.08 and §701's old bot 0.41.

## Interpretation (Inference)

On identical states the 1.2M net loses about twice production Silver's HP per elite and boss fight, with the
same death rate, and 8× its search budget does not change the HP loss (−0.3) while it trims deaths by about a
fifth. Its combat weakness is in the net's in-fight evaluation and prior, not the bench's 128-simulation budget.
Because the same net wins 38.5 % of its own A20 runs with this combat, its out-of-combat play carries the run;
combat is the part to improve. Not tested: whether the HP loss is a deliberate trade (the utility values the run's
P(win), not HP), larger budgets, or the 0.44M student.
