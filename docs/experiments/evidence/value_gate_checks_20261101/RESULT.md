# Value-gate checks: result (2026-11-01)

Protocol and data: [README.md](README.md). All three are offline; none changes a default.

## (a) Incense-holder subgroup BCE

ENS_rc (#915's model with relic-counter one-hots, incl. the Incense Burner phase) minus ENS_all (the same without),
out-of-fold, per-game BCE, seed-cluster bootstrap 95 % CI:

| dev core subgroup | entries / games / seeds | kill rate | ENS_rc − ENS_all | ENS_all + phase offsets − ENS_all |
|---|---|---|---|---|
| all | 2,174 / 3,798 / 1,110 | 65.1 % | −0.0001 [−0.0019, +0.0017] | −0.0005 [−0.0024, +0.0013] |
| Incense holders | 271 / 459 / 138 | 75.2 % | **−0.0038 [−0.0107, +0.0030]** | −0.0044 [−0.0199, +0.0108] |
| non-holders | 1,903 / 3,339 / 985 | 63.8 % | +0.0004 [−0.0013, +0.0022] | 0 (unchanged by construction) |

- "Phase offsets" is a minimal-capacity probe: one logit offset per entry phase (6), fitted out of fold on the
  training folds' holders with a N(0, 0.5²) penalty, added to ENS_all.
- Observed kill rate by entry phase (dev core holders, 37-64 entries each): 0.83 / 0.66 / 0.74 / 0.72 / 0.86 / 0.77.
- Holders are 12.1 % of dev-core games. A perfectly priced term of size ±Δ on every holder would lower holder BCE by
  Δ²/(2p(1−p)): 0.0024 / 0.0096 / 0.039 for Δ = 3 / 6 / 12 pp, i.e. 0.0003 / 0.0012 / 0.0047 in the aggregate.
  The aggregate CI half-width is 0.0018, so the aggregate gate only sees an entry-level phase effect of about ±11 pp on
  every holder; the holder-only CI (half-width ≈ 0.007) sees about ±7 pp (detectable gain taken as twice the half-width).

**Reading.** The whole point gain sits in the holders (−0.0038 there, +0.0004 elsewhere), and the aggregate dilutes it
by the holder share to −0.0001. The subgroup CI still includes 0 (271 entries), so the gain is suggestive, not shown.
The decision does not hinge on that: the arithmetic shows the aggregate BCE gate cannot see an Incense-size term at
this data size whatever the model, as #927 predicted. Rule (a) applies in its conservative form: judge state terms
like this one by targeted causal probes (the §723/§724/§731 design), and report subgroup BCE only as a secondary
number.

## (b) V_A4 learning curve

ENS_rc trained on nested seed subsets (hash rule) of each fold's training seeds, all sources thinned alike; test folds
and scoring unchanged:

| fraction | training entries (games) | BCE | Brier R² (dev core) | R² (run-1 entries) |
|---|---|---|---|---|
| 1/8 | 588 (767) | 0.533 | 0.216 | 0.197 |
| 1/4 | 1,141 (1,499) | 0.516 | 0.244 | 0.219 |
| 1/2 | 2,234 (2,938) | 0.502 | 0.266 | 0.235 |
| 1 | 4,387 (5,686) | 0.491 | 0.284 | 0.259 |

- Gain per doubling shrinks: +0.028, +0.022, +0.018.
- Power law R²(n) = R∞ − a·n^(−b): R∞ 0.348, b 0.36. Predicted R² at **10^5 training entries 0.327** (seed bootstrap
  of the fit [0.268, 0.409]; P(≥ 0.33) = 0.49). 10^5 production games give only ~4×10^4 Act-4 entries (37-42 %
  reach Act 4 in the stage-2 campaigns): predicted **0.319**.
- A log-linear fit (no saturation, an upper envelope) predicts 0.391 [0.329, 0.455] at 10^5 entries.
- The run-1-only fit degenerates (R∞ → 1, b 0.04), so only the pooled curve is used. The Bernoulli ceiling is about
  0.41-0.43 (§720/§722).

**Reading.** By the stated rule (point estimate < 0.33) the 10^5-game outcome-only capture is not bought: ~23k core-h
would raise V_A4's R² by about +0.035 (0.284 → ~0.32). The call is borderline (the bootstrap straddles 0.33; it resamples only test seeds with the predictions fixed and
extrapolates about 23× beyond the data, so the real interval is wider), and only
the no-saturation envelope reaches 0.39. Nothing on record uses V_A4 in play, and §727 shows value-led choices lose at
today's accuracy, so the borderline case does not justify the cost.

## (c) Simulated label-noise ceiling for sibling ranking

#644's analytic ceiling (0.80-0.87) plugs the observed sibling gaps into Φ(−|d|/se); noise inflates those gaps. Here
true action values are re-estimated per root and labels re-simulated as truth + the mean of 32 resampled repeat-residual
columns (common-seed structure kept), 20 simulations, §577 concordance per root → source → mean:
- naive: truth = observed means (reproduces the analytic number: 0.880 vs 0.873);
- js: posterior-mean shrinkage (too smooth → low);
- **vm: variance-matched scaling (centred SS = observed − noise) per root, the central estimate**; vm pooled uses one
  scaling per scope (map / non-map), which keeps noise-dominated roots' observed shape and so sits higher;
- hidden: vm plus #644's hidden-state term on every action (overstates deterministic siblings' noise → low).

| roots, labels | best head or blend (§715) | X2-B with M0 | ceiling vm | vm pooled | vm + hidden (val / train σ_h²) | js | naive | gap best → vm |
|---|---|---|---|---|---|---|---|---|
| map, M0 | 0.615 | 0.602 | **0.770** | 0.846 | 0.748 / 0.740 | 0.751 | 0.858 | **+0.155** |
| map, raw | 0.622 | 0.599 | 0.763 | 0.846 | 0.743 / 0.740 | 0.745 | 0.861 | +0.141 |
| non-map, M0 | 0.752 | 0.706 | 0.824 | 0.860 | 0.734 / 0.715 | 0.802 | 0.889 | +0.072 |
| non-map, raw | 0.733 | 0.684 | 0.792 | 0.840 | 0.711 / 0.696 | 0.762 | 0.885 | +0.058 |
| all, M0 | 0.719 | 0.681 | 0.811 | 0.857 | 0.737 / 0.721 | 0.790 | 0.881 | +0.092 |

(The best evaluator is picked post hoc from §715's 24, which flatters it slightly.)

**Reading.** At map roots, the only roots production searches (ADR-0061), the best head is 0.12-0.16 below the
ceiling under every truth model, including the lowest one. Label noise does not explain the map-root plateau, so
rule (c) does not stop value work there. Off the map the gap depends on the truth model: 0.06-0.07 below the central
ceiling, up to about 0.11 below the pooled one, and at or above the hidden-state variant. So the heads may be close to
the noise limit there, but this is not settled; production does not search those roots. These are rollout3 labels, the search's own estimator (§715 caveat), so "ceiling" means
agreement with that estimator, not with the true action value.

## Overall

| check | rule | outcome |
|---|---|---|
| (a) | subgroup visible, aggregate flat → targeted probes | holder gain −0.0038 (CI incl. 0), aggregate −0.0001; dilution makes the aggregate gate blind → **probes, not BCE, for state terms** |
| (b) | R²(10^5) < 0.33 → no capture | 0.327 at 10^5 entries, 0.319 at 10^5 games → **no outcome-only capture** (borderline) |
| (c) | best within 0.05 of ceiling → stop | map gap +0.12-0.23 under every variant → **do not stop on noise grounds**; non-map gap −0.05 to +0.11, unsettled |

Together: more outcome-only rows are not the lever (b, and §700), and the label-noise limit is not what blocks map-root
ranking (c). Map-root headroom has to come from what the labels and heads represent: features, level and scale
(§715), paired or fight-level labels (#927 ranks 14 and 16). Single state terms are judged by causal probes (a).
