# Win-now blend: a leaf without a net (exploratory)

Status: exploratory, not pre-registered. Run on 2026-10-23 while the fight-level A/B `../silver_leaf_head_ab_20261022`
was running; it changes no default and nothing in that A/B. Thread "Exact combat solving research"; doc "Leaf
evaluation for Silver" (https://claude.ai/artifact/P8536tUChd5XLo1gV6kfbu).

## Verdict

- On exact first fights, half win-now and half playout (no net) is as good a leaf as the learned head: on the 300
  fresh fights it beats the A/B candidate (the head capped at win-now) by -0.084 ± 0.058 regret per fight (prod) and
  -0.076 ± 0.037 (max backup), and ties the uncapped head with the turn penalty (+0.018 ± 0.050, +0.034 ± 0.030).
- At fight level it is worse. In the three-source smoke of the A/B harness it lost 2.7 points per fight against
  production (HP lost +1.7) and 19 points per boss fight (HP lost +9.9; Collector, Awakened One, Heart). No fight
  stalled. Three sources only, so this is a direction, not a measurement.
- So the first-fight test does not carry over for this leaf (as for the change of §638). The capped head shares the
  property that probably hurts: on 58-61% of first-fight leaves its value is exactly win-now. If the running A/B wins,
  telling the head's share from win-now's would need a win-now arm; if it loses on bosses, the cap is a suspect.
- A looser cap binds rarely and keeps much of the first-fight gain in prod: min(head, win-now + 10) binds at 1-2% of
  leaves and gives -0.246 on the tuning fights, against -0.253 uncapped and -0.075 capped at win-now. With max backup
  it gives -0.183, no better than the plain cap (-0.177; uncapped -0.253). 150 fights, SE about 0.06. Whether +10
  still stops the stalls is untested at fight level.
- Update, after the A/B: it failed its gate (head − CPU-matched production, score −1.31 [−2.78, +0.14] per fight),
  better in normal fights and worse in elites and Acts 3-4 (`../silver_leaf_head_ab_20261022/RESULT.md`).

## Question

The candidate's leaf is 0.5 x (min(head, win-now) - 1 x (leaf turn - root turn)) + 0.5 x playout. Win-now is Silver's
victory score if the fight ended at the leaf (`SilverSearcher::winNowValue`: HP after post-battle heals, potions,
turn). On the first fights the cap binds at 58% (prod) and 61% (max backup) of leaf evaluations, cutting 3.6-3.8
points where it binds (table below), so more often than not the head half of the leaf is win-now. Two questions:

1. How much of the head's first-fight gain does win-now alone give, as a leaf with no net:
   L x win-now + (1 - L) x playout?
2. How much of the cap's cost (it keeps about 60% of the uncapped head's gain) comes from its tightness?

## Change

`apps/exact_combat_solver.cpp`, `--leaf-oracles`: a final `+capM` caps the head at win-now + M points (`+cap` is
M = 0 as before), and every capped mode adds `leafCapBinds` (leaf evaluations at which the cap bound) and `leafCapCut`
(head value it removed, summed) to the fight's summary row. Binary sha256 `f3ad5b11850ed935...` (preset
linux-gcc-release-x86-64-v3). The modes that existed before give identical rows: Two Louse 111149670-672, configs
prod and prod@mb=4, modes none, `hblend:a20:0.5/1` and `hblend:a20:0.5/1+cap`, 174 rows against the turn-penalty
test's binary `a214254f...`, equal apart from timings and the cumulative `replays` counter; `+cap0` equals `+cap`.

The win-now leaf needs no engine code: `make_wn.py` writes a head file whose output is always 10000 points
(`heads/a20.txt` with its output layer zeroed and offset 10000; `wn.txt`, sha256 `5efb2d2d2a07e1e7...`, on the share
as `exact-combat-research/leaf-value/heads/wn.txt`). Capped, it always binds, so `hblend:wn:L+cap` is exactly
L x win-now + (1 - L) x playout, and `/1` adds the turn penalty. The native flag reads the same file, so the fight-level
smoke ran the identical leaf.

## First fights

Exact first fights as in `../leaf_head_turn_penalty_20261022` (`run_tp.sh`, analysis `analyze_oracle.py`, outcome
`outcome_tp.py`): configs prod and prod@mb=4 (max backup). Paired change in exact regret per fight against the
playout leaf of the same config, ± SE over fights.

**Tuning fights** 111149600-649 (Cultist, Two Louse, Jaw Worm; 150 fights; the turn-penalty test's tuning set):

| leaf | prod | max backup | cap binds (prod / mb) |
|---|---|---|---|
| a20 head, `/1`, uncapped | -0.253 ± 0.075 | -0.253 ± 0.058 | |
| `+cap` (the A/B candidate) | -0.075 ± 0.064 | -0.177 ± 0.048 | 58.1% / 61.1% |
| `+cap5` | -0.230 ± 0.064 | -0.216 ± 0.056 | 16.3% / 18.5% |
| `+cap10` | -0.246 ± 0.074 | -0.183 ± 0.059 | 1.1% / 1.9% |
| `+cap20` | -0.253 ± 0.075 | -0.253 ± 0.058 | 0.0% / 0.0% |
| a20prod head, `/1` | -0.223 ± 0.068 | -0.134 ± 0.055 | |
| a20prod head, `/1+cap10` | -0.261 ± 0.068 | -0.105 ± 0.052 | 1.7% / 2.6% |
| win-now, L = 0.25 | -0.119 ± 0.072 | -0.131 ± 0.047 | (always) |
| win-now, L = 0.5 | -0.186 ± 0.084 | -0.227 ± 0.063 | |
| win-now, L = 0.5, `/1` | -0.123 ± 0.078 | -0.245 ± 0.062 | |
| win-now, L = 0.75 | -0.001 ± 0.133 | +0.166 ± 0.107 | |
| win-now alone (L = 1) | +3.748 ± 0.984 | +6.938 ± 1.275 | |

Where the plain cap binds it removes 3.6 points (prod) and 3.8 (max backup) on average. Win-now alone is far worse
than the playout: it ignores everything still to come in the fight.

**Fresh fights** 111333000-099 (300 fights; the turn-penalty test's confirmation set; the a20 and a20prod rows are
from `../silver_leaf_a20_prod_20261022` Part B, same fights, and every playout row agrees between the two runs):

| leaf | prod | max backup |
|---|---|---|
| a20 head, `/1`, uncapped | -0.251 ± 0.054 | -0.283 ± 0.048 |
| a20 head, `/1+cap` (the A/B candidate) | -0.149 ± 0.054 | -0.174 ± 0.050 |
| a20prod head, `/1` | -0.264 ± 0.054 | -0.214 ± 0.044 |
| win-now, L = 0.5 | -0.234 ± 0.067 | -0.249 ± 0.052 |
| win-now, L = 0.5, `/1` | -0.081 ± 0.067 | -0.190 ± 0.053 |

Paired, each leaf minus win-now L = 0.5 (`compare_modes.py`): the candidate +0.084 ± 0.058 (prod) and +0.076 ±
0.037 (max backup), the uncapped a20 `/1` -0.018 ± 0.050 and -0.034 ± 0.030, a20prod `/1` -0.030 ± 0.051 and
+0.035 ± 0.040. Outcome (`results/fresh_outcome.txt`): win-now L = 0.5 ends the fights with 0.3-0.5 more HP than the
playout leaf and takes longer, 2.9 turns against 2.4 (prod), 3.7 against 2.5 on Jaw Worm. L = 0.5 is the best of the
four weights on the tuning fights; the turn penalty hurts it on the fresh fights and in prod on the tuning fights.

## Fight level (smoke)

The A/B's smoke sources 111339997-999 in its harness (`run_unit.sh` environment, binary `83de6c12...`), arms
`base10000` and `head10000` only, with `STS_CTMSILVER_LEAF_HEAD=wn.txt`, `_BLEND=0.5`, `_WIN_CAP=1` and
`_TURN_PENALTY=0`: head10000 is the win-now blend at 10,000 simulations. 50 valid replayed fights (18 normal, 19
elite, 10 boss, 3 other), no invalid rows, no escapes, no stall (decisions per fight 52.4 against 50.4); CPU
head10000/base10000 1.15 per fight, 1.11 per simulation. Analyzed with the A/B's `analyze.py`, its arms cut to these
two and no matched arm. Paired contrasts win-now - production per fight, 95% bootstrap over the three sources
(descriptive), next to the capped a20 head's smoke on the same sources (`../silver_leaf_head_ab_20261022/smoke`; all
150 of its production and control rows equal this smoke's):

| fights | win-now: score | win-now: HP lost | capped a20: score | capped a20: HP lost |
|---|---|---|---|---|
| all (50) | -2.65 [-4.30, +0.36] | +1.72 [+0.03, +3.59] | -0.77 [-16.32, +2.59] | -0.39 [-0.68, +1.36] |
| boss (10) | -19.2 [-28.7, +5.0] | +9.9 [-0.9, +20.4] | -11.7 [-113.3, +3.0] | +2.85 [-0.25, +8.5] |
| elite (19) | -5.6 [-15.7, +1.4] | +0.9 [-0.9, +5.3] | -5.1 [-16.1, +1.9] | -0.8 [-2.5, +1.3] |
| normal and other (21) | +7.9 [+2.0, +15.4] | -1.4 [-2.0, -1.2] | +8.3 [+0.4, +16.9] | -1.5 [-2.1, -0.4] |

Boss fights, HP after the two redraws (X = died):

| source | boss | production | capped a20 | win-now |
|---|---|---|---|---|
| 111339997 | The Guardian | 43/39 | 56/55 | 52/55 |
| 111339997 | Collector | 75/50 | 75/59 | 39/46 |
| 111339997 | Awakened One | 103/70 | 61/70 | 29/19 |
| 111339997 | Time Eater | 82/43 | 60/32 | 53/50 |
| 111339997 | The Heart | 99/64 | 80/74 | 69/44 |
| 111339998 | Hexaghost | 8/10 | X/7 | 9/8 |
| 111339999 | The Guardian | 27/23 | 26/26 | 35/26 |
| 111339999 | Collector | 7/12 | 7/12 | 16/6 |
| 111339999 | Donu and Deca | 2/1 | 1/2 | 2/X |
| 111339999 | Awakened One | X/X | X/X | X/X |

Summed boss HP: production 758, capped a20 703, win-now 558.

The likely mechanism: win-now values a leaf as if the fight ended there, so it counts the HP the player has now and
ignores the enemies' HP and the damage still to come. In a first fight of 2-3 turns little damage lies ahead and the
blend helps; in a long boss fight that scales (Awakened One, Time Eater, the Heart) half of the leaf ignores most of
the fight's damage, which favors keeping HP now over killing faster. The first fights point the same way: the win-now
blend took more turns for a little more HP.

Traces of the four boss fights of source 111339997 that win-now lost (`STS_CTMSILVER_FIGHTS` and
`STS_CTMSILVER_LEAFHEAD_TRACE`; the reruns end with the smoke's HP; `results/wn_boss_traces.txt`) fit this. In three of
them the win-now blend dealt its damage later: after six turns the Heart had 342 HP left against production's 211
(after four, 552 against 474) and Time Eater 347 against 284; the Awakened One's first phase fell a turn later and the
fight took 10-11 turns against 8, while win-now held more HP early (90 against 78 after 2-4 turns) and lost it later.
The Collector fight went at production's pace but one turn longer in one redraw, and its HP went in the last turns.
Raw traces: `/mnt/project-files/silver-leaf-head-ab/smoke/wn_boss_traces_raw.tgz` (sha256 `90fb1f790905e497...`).

## Files

- `make_wn.py` (the constant head), `compare_modes.py` (paired differences across two solver runs).
- `results/`: `tune_analysis.txt`, `tune.json` (first tuning run), `tune2_analysis.txt`, `tune2.json` (win-now
  weights), `fresh_analysis.txt`, `fresh.json`, `fresh_outcome.txt`, `tune_outcome.txt`, `fresh_compare.txt`,
  `cap_binding.txt`, `smoke_wn_analysis.txt`, `smoke_wn.json`, `smoke_wn_fights.txt` (per fight), the capped a20
  smoke cut to the same two arms (`smoke_capped_a20_analysis.txt`, `smoke_capped_a20.json`), and
  `wn_boss_traces.txt` (the four traced boss fights).
- Raw smoke rows: `/mnt/project-files/silver-leaf-head-ab/smoke/smoke_wn_raw.tgz` (sha256 `aa6a8566e40b8b1b...`).

## Commands

From the repo root, `BIN` the solver above, `T=docs/experiments/evidence/leaf_head_turn_penalty_20261022`,
`D=docs/experiments/evidence/silver_leaf_a20_data_20261022`, `H=/mnt/project-files/exact-combat-research/leaf-value/heads`:

```
python3 make_wn.py $H/a20.txt wn.txt
bash $T/run_tp.sh $BIN tune tune 111149600 50 2 "none,hblend:a20:0.5/1,hblend:a20:0.5/1+cap,hblend:a20:0.5/1+cap5,\
hblend:a20:0.5/1+cap10,hblend:a20:0.5/1+cap20,hblend:wn:0.5/1+cap,hblend:wn:0.5+cap,hblend:a20prod:0.5/1,\
hblend:a20prod:0.5/1+cap10" "a20=$H/a20.txt,a20prod=$H/a20prod.txt,wn=wn.txt"
bash $T/run_tp.sh $BIN tune2 tune 111149600 50 2 "none,hblend:wn:0.25+cap,hblend:wn:0.75+cap,head:wn+cap" "wn=wn.txt"
bash $T/run_tp.sh $BIN fresh fresh 111333000 100 2 "none,hblend:wn:0.5/1+cap,hblend:wn:0.5+cap" "wn=wn.txt"
SEEDS=111149600:111149649 python3 $D/analyze_oracle.py tune.json tune/tune_*.jsonl
SEEDS=111333000:111333099 python3 $D/analyze_oracle.py fresh.json fresh/fresh_*.jsonl
SEEDS=111333000:111333099 python3 compare_modes.py hblend:wn:0.5+cap hblend:a20:0.5/1+cap fresh/*.jsonl PARTB/fresh_*.jsonl
```

The smoke: the A/B's `run_unit.sh` environment with `a20.txt` replaced by `wn.txt`,
`STS_CTMSILVER_LEAF_HEAD_TURN_PENALTY=0` and `STS_CTMSILVER_SWEEP_SIMS=10000`, one source per process. The traces:
the same environment plus `STS_CTMSILVER_FIGHTS=<fight index>` and `STS_CTMSILVER_LEAFHEAD_TRACE=<file>`, source
111339997, one process per fight (19, 28, 29, 31).
