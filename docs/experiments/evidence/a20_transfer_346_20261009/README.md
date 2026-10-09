# #346 A20 counterfactual corpus and option-spread comparison with E3

Ledger: [§402](../../ledger-06.md). Plan: [PLAN.md](PLAN.md).

## Probe (bestbench, flat10k profile, seeds 59000000..59000031)

| Run | A0 | A20 |
|---|---|---|
| main `10376b97`, stop after the first Act-3 boss | 24/32 | 6/32 |
| `5ba068e0`, A20 second boss played | n/a | **0/32** |

At `5ba068e0` the 26 earlier A20 losses are identical rows. All six earlier
"wins" die to the second boss on floor 51. Raw files are in
`/mnt/project-files/a20-transfer-346/probe-10376b97/` and
`probe-a20-secondboss-5ba068e0/`.

## Corpus

- Producer: `ooccfpilotgen` GEN=2 at `5ba068e0`, binary sha256 `dddb09f0…` in
  every worker. ASCENSION=20; otherwise E3's settings (learned-stop V4 teacher,
  K=2 futures shared across options, up to 2 states per seed, CARD_REWARD and
  BOSS_RELIC).
- 20 cloud workers × 60 seeds, seeds 59100000..59101199. 240 of 240 parts
  finished with no stalls. 17,466 of 17,466 labels are valid, from 2,094 states.
- Output: `/mnt/project-files/a20-transfer-346/cf-a20-5ba068e0/wWW/` (not
  archived in Git).
- The generator plays to the end of the run. At A20 a win is the second
  boss on floor 51, and the label win rate is 10.9% (card) / 9.7% (relic).

## Analysis

`compare_e3.py E3_ROOT A20_ROOT` writes [report.json](report.json).

- **Signal:** the futures are common random numbers across a state's
  options, so each state gets a two-way (option × future) ANOVA. The signal
  is var(option means) − MS_interaction/K, an unbiased estimate of the variance
  of true option values inside the state. Its mean over states is reported,
  with 95% CIs that resample source seeds.
- **Targets:**
  - `finalWon`;
  - `act3Boss1`: the first Act-3 boss is beaten. At A0, keys off, this is the
    run win. At A20 it means reaching the floor-51 boss;
  - `horizonFloor`: the floor of the run's last fight.
- E3's stalled part (seeds 55000830..834) has no manifest and is skipped, as in §396.

| Target | Type | A0 states | A0 option SD | A20 states | A20 option SD |
|---|---|---|---|---|---|
| final win | card reward | 995 | ≈0 (signal −0.0006 [−0.0047, 0.0033]) | 1,200 | ≈0 (−0.0006 [−0.0031, 0.0020]) |
| final win | boss relic | 987 | 0.122 (0.0150 [0.0097, 0.0205]) | 894 | 0.065 (0.0042 [0.0011, 0.0073]) |
| first Act-3 boss | card reward | 995 | ≈0 | 1,200 | 0.039 (0.0015 [−0.0026, 0.0055]) |
| first Act-3 boss | boss relic | 987 | 0.122 | 894 | 0.114 (0.0131 [0.0081, 0.0185]) |
| floor reached | card reward | 995 | 0.37 floors (0.14 [−0.55, 0.90]) | 1,200 | **2.02 floors** (4.10 [1.01, 7.15]) |
| floor reached | boss relic | 987 | 1.73 floors (3.01 [1.98, 4.12]) | 894 | **3.69 floors** (13.58 [11.30, 16.10]) |

Signal-to-noise ratio (signal / MS_interaction) for floor reached: card reward
0.012 at A0 vs 0.059 at A20; boss relic 0.18 vs 0.34.

## Reading (descriptive; no model was trained)

- Card rewards do not move the win probability at either ascension. At A20
  they do move how far the run gets (about 2 floors of option SD, CI excludes 0).
  At A0 they do not detectably.
- Boss relics move the first-Act-3-boss probability equally at A0 and A20
  (SD ≈ 0.12). The A20 final-win label compresses that to 0.065, because the
  second boss kills most runs.
- So, at A20, choices make a bigger difference to survival depth (floor
  reached), but not to win labels. Whether that helps an A0 model is the
  transfer test in #346, which has not been run.
