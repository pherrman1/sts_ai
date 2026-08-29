# Rank-4 residual state×action Silver visit policy (2026-08-30)

## Decision

**`RANK4_INTERACTION_VISIT_POLICY_REPLAY_INCONCLUSIVE`**.

This single fixed rank-4 residual provides neither exploratory support nor a
rejection of all nonlinear policies. Against frozen grouped linear, it improved
frozen-B best-action probability by `+0.793651 pp`, but worsened mean frozen-B
regret by `+0.144530`; its paired 95% root-bootstrap intervals include zero for
both measures. No rank, initialization, feature, temperature, or PUCT tuning
was performed after seeing these values.

## 1. Implementation and optimization validity

- Baseline merge / PR #85 containment: `2f9e48c41cfb19b1879ef8055ef280d6962b2b10`
  contains `510fb3e4b912470d5c1de4155d62298ebc688cd6`.
- Model: `z(s,a)=z_grouped_linear(s,a)+sum_{k=1}^4(u_k^T s)(v_k^T a)`;
  the 1,766-state / 22-action partition, frozen grouped weights, train-only
  mean/scale/active mask, no interaction bias, no temperature, and exact
  normalized 25k-A visits are fixed.
- PyTorch CPU float64 was deterministic (`seed=20260830`, deterministic
  algorithms enabled); `U~Normal(0,1e-3)`, `V=0`; full-batch L-BFGS used
  `max_iter=500`, `history_size=50`, strong-Wolfe line search, and fixed L2
  `1e-4`. The final penalized objective was `0.3503692825`, below the exact
  linear initialization `0.7756896654`.
- Zero residual reproduced all 63 frozen grouped-linear distributions with
  maximum absolute probability error `2.22e-16` (requirement `<=1e-12`).
  The independently repeated fit produced byte-identical U/V arrays and anchor
  probabilities. Replay-prior export preserved every probability exactly.
- Inputs matched the supplied feature/corpus/relabel/model/probability/snapshot
  hashes. The feature schema is exactly 1,788 fields: the frozen 1,766-state
  prefix followed by the ordered 22-action suffix from `aIsCard` through
  `aSelObtainWeight`. The 93 anchors remained outside fitting and preprocessing.

## 2. Offline diagnostics

Offline quantities are diagnostics only. On the 63 multi-action anchors,
interaction rank-4 versus grouped linear had CE/KL `5.725053/5.231697` versus
`1.392368/0.899012`, TV `0.564858` versus `0.511496`, entropy MAE `0.408935`
versus `0.845315`, and max-mass MAE `0.185829` versus `0.423552`.

The interaction changed the prior argmax on 34 roots and had mean/max TV from
grouped linear `0.541973/0.989245`. It was trained only on the 327 train
parents; 75 validation parents were diagnostic only and 93 anchors were fully
excluded. These contrasting shape diagnostics are not search evidence.

## 3. Frozen replay result

The archived source/binary `581b68bb31a8b62bb94e88c5b783e042880746b1` /
`d8d08392343ab442ec093e5fa07b64b326755560ff374dfba61bbce9c1a18006` ran
exactly 63 roots × 4 replicate seeds × 3 arms = 756 rows at 32 simulations.
Frozen 25k-B was the only judgment source. Concurrent controls reproduced
exactly: current UCT `41.269841% / 4.051736`, oracle visit-PUCT
`51.190476% / 3.505948`; interaction was `44.444444% / 3.914213`.

| Interaction comparison | B-best delta (95% root CI) | Regret delta (95% root CI) | Improved / worsened / tied roots |
| --- | ---: | ---: | ---: |
| grouped linear | `+0.793651 pp` (`[-3.968254,+5.555556]`) | `+0.144530` (`[-0.209479,+0.626566]`) | 12 / 8 / 43 |
| current UCT | `+3.174603 pp` (`[-3.174603,+9.920635]`) | `-0.137523` (`[-0.651184,+0.419239]`) | 19 / 18 / 26 |
| rank-shape | `+1.984127 pp` (`[-3.174603,+7.539683]`) | `-0.112805` (`[-0.330524,+0.095949]`) | 13 / 11 / 39 |
| oracle | `-6.746032 pp` (`[-11.904762,-1.984127]`) | `+0.408265` (`[+0.080783,+0.822429]`) | 4 / 17 / 42 |

The interaction recovered `32.00%` of the concurrent oracle B-best gain and
`25.20%` of its regret reduction versus current UCT. The primary grouped-linear
comparison misses both support conditions (regret point estimate is harmful;
no favorable interval excludes zero) and rejection conditions (both point
estimates are not neutral/worse; both intervals do not rule out 20% recovery).

The inherited grouped replay's manifest declares SHA-256 `9cdfe…add7f`, but
the committed JSONL available to this worktree hashes `a545…3e5c`. This
discrepancy is retained in the manifest rather than rewritten. The comparison
was limited to artifacts whose source/executable, 63 root/replicate keys,
search seeds, snapshot/relabel hashes, headers, and every current/oracle
control row align exactly; those compatibility checks passed. No numerical
comparison was made with the incompatible raw-count replay.

## 4. Scientific interpretation

This is exploratory search-level evidence on 63 repeatedly examined frozen
roots, not gameplay or playing-strength confirmation. The fixed rank-4
bilinear residual did not meet the predeclared rule for support, and its result
does not establish that nonlinear policies fail generally. A favorable result
would still have required fresh-root or paired-gameplay confirmation; this
inconclusive result does not authorize an automatic rank sweep, generic MLP,
calibration, or PUCT tuning.

## Reproducibility artifacts

Machine artifacts and the full commands/settings are in
`build/silver_rank4_interaction_policy_20260830/`: model
`a9f4ba81…98cf`, anchor probabilities `8611c1c5…b4c0`, replay priors
`d2366e72…cec6d`, raw replay `36008e52…b7634`, offline report
`22ea9c6b…09c8`, replay analysis `4c4e9dcb…58fac`, and
`replay_manifest.json` for the complete SHA inventory.
