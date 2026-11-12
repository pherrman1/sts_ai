# Learned encounter budget, step A: offline heterogeneity check on existing fight data (result, 2026-11-12)

Offline only: no new games, no seeds, no workers. Question (Philipp, 2026-11-12 17:31 CET, "und ein gelerntes sim
budget nach encoutner?", go 17:34 CET "ja mach das mal"): does the value of more combat simulations vary
predictably by encounter and entry state, enough that a learned per-fight budget beats a uniform budget at equal CPU?
Design and next steps: [learned-encounter-budget.md](../../../knowledge-base/research/combat-search/learned-encounter-budget.md).

## Data

- §770 / §772 / §774 (teacher check, Gumbel budget, max backup at 32k/64k): 1,878 act-1-3 elite and boss fights of
  309 Baalorlord runs, every fight played 4 times (same copy seeds) under production (learned stop, about 4.5k sims
  per decision) and the Gumbel root (`gsh16`) at flat 16k / 32k / 64k, with and without max backup 4.
- Share archives `combat-plan/{teacher-check,gumbel-budget,gumbel-mb-budget}/ARCHIVE-units-20261110.tar.xz`,
  extracted locally. `extract_rows.py` (a copy of §774's `analyze.py` that also keeps entry features and per-copy
  values) reproduces §774's selection: 1,878 fights, 0 dropped, 0 conflicts, production reproduction 1,878 / 1,878.
  Rows: `results/rows.json.gz`. Analysis: `python3 -I analyze.py rows.json results/analysis.json`.
- Outcome: HP lost per fight (§774's definition, 0 HP left on a loss). Gain = HP lost at the low budget minus HP lost
  at the high budget, on copies 1-3 (copy 0 of production is held back as a "probe" feature, i.e. a cheap first
  search). Features at fight entry: act, room, floor, HP, max HP, HP share, deck size, upgrades, relic and potion
  counts, encounter, relics and potions seen ≥ 40 times.
- Ladders: plain g16 → g64, max backup g16mb → g64mb, and production → g64mb (the widest budget step available).

## Results

**1. Within an encounter, the per-fight gain is not measurable above copy noise.**

| ladder | mean gain (HP, 95% CI) | variance total / copy noise / signal | split-half r | encounter Q (17 df) |
|---|---|---|---|---|
| g16 → g64 | +0.41 [+0.18, +0.63] | 28.3 / 30.4 / ≈ 0 | −0.09 | 18.4 (p 0.37) |
| g16mb → g64mb | +0.51 [+0.28, +0.76] | 31.9 / 31.5 / 0.4 (1%) | +0.02 | 40.2 (p 0.001) |
| prod → g64mb | +1.65 [+1.35, +1.97] | 43.0 / 37.6 / 5.4 (13%) | +0.07 | 62.4 (p < 0.001) |

Split-half r correlates the gain on copies 0-1 with the gain on copies 2-3 of the same fight. Between 16k and 64k a
fight that profits on two copies does not profit more on the other two. Some of the heterogeneity that exists sits
between encounters: the gain from the widest step ranges from +0.2 HP (Gremlin Nob) to +5.5 HP (Awakened One).

**2. State features predict the gain barely better than the encounter.** These are cross-fitted correlations with
the realized gain (5 folds by run). For g16mb → g64mb: encounter mean 0.10, ridge on all features 0.08, gradient
boosting 0.06. For prod → g64mb: 0.13 / 0.17 / 0.12, and 0.19 for ridge with the probe.

**3. Cost is predictable, and an allocation that uses it beats a uniform budget at equal CPU.** Extra CPU per fight
for 16k → 64k ranges from 4 s (Gremlin Nob) to 480 s (Awakened One), and the cross-fitted prediction correlates
0.87-0.91 with it in log scale. In the table, a policy ranks fights by predicted gain / predicted extra CPU and
gives the high budget to the top fights until 25% of the high arm's extra CPU is spent. Against that it sets
spending the same CPU at random (the uniform mix). Values are HP per fight, negative = the policy loses less HP.

| ladder | cost only (gain = const) | encounter | ridge | boosting | boosting + probe | oracle (copies 0-1 → 2-3) |
|---|---|---|---|---|---|---|
| g16 → g64 | −0.23 [−0.37, −0.08] | −0.19 [−0.34, −0.04] | −0.20 [−0.34, −0.05] | −0.05 [−0.17, +0.07] | −0.09 [−0.23, +0.05] | −0.08 [−0.23, +0.06] |
| g16mb → g64mb | −0.04 [−0.18, +0.11] | −0.14 [−0.26, −0.02] | −0.05 [−0.18, +0.10] | +0.02 [−0.11, +0.13] | +0.02 [−0.11, +0.14] | −0.13 [−0.27, +0.01] |
| prod → g64mb | −0.59 [−0.75, −0.41] | −0.55 [−0.72, −0.39] | −0.58 [−0.75, −0.40] | −0.52 [−0.68, −0.36] | −0.55 [−0.73, −0.37] | −0.45 [−0.66, −0.25] |

For prod → g64mb, the uniform mix at 25% of the extra CPU gains 0.41 HP. The policy gains about 1.0 of the 1.65 HP
that 64k everywhere would bring. It does that by giving the high budget to 75-80% of the fights (the cheap elites,
about 10-30 s extra each) and leaving the expensive bosses low. The q = 10% and 50% points, and the plain and max-backup
ladders, are in `results/analysis.json`.

## Step B0: run-value currency (offline, added 2026-11-12)

`currency.py` fits V = P(Heart kill | state after a won fight) on §775's 2,048 traced games
(`../gumbel_wholerun_trace_20261109/results/battles.csv.gz`, 43,996 won Act 1-3 fights, arms D and G16). It uses
5 folds by seed. Output: `results/currency.json`.

- Fit:
  - Monotone gradient boosting (HP increasing) has a cross-fitted log loss of 0.626, against 0.642 for the logistic
    model and 0.661 for the act × room base rate (pooled arms).
  - It is calibrated within about 3 pp per decile, except the top decile (0.89 predicted vs 0.85 observed).
- Exchange rates (pooled):
  - +1 HP after a fight is worth 0.27-0.67 pp Heart: about 0.3 in Acts 1-2 and 0.46-0.67 in Act 3.
  - A death costs V(alive) = 37-77%, so one death is worth about 100-180 HP.
- Caveat (Inference): V is associational. HP after a fight also proxies deck strength, so dV/dHP is probably
  overstated. A causal check is the Heart-entry HP perturbations (`heart_entry_perturb*`). `hp_post` includes the
  heals after a fight; `to_heart.py` therefore counts Act 1-2 boss HP at 25% (A20 heals 75% of missing HP at the next act).

**Step A in this currency** (`to_heart.py` → `analyze.py`, `results/analysis_heart.json`; units = pp Heart-equivalent per fight):

- **Gains:**
  - g16 → g64: +0.36 [+0.14, +0.59].
  - g16mb → g64mb: +0.27 [+0.05, +0.49].
  - prod → g64mb: +0.95 [+0.72, +1.19].
  - Split-half r is still about 0 (0.00-0.05).
- **Policy at 25% of the extra CPU, against the matched-CPU random mix (prod → g64mb):**
  - cost-only −0.37 [−0.53, −0.21];
  - encounter −0.24 [−0.39, −0.09];
  - ridge −0.41 [−0.57, −0.24];
  - boosting −0.24;
  - split-copy oracle −0.16.
- **16k → 64k ladders:** only cost-only and encounter reach CI < 0, for g16 → g64 at −0.12 to −0.17.
- **Conclusion:** the conclusion holds when deaths are valued. The allocation gain comes from cost, and a state model
  adds nothing measurable over cost plus encounter.

## Interpretation (Inference)

- **A learned budget pays mostly through cost, not through gain.** Encounters differ about 100× in the price of more
  simulations and at most a few times in what the simulations buy. Within an encounter, the state adds nothing that
  can be measured with 4 copies per fight. A model that "knows" which fights profit has no data to learn this from
  between 16k and 64k.
- **The widest step (about 4.5k → 64k) shows real heterogeneity (13% of the variance, p < 0.001 across
  encounters).** This fits §779 and §792: the value of more simulations sits at the cheap end, where the PPO budget
  is. The cheap end (1k-8k) under the Gumbel root has no per-fight paired data yet, and neither do hallway fights or
  Act 4.
- **HP lost is the wrong currency for bosses.** After the Act 1 and Act 2 bosses, 75% of the missing HP is healed, so
  there a boss's HP barely counts and its death decides. Simulations above 16k avoid about 1 pp of boss deaths in Acts 1-2
  (16k → 64k: B1 0.8 pp, B2 1.6 pp; prod → g64mb about 3 pp) at 80-225 s per boss fight. The cost-only policy
  starves exactly these fights. So the HP result cannot choose between "budget to elites" and "budget to bosses". A learned budget needs a
  run-value currency (death and carried HP converted to Heart probability) before it can be trusted.
- Baalorlord's states, not our agent's. Act 1-3 elites and bosses only.

## Decision

The step-A rule from the design doc was to proceed only if per-fight heterogeneity is predictable. The result:

- Heterogeneity within an encounter is not shown between 16k and 64k.
- Heterogeneity between encounters and in cost is large.

So the learned budget is worth pursuing as a **cost-aware allocation by encounter and state at the cheap end**, not
as a state-level gain predictor above 16k. Step B, a paired per-fight budget ladder at 1k-16k on our own cheap-stack states with a run-value currency,
needs Philipp's typed go for seeds and workers. No default change. Cost: about 1 CPU-minute.
