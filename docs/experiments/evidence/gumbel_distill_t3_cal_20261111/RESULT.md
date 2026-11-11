# Gumbel distillation T3 (calibration only): the distilled net's value head as Silver Q-init

Offline analysis, no campaign, no gate. Philipp, 2026-11-11 20:33 CET ("oke lets try vlaue kopf bzw q init") and
20:36 CET (go for a cost smoke and a paired fight test on 40 workers). Before the fight test this calibration was run;
it showed the net value is less precise than a single Silver rollout, and Philipp chose to park the test (decision
card, 21:31 CET). No new seeds.

## Question

Q-init: when Silver expands a tree node, it starts the node's selection value from the net's value instead of from
nothing, as if the node already had w virtual visits worth the net's value:
`Q_sel = (evaluationSum + w · V_net) / (n + w)`. This only helps if V_net is at least comparable in precision to the
rollouts it is mixed with. How precise is T1's generalist N_f1 (P-V_f1, §787) value head on Silver's score scale, and
how noisy is one Silver rollout?

## Data

- **Net error.** `t3cal.py` (run on the PC GPU, tools/combat_net at 2abe6aa7d) wrote `t3cal_val.npz` (330,542 rows,
  T1's validation split h = 1 of D2; sha256 in `results/SHA256SUMS`; transfer ref ppo-xfer/t3-cal c0936cb2, copy on
  the share at `/mnt/project-files/gumbel-distill/t3/t3cal_val.npz`): the 21 value-class probabilities of N_f1 (death + 20 end-HP/maxHP bins, value
  NLL 1.66), the root's visit-weighted mean Q of the 16k G16 + mb4 search (rootQ), the fight score, hp, maxHp, potion
  count, act, room, encounter.
- `cal.py t3cal_val.npz coefs.json` fits rootQ on [1, P(win), E[end HP], potions, hp] by least squares, per encounter
  (global fit for encounters with < 2,000 training rows), on a seed-hash split (60 / 37 of 97 buckets); output
  `results/cal.txt`, coefficients `results/coefs_per_encounter.json`.
- **Rollout noise.** Temporary instrumentation in `SilverSearcher::updateFromPlayout` (not committed): per Gumbel
  root, for every root edge with ≥ 100 playouts, the within-edge variance of the playout returns, pooled over edges
  (one `[rollsd]` line per root). Four §775 G16 games replayed locally with T2's binary 7f2800f0 + the
  instrumentation (seeds 111378258, 111378261 (Heart kill), 111378280, 111378283; same games as §775 by log).
  Lines in `results/rollsd_lines.txt`, pooled with `rollsd_pool.py` → `results/rollsd.txt`.

## Result

Net value against the search's root Q (held-out seeds, 128,315 rows):

| fit | R² | residual sd |
|---|---|---|
| rootQ ~ hp + potions (global) | 0.43 | 31.9 |
| rootQ ~ net features + hp + potions (global) | 0.52 | 29.3 |
| per encounter, within-encounter R² (hp + potions only) | 0.37 | |
| per encounter, within-encounter R² (net features) | **0.48** | 27.5 |
| per encounter, rich (all 21 classes) | 0.50 | 27.1 |

Residual sd of the per-encounter net calibration, by fight type (rootQ's own sd in brackets):

| act | normal | elite | boss |
|---|---|---|---|
| 1 | 10.7 (19.0) | 15.7 (23.2) | 25.9 (35.7) |
| 2 | 17.7 (30.1) | 26.4 (39.5) | 31.4 (44.0) |
| 3 | 22.7 (33.6) | 32.3 (45.4) | 39.5 (53.4) |
| 4 | | 35.3 (49.0, Shield and Spear) | 49.1 (56.6, Heart) |

Root Q vs fight score: corr 0.89, Q on average 15.2 below the score (as in T0).

Rollout noise, pooled within-root-edge sd of one playout's return: act 1 **13.2** (690 roots), act 2 **13.4** (691),
act 3 **21.9** (356), act 4 **30.1** (99).

## Reading (inference)

- The net's error is about 0.8-2.3x the noise of a single rollout (act 1 normal 10.7 vs 13.2, the only cell where
  the net is slightly better; act 1 boss 25.9 vs 13.2; act 3 22.7-39.5 vs 21.9; Heart 49.1 vs 30.1). Mixed as Q-init,
  its inverse-variance weight is w ≈ (σ_roll / σ_net)² ≈ 0.18-1.5 virtual visits, so after 2-3 real visits it no
  longer matters. Each Q-init costs a net forward (about 2.5 ms against
  about 50 µs per simulation), about 50x CPU if done at every new node.
- As a replacement for the rollout (leaf value), the net would be worse than today's rollout.
- The comparison flatters the net: the error is measured at real root states (the net's training distribution, held-out
  seeds); deep tree nodes are further from it. It also does not include the rootQ target's own noise (small at 16k
  simulations), which would make the net's error slightly smaller.
- Half of what the net explains (R² 0.37 of 0.48 within encounter) is already in hp and potions.
- For the value head to become a useful leaf or Q-init, its error must fall well below the rollout noise. That needs
  a stronger value net (more teacher data aimed at value, value-only training, possibly a target closer to the
  rollout return), not this search test.

## Decision

Q-init fight test parked (Philipp, 2026-11-11 21:31 CET). No code change: the parked searcher change (node
net value, blend in selection, init before the first rollout; backend not written) is kept as `qinit-wip.patch`
against main 21a6baf2 as a starting point if a stronger value net exists.
