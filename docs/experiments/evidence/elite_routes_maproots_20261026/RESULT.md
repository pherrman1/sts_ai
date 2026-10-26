# Elite routes at map roots: offline findings (2026-10-26)

Experiment 4 of the deep-research report (HP-gated tilt toward elite routes at map roots). Stopped offline: the
expert audit (#865) found no elite deficit, and the data below agree. No code, no seeds, no run design.

Data: existing records only. §683 (1,024 seeds x D/MAP/OFF), §661 (1,024 x A/M/S/MS), §676 (512 x A/C):
2,560 seeds, 8,192 games. Map graphs from the state records (`obs.map.xs/ys/roomTypes/pathXs`); "elite potential"
of a map child = max elites on any path from it to the act's last row. Scripts in this folder
(`elite_extract.py` -> per-game pickle; `a5.py` root choices; `a6.py` map natural experiment; `a7.py`+`a8.py`
first-divergence pairs). Run with `python3 -I`; `ELITE_DIR` holds the extracted unit tars of the three campaigns
(`u683/`, `u661/`, `u676/` from share `ooc-map-only-search/units`, `value-level-ab/units`,
`ctm-calibration-ab/units`) and the pickles. `elite_extract.py UNITS_DIR OUT.pkl` writes `elite<campaign>.pkl`.

## 1. Elite dose: no deficit
- Elites fought per act among games that clear the act (§683, all arms): 2.50 / 2.22 / 2.70; median 3 / 2 / 3.
- Heart killers pooled over the three campaigns (n = 1,956 games): 2.63 / 2.40 / 2.74, median 8 over acts 1-3
  (§683 alone, n = 731: 2.69 / 2.45 / 2.80); §683 Act-4 arrivals
  median 8 (mean 7.7). Baalorlord's winning runs: median 8, 3 in Act 1. Only 5.0% of bot winners (pooled) fought <= 1 Act-1 elite.

## 2. The bot already takes elite-heavy routes when healthy
Map roots where one child has more elite potential than another (§683): share that takes the elite-heavier child.

| HP | Act 1 | Act 2 | Act 3 |
|---|---|---|---|
| 80-99% | 0.87 | 0.84 | 0.88 |
| 60-79% | 0.82 | 0.70 | 0.79 |
| 40-59% | 0.73 | 0.50 | 0.60 |
| 20-39% | 0.55 | 0.26 | 0.38 |

At HP >= 40%, MAP, D and OFF (student_sel alone) agree within ~0.05: the choice is the prior's (take rate ~ prior
mass of the elite child). Below 40% the arms spread more (act 3, 20-39% HP: MAP 0.38 / D 0.28 / OFF 0.46; small n).
Search Q leans the same way: the Q gap of the elite-heavier child is positive from 40-59% HP in acts 1 and 3 and
from 60% in act 2, negative below. An HP-gated tilt
would flip only ~0.4 declined roots per game per act at HP >= 60%.

## 3. Natural experiment: maps with more reachable Act-1 elites (seed-determined, exogenous to play)
Kill-rate slope per extra reachable Act-1 elite at the first map root, seed-clustered bootstrap:

| campaign | elites fought per extra reachable | Heart kill | Act 4 | Act-1 clear |
|---|---|---|---|---|
| §683 | +0.57 | +7.1 pp [+3.7, +12.5] | +7.0 | -0.2 |
| §661 | +0.47 | +2.8 pp [-0.5, +6.3] | +3.4 | -1.3 |
| §676 | +0.49 | -0.8 pp [-6.9, +5.1] | -0.7 | -1.4 |
| pooled | +0.51 | **+3.8 pp [+1.4, +6.2]** | +4.1 [+1.3, +6.9] | -0.9 |

Unchanged with controls for reachable rest/shop/event/monster counts (+3.6 pp). Act 2: +0.8 pp [-1.7, +3.3];
Act 3: +3.9 pp [+0.5, +7.6] (conditional on reaching the act). Inference: Act-1 elite opportunity is worth
something; §683 alone overstated it (it was the first campaign looked at).

## 4. Paired test of the bot's own declines: first-divergence pairs
Same-seed arm pairs whose first differing state is a map root with children of different elite potential
(1,038 pairs; elite-heavier side minus other):
- Heart kill +1.6 pp [-1.2, +4.4]; Act 4 +1.9 pp [-1.4, +5.2].
- Act 1 (727): kill +1.2 [-2.1, +4.7]. Act 1 at HP >= 60% (594): +1.3 [-2.2, +5.1].
- Act 2 (241): kill +3.3 [-2.9, +9.5], Act 4 +9.1 [+2.5, +16.2] (small n, one of many cuts).
- HP < 40% (51): kill -5.9 [-17.6, +5.9].

Reading: at the roots where the bot's own variants disagree, taking the elite-heavier child is not measurably better
for kills. Point estimates suggest at most ~1-2 pp per flipped root, so a tilt that flips ~0.4 roots per game per
act would sit well below what a 1,024-seed paired A/B can detect (MDE ~3.5 pp). Caveat: divergence pairs are not
randomized (the two arms' policies also differ downstream).

## Conclusion
No elite deficit; the prior already routes into elites at high HP; the marginal declined elite is worth too little
to resolve. Experiment 4 stops. Only lead left: Act-2 mid-HP declines (take rate 0.50 at 40-59% HP, Act-4 +9 pp in
241 pairs), which is weak, post-hoc evidence and not worth a run on its own.
