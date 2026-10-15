# Paired analysis of the Silver root-oracle replay (2026-08-29)

This report strengthens the existing 1,260-row replay. It does not change the
replay implementation, add a prior mechanism, run gameplay, or train a model.

The analysis treats each root as the paired unit separately at each budget;
budgets are never pooled. Top-choice delta is treatment correctness minus
control correctness. Regret delta is treatment frozen-25k-B regret minus
control frozen-25k-B regret, so negative is better. The median is the median
of the per-root regret deltas. Bootstrap intervals resample the 63 roots with
replacement 10,000 times using Python `random.Random(20260829)` and the
inclusive percentile rule.

## Results

Counts are `treatment-only correct / control-only correct / both correct /
neither correct`. Regret counts are `improved / worsened / tied`, where
improved means lower treatment regret.

| Budget | Comparison | Top counts | Top delta | Top bootstrap 95% CI | Mean regret delta | Regret bootstrap 95% CI | Median delta | Regret improved / worsened / tied | Largest negative delta (root) | Largest positive delta (root) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 16 | oracle-order UCT vs current UCT | 8 / 3 / 28 / 24 | +7.937 pp | [-1.587, +17.460] pp | -0.196899 | [-1.578378, +1.123395] | 0.000000 | 11 / 5 / 47 | -30.904693 (`b43ac0e76e2bdbcf`) | +26.113012 (`e8baedda4491fd9d`) |
| 16 | visit-PUCT vs current UCT | 7 / 4 / 27 / 25 | +4.762 pp | [-4.762, +15.873] pp | -0.180556 | [-1.552694, +1.111647] | 0.000000 | 13 / 8 / 42 | -30.904693 (`b43ac0e76e2bdbcf`) | +26.113012 (`e8baedda4491fd9d`) |
| 16 | rank-PUCT vs oracle-order UCT | 2 / 7 / 29 / 25 | -7.937 pp | [-17.460, +1.587] pp | +0.183256 | [-0.055200, +0.477417] | 0.000000 | 5 / 8 / 50 | -1.775520 (`cbda52b79d033fbb`) | +5.853217 (`b9a1e083f6f9ba66`) |
| 16 | visit-PUCT vs rank-PUCT | 3 / 0 / 31 / 29 | +4.762 pp | [0.000, +11.111] pp | -0.166913 | [-0.414141, 0.000000] | 0.000000 | 3 / 0 / 60 | -5.853217 (`b9a1e083f6f9ba66`) | 0.000000 (`fcff37fbf3dfd4f3`) |
| 32 | oracle-order UCT vs current UCT | 4 / 2 / 28 / 29 | +3.175 pp | [-4.762, +11.111] pp | -0.368677 | [-1.066603, +0.016235] | 0.000000 | 6 / 2 / 55 | -20.211319 (`fcff37fbf3dfd4f3`) | +0.803014 (`4642ca7fef733152`) |
| 32 | visit-PUCT vs current UCT | 8 / 2 / 28 / 25 | +9.524 pp | [0.000, +19.048] pp | -0.639986 | [-1.441007, -0.074749] | 0.000000 | 11 / 3 / 49 | -20.211319 (`fcff37fbf3dfd4f3`) | +2.124883 (`cbda52b79d033fbb`) |
| 32 | rank-PUCT vs oracle-order UCT | 3 / 2 / 30 / 28 | +1.587 pp | [-4.762, +7.937] pp | -0.157740 | [-0.441189, +0.048977] | 0.000000 | 5 / 3 / 55 | -6.903595 (`487b75069c104cd0`) | +1.820925 (`d8e296a7f99f20ab`) |
| 32 | visit-PUCT vs rank-PUCT | 3 / 0 / 33 / 27 | +4.762 pp | [0.000, +11.111] pp | -0.113569 | [-0.356472, +0.054942] | 0.000000 | 3 / 1 / 59 | -5.853217 (`b9a1e083f6f9ba66`) | +1.775520 (`cbda52b79d033fbb`) |
| 64 | oracle-order UCT vs current UCT | 0 / 1 / 29 / 33 | -1.587 pp | [-4.762, 0.000] pp | +0.043578 | [0.000000, +0.122003] | 0.000000 | 0 / 2 / 61 | 0.000000 (`07424d8f44b8ec48`) | +2.195291 (`228eb64487cab54d`) |
| 64 | visit-PUCT vs current UCT | 8 / 5 / 25 / 25 | +4.762 pp | [-6.349, +15.873] pp | -0.106608 | [-1.154359, +1.090221] | 0.000000 | 10 / 7 / 46 | -20.211319 (`fcff37fbf3dfd4f3`) | +26.455154 (`d57f03f5296931a0`) |
| 64 | rank-PUCT vs oracle-order UCT | 7 / 4 / 25 / 27 | +4.762 pp | [-4.762, +15.873] pp | -0.082583 | [-1.166866, +1.112979] | 0.000000 | 9 / 8 / 46 | -20.211319 (`fcff37fbf3dfd4f3`) | +26.455154 (`d57f03f5296931a0`) |
| 64 | visit-PUCT vs rank-PUCT | 2 / 1 / 31 / 29 | +1.587 pp | [-3.175, +6.349] pp | -0.067603 | [-0.278070, +0.144124] | 0.000000 | 4 / 1 / 58 | -3.702836 (`9b0feff1a2845158`) | +4.539911 (`d0b6bef005e2cb36`) |
| 128 | oracle-order UCT vs current UCT | 3 / 0 / 27 / 33 | +4.762 pp | [0.000, +11.111] pp | +0.046787 | [-0.346503, +0.535746] | 0.000000 | 4 / 1 / 58 | -6.903595 (`487b75069c104cd0`) | +11.811842 (`fcff37fbf3dfd4f3`) |
| 128 | visit-PUCT vs current UCT | 12 / 4 / 23 / 24 | +12.698 pp | [0.000, +25.397] pp | -0.700979 | [-2.297620, +0.705169] | 0.000000 | 16 / 5 / 42 | -35.195135 (`f47c1d6977c181fd`) | +26.455154 (`d57f03f5296931a0`) |
| 128 | rank-PUCT vs oracle-order UCT | 8 / 6 / 24 / 25 | +3.175 pp | [-7.937, +14.286] pp | -0.563853 | [-2.254802, +0.936818] | 0.000000 | 11 / 9 / 43 | -35.195135 (`f47c1d6977c181fd`) | +26.455154 (`d57f03f5296931a0`) |
| 128 | visit-PUCT vs rank-PUCT | 4 / 1 / 31 / 27 | +4.762 pp | [-1.587, +11.111] pp | -0.183913 | [-0.462771, +0.075877] | 0.000000 | 6 / 1 / 56 | -4.524261 (`228eb64487cab54d`) | +4.539911 (`d0b6bef005e2cb36`) |
| 1000 | oracle-order UCT vs current UCT | 2 / 0 / 38 / 23 | +3.175 pp | [0.000, +7.937] pp | -0.219313 | [-0.554171, +0.007760] | 0.000000 | 3 / 1 / 59 | -6.903595 (`487b75069c104cd0`) | +0.488853 (`228eb64487cab54d`) |
| 1000 | visit-PUCT vs current UCT | 7 / 7 / 31 / 18 | 0.000 pp | [-11.111, +11.111] pp | -1.491264 | [-3.377971, +0.020097] | 0.000000 | 8 / 8 / 47 | -35.195135 (`f47c1d6977c181fd`) | +8.452180 (`07424d8f44b8ec48`) |
| 1000 | rank-PUCT vs oracle-order UCT | 5 / 12 / 28 / 18 | -11.111 pp | [-23.810, +1.587] pp | -0.392357 | [-2.359843, +1.366017] | 0.000000 | 6 / 14 / 43 | -35.195135 (`f47c1d6977c181fd`) | +26.455154 (`d57f03f5296931a0`) |
| 1000 | visit-PUCT vs rank-PUCT | 7 / 2 / 31 / 23 | +7.937 pp | [0.000, +17.460] pp | -0.879594 | [-1.965874, -0.081084] | 0.000000 | 9 / 3 / 51 | -26.455154 (`d57f03f5296931a0`) | +4.539911 (`d0b6bef005e2cb36`) |

## RNG pairing status

All four arms for a given root/budget used the same saved `BattleStateWire`,
the same 25k-A teacher RNG identity, fresh search statistics, and the same
Silver search configuration apart from the root treatment. This is common
initial-seed control.

They did not share identical realized search/chance RNG conditions after the
first treatment-dependent choice. Root ordering changes which action is
expanded; rank/visit PUCT changes subsequent edge selection. Those paths can
consume different numbers and categories of random draws, so later chance
outcomes are not aligned across arms. The current 1,260-row output is
therefore paired by root and common initial seed, but is **not a fully paired
stochastic comparison** with matched random trajectories.

The bootstrap intervals quantify variation over the 63 frozen roots, not the
additional stochastic variance that would be estimated by repeated matched
seed replicates.

## Decision

The point estimates still suggest useful behavior in places, but the paired
root evidence is not stable enough to change integration:

- Oracle-order UCT has positive point top-choice deltas at four of five
  budgets, but its intervals include zero or substantial harm at 16, 32, 64,
  and 128. Its 1000-simulation regret interval also reaches slightly positive
  harm.
- Visit-PUCT has the strongest point regret result at 1000 and a negative
  regret interval at 32, but its 16/64/128/1000 regret intervals include
  material positive harm; its 1000 top-choice delta is exactly zero with an
  [-11.111, +11.111] pp interval.
- Every median regret delta is zero because most root pairs are tied in
  frozen-B regret. The mean results are visibly sensitive to large individual
  root deltas, including positive outliers of +26.455 and +26.113 Q units and
  negative outliers down to -35.195 Q units.
- Rank-PUCT is not a stable control for the visit-prior result; at 1000 it is
  11.111 pp below oracle-order UCT on top choice, with a wide interval.

Following the preregistered decision rule for this follow-up, recommend a
small repeat of the root replay with a few matched RNG replicates per root
before changing prior integration. Use the same replicate seed set for every
arm and analyze root×replicate pairs at each budget. Four replicates per root
is the smallest useful next check; it would remain offline and would not
require gameplay or model training. Do not implement a new prior formula yet.
