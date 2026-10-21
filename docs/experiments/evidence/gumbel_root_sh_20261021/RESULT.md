# Gumbel sequential halving at OOC full-budget roots: offline target quality (2026-10-21)

**Question (Philipp, 15:04Z "Let's implement and test it"):** full-budget OOC roots are ~59% of run CPU
(`/mnt/project-files/az-speed-profile/REPORT.md`, 14:30Z addendum). Does a Gumbel AlphaZero root with sequential
halving (SH) give better root decisions and policy targets than PUCT at the same or a smaller budget?

**Setup.** Combined-stack A20 config (arm A of `az_gen1b_value_leaf_ab_20261020`, student_sel, learned stop in real
combats, fast-root cap 1024, boss-only prior playouts, `STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25`) plus
`STS_OOC_MCTS_ROOT_COMPARE`. At every full-budget root, after the real 4096-sim PUCT search, the same model runs:
- a **reference**: 8192 simulations split evenly over every root action, with PUCT below the root and its own seed. Its
  per-action Q is independent of both methods;
- **SH** with M = 4 and 16 (Gumbel scale 1) at 512/1024/2048 simulations, each with its own seed.

PUCT at k simulations is the main search's k-simulation checkpoint (full roots run without stops). Seeds
111145010–111145017, binary from `eb1f4364`. Seeds 014–017 stopped early at a container restart; every root they
finished counts. That gives 116 full roots from 8 runs. Root action counts: 2 (24), 3 (12), 4 (44), 5 (8), 7 (1),
8+ (27).

**Metrics** (`tools/analyze_gumbel_root_compare.py 2.371`, β = the production ADR-0043 constant):
- **regret** = Q_ref(best) − Q_ref(played). The max over noisy reference Q inflates every method by the same amount,
  so paired differences are unbiased.
- KL(π'_ref ‖ π'_method) between improved-policy targets.
- agreement with the reference's best action.

| method | KL(ref‖π') | agree | regret ×1e-3 | CPU s/root |
|---|---|---|---|---|
| prior argmax | – | 0.405 | 11.39 | – |
| PUCT 512 | 0.094 | 0.422 | 11.36 | ~3.5 |
| PUCT 2048 | 0.091 | 0.431 | 10.70 | ~14 |
| PUCT 4096 (production) | 0.060 | 0.440 | 10.08 | ~28 |
| SH M4 @512 | 0.071 | 0.517 | 8.26 | 3.6 |
| SH M16 @512 | 0.092 | 0.526 | 6.97 | 3.6 |
| SH M16 @1024 | 0.088 | 0.560 | 6.33 | 7.1 |
| SH M16 @2048 | **0.030** | **0.690** | **3.79** | 14.0 |

Paired SH − PUCT at matched simulations (95% bootstrap CI):
- **regret ×1e-3:** M16@2048 −6.91 [−10.33, −3.83]; M16@1024 −4.92 [−8.37, −1.75]; M16@512 −4.40 [−7.43, −1.50]. Every
  SH cell is below 0. M16@2048 against PUCT@4096: −6.30.
- **KL:** M16@2048 −0.062 [−0.112, −0.021]. At 512/1024 there is no difference (CIs straddle 0).

PUCT CPU is estimated from the reference's 6.8 s per 1k simulations. Full data is in [analysis.txt](analysis.txt).

**Interpretation.** PUCT at this budget barely leaves the prior: student_sel's top prior is ~0.99, and PUCT@4096 agrees
with the reference about as often as the prior argmax does. SH spends its visits on the sampled candidates and then
plays by Q, so it finds the action the leaf evaluator prefers more often, at half the root CPU (M16@2048).

**Caveat (decisive).** The reference uses the same leaf evaluator (rollout3 + X2-B). SH effectively plays argmax-Q
among the survivors, and argmax-Q root selection lost twice in real A20 play (§414, §560). Better agreement with leaf
Q is therefore not evidence of more Heart kills. Adoption needs a paired A20 play A/B: `STS_OOC_MCTS_GUMBEL_ROOT=16`
with full roots at 2048 against the current stack.

Raw rows: `/mnt/project-files/az-speed-profile/gumbel-compare/` ([rows.sha256](rows.sha256)).
