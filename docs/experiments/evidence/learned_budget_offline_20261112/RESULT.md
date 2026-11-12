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

**3. Cost is predictable, but no allocation beats a uniform middle budget at equal CPU.** Extra CPU per fight for
16k → 64k ranges from 4 s (Gremlin Nob) to 480 s (Awakened One), and the cross-fitted prediction correlates 0.87-0.91
with it in log scale.

The two-level policies rank fights by predicted gain / predicted extra CPU. They send the top fights to the high
budget until a share q of the high arm's extra CPU is spent.

- **Against a random mix at the same CPU,** they look better. At q = 25% the gain is −0.2 HP per fight
  (g16 → g64) and about −0.55 HP (prod → g64mb), with CIs below 0. This comparison is misleading (review J, R1):
  a random mix of the low and high budget is the chord under a concave budget curve, so any policy that spreads
  the extra CPU over many fights beats it.
- **Against the real uniform middle budget,** which the data contain at its own CPU (32k, 32k mb, and g16mb for
  the prod ladder; q = 0.32 / 0.34 / 0.20), no policy is better. Values are HP per fight, policy − uniform middle,
  95% CI.

| ladder (middle) | cost only | encounter | ridge | boosting | boosting + probe | 3-level encounter | 3-level ridge + probe |
|---|---|---|---|---|---|---|---|
| g16 → g64 (32k, 10.49) | −0.10 [−0.34, +0.14] | −0.07 [−0.32, +0.18] | +0.02 | +0.17 | +0.07 | −0.03 [−0.23, +0.18] | +0.07 [−0.12, +0.26] |
| g16mb → g64mb (32k mb, 10.23) | +0.00 [−0.23, +0.24] | −0.07 [−0.28, +0.17] | +0.03 | +0.11 | +0.15 | −0.00 [−0.17, +0.18] | −0.07 [−0.29, +0.16] |
| prod → g64mb (16k mb, 10.49) | +0.25 [−0.03, +0.51] | +0.27 [−0.00, +0.53] | +0.20 | +0.35 [+0.08, +0.63] | +0.29 [+0.03, +0.55] | +0.04 [−0.15, +0.23] | −0.01 [−0.16, +0.16] |

The 3-level policies choose low, middle or high per fight. They use cross-fitted predicted increments and costs,
and one price λ set so that the predicted spend equals the middle arm's (realized 0.95-1.04× its CPU). They match
the uniform middle budget and do not beat it. On the prod ladder the two-level policies are worse than 16k mb
everywhere. All rows, including q = 10% / 25% / 50% against the random mix, are in `results/analysis.json`.

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
- **Variance decomposition in this currency (review J, R2):** the signal share is 10-11% on all three ladders (in HP
  it was ≈ 0 / 1% / 13%). Split-half r is still about 0, so that signal is not reproducible per fight with these
  copies. **Inference:** much of it comes from deaths, which carry 100-180 HP-equivalents and are rare per copy.
  The variance estimate is unstable with 3 copies, while the split-half check needs no noise model.
- **Against the uniform middle budget at its CPU:** no policy is better here either.
  - Two-level policies: −0.04 to +0.25 pp Heart-equivalent per fight; the only CI that excludes 0 is boosting on the
    prod ladder (+0.25 [+0.02, +0.50], worse).
  - 3-level policies: −0.13 to +0.12, every CI covering 0.
  - Against the random mix the policies still look better (prod ladder at q = 25%: −0.24 to −0.41). That is the
    concavity again.
- **Conclusion:** valuing deaths does not change the corrected result. A uniform middle budget is as good as any
  learned allocation on these fights.

## Interpretation (Inference)

- **The apparent allocation gain is the concave budget curve.** Spending some extra CPU on many fights beats spending
  it on a random few, and a uniform middle budget does that already. Learned allocation by encounter, state, cost or
  a cheap probe adds nothing measurable on top, in HP or in Heart pp.
- **Within an encounter, the state adds nothing that 4 copies can measure.** Split-half r ≈ 0 on every ladder.
  Encounter differences exist (p 0.001 with max backup in HP). Cost differences are about 100×.
- **Prod → g64mb has about 10-13% variance-signal share** (in HP and in Heart pp). It is not reproducible split-half,
  so it is not actionable with these data.
- **Scope:** Baalorlord's states, Act 1-3 elites and bosses, 16k-64k Gumbel (and production about 4.5k). The cheap
  end (1k-8k), hallway fights and Act 4 are not covered. §792's H4 (4k in hallway fights, NOT_WORSE at 0.82× CPU) is
  the one hand-set reallocation that worked in whole runs, and it is a uniform budget per room class.
- **HP lost undervalues bosses** (Act 1-2 heal); hence the B0 currency.

## Decision

- **Learned allocation at 16k-64k: NOT_SHOWN.** No learned policy beats a uniform middle budget at equal CPU. The
  earlier "beats a uniform budget" claim compared against a random mix and is withdrawn (review J, R1).
- Heterogeneity within an encounter is not shown at 16k → 64k. Between encounters it exists. Cost varies about 100×.
- **Step B** (a per-fight ladder at 1k-16k on our own states) now has a weaker prior. If it runs, its decision rule
  must compare with the uniform budgets of the ladder (the concave frontier), not with a random mix. It needs
  Philipp's typed go for seeds and workers. No default change. Cost: about 1 CPU-minute.
