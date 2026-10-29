# OOC root quality: action gap, relative bias, search variance, coverage

Last verified: 2026-10-28 against `main` `9164445` (definitions only; no measurement yet). Measurement design:
[PREREG draft](../../../experiments/evidence/ooc_root_quality_20261028/PREREG.md).

## Purpose / research question

Philipp, 2026-10-28: can we compute the "root quality" of a few real OOC roots (card rewards first), with exact
definitions of the four quantities of the simple-regret view of one root decision: the true action gap Δ, the
relative search/leaf bias B_rel, the search variance σ and the coverage q? The goal is curves
P(wrong card | N, h) and E[simple regret | N, h] for our actual OOC search, so that a budget or depth statement
("a 2 pp gap needs about 20k simulations at horizon 3") rests on measured quantities.

This page fixes what each quantity means operationally in this repository, which of them can be estimated at what
cost, and which cannot. It contains no result.

## Objects

**Root.** A root $s$ is a real OOC decision of a recorded game, identified by (run seed, `decisionIndex`) and
reached by a bit-exact replay. It contains the public state and the hidden RNG state. Its action set $A(s)$ is the
live search model's root candidate list (`STS_OOC_ROOT_PROBE` `candidates`): at a card reward the offered cards and
Skip, plus Singing Bowl if held; $K = |A(s)|$, usually 4. $a_{\mathrm{ref}}(s)$ is the production chain's choice
(probe `production.keys`).

**Continuation policy π.** The frozen production stack of the replayed campaign (for the primary cohort: the
`card_rule_ab_20261026` arm-A environment in `run_unit.sh`, run with the frozen RUN_COMMIT), including its own seed
derivation (`oocMctsSearchSeed(seed, index)`, Silver seeds). π decides everything after the root, OOC and combat.

**Future randomness ω.** The hidden future after the root is redrawn by `resampleCounterfactualFuture`
(`sampleNoncombatFuture`), seeded by the salt of `STS_OOC_FORCE_DECISION=INDEX:SALT:KEY`. The per-draw function is the
one the OOC search uses itself, but the process differs: the fork draws once after the root action and then plays
one coherent world, while the search redraws at every child expansion and before every rollout combat, so it never
conditions on hidden information revealed later in its own line. That difference stays inside the search bias B.
In the seed regime the floor-0 observation identifies the seed (§702), so without the redraw "the" future would be a
clairvoyant fixed sequence; the redraw is what makes $Q$ a decision value. One salt shared across the actions of a
root gives common random numbers (CRN) between the actions.

**Outcome.** $Z = 1\{\text{Heart kill}\}$ of the forked game (secondary: Act-4 arrival).

**Search configuration θ and search randomness u.** θ = (leaf model L, leaf horizon h, budget N, root rule, tree
parameters). Leaf model: X2-B with M0 calibration (A20 default, ADR-0057) or the SR head (`SR_crn_r2_s2_ep20`, as in
§712 arm D). Leaf horizon h = `STS_OOC_MCTS_LEAF_COMBATS` ∈ {0, 1, 3, 5}: the number of combats the rollout chain
plays past a tree leaf before the leaf value anchor (production 3 = "rollout3"). Root rule: uniform root (simulations
split evenly over $A(s)$, best mean Q, as `STS_OOC_MCTS_ROOT_COMPARE`'s reference and §712's card rule) unless stated;
below the root the live tree (student_sel PUCT prior, cpuct 1.5, widening K = 4, α = 0.75, merged outcomes).
u = the search seed, which drives every random draw inside the search (CTM draws, chance successors, rollouts).
The search sees only what production search sees at $s$.

"Depth" in Codex's sense has two parts here: the leaf horizon h, which we control, and the tree depth reached,
which follows from N and widening (~1 floor at production budgets: next combat is a chance node with ~2,000
successors, `ooc-mcts-card-depth` diagnostics, §706 for combat). We vary h and record tree depth.

## Definitions

All quantities are per root $s$ and, where stated, per configuration θ.

### True action value and gap Δ

$$Q(s,a) = \Pr_\omega\big[Z = 1 \mid s,\ a,\ \text{then } \pi\big] = \mathbb{E}_\omega\, Z(s,a,\omega).$$

$a^*(s) = \arg\max_a Q(s,a)$ (ties: any). For a competitor $i$: $\Delta_i(s) = Q(s,a^*) - Q(s,i) \ge 0$;
$\Delta_{\min}(s) = \min_{i \ne a^*} \Delta_i(s)$.

Everything we can estimate without first identifying $a^*$ is referenced to $a_{\mathrm{ref}}$:
$\delta_i(s) = Q(s,i) - Q(s,a_{\mathrm{ref}})$, so $\Delta_i = \max_j \delta_j - \delta_i$.

$Q$ is defined relative to π: a card that would be good under a better continuation policy can have a low $Q$ here.
That is intended (it is the value the current agent can realise), and it changes if π changes.

### Search estimate and relative bias B_rel

The search returns $\hat Q_a(s;\theta,u)$ for each root action and plays $\hat a(s;\theta,u) = \arg\max_a \hat Q_a$.
Its mean at finite budget is $\mu_a(s;\theta) = \mathbb{E}_u \hat Q_a(s;\theta,u)$, and $\mu_a(s; L,h,\infty)$ its limit
(estimated at the largest budget measured; see Variance for the convergence check).

$$B_a(s;\theta) = \mu_a(s;\theta) - Q(s,a), \qquad
B^{\mathrm{rel}}_i(s;\theta) = B_i - B_{a^*} = \Delta_i(s) - \tilde\Delta_i(s;\theta),$$

where $\tilde\Delta_i = \mu_{a^*} - \mu_i$ is the gap the search sees. Only differences matter: a level shift of the
leaf (e.g. a calibration offset) cancels. The reference form, identifiable without $a^*$, is

$$b_i(s;\theta) = (\mu_i - \mu_{a_{\mathrm{ref}}}) - \delta_i(s), \qquad B^{\mathrm{rel}}_i = b_i - b_{a^*}.$$

Notes:
- $B$ at finite N contains a small finite-budget part: below a uniform root the subtree still adapts (PUCT, widening),
  so $\mu_a(N)$ can drift with N. The measurement reports $\mu(N)$ per checkpoint, not only the limit.
- Sources inside $B$ (rollout policy ≠ π, CTM instead of real combat, truncation at horizon h with leaf error,
  pruning, tree rules) are not separately identified by this definition. Varying h separates the truncation part:
  $\mu(L,h)$ for h = 0, 1, 3, 5 is a ladder toward longer simulated horizons, not toward π itself (the rollout chain
  and CTM stay).
- $B$ is a property of (s, θ) and the frozen π; it says nothing about bias against a better policy.

### Search variance σ

Two levels, both conditional on (s, θ), randomness u only:

1. **Decision-level:** $\sigma_{D,i}(s;\theta) = \mathrm{SD}_u\big(\hat Q_{a_{\mathrm{ref}}} - \hat Q_i\big)$, the run-to-run
   SD of the difference the decision is based on. This is what decides flips.
2. **Per-simulation:** $\sigma_a(s;h,L)$, the SD of a single backed-up return of root child $a$ (one simulation's
   leaf value or terminal). If the $n = N/K$ returns per child were i.i.d. and children independent,
   $\sigma_{D,i}^2 \approx (\sigma_{a_{\mathrm{ref}}}^2 + \sigma_i^2)/n$. Live OOC search has no sibling coupling (one
   sequential stream; §699, §703), so this unpaired form is the right baseline; the ratio
   $\rho_{\mathrm{eff}} = \sigma_{D}^2 \cdot n / (\sigma_{a}^2 + \sigma_i^2)$ measures how far the tree's adaptivity
   departs from it.

The search's own self-consistency follows from σ alone: $P_{\mathrm{self}}(s;\theta) = \Pr_u[\hat a(s;\theta,u) \ne
\bar a_\infty(s;L,h)]$ with $\bar a_\infty = \arg\max_a \mu_a(s;L,h,\infty)$, the probability that budget N picks a
different action than the same search would pick with unlimited budget. It is the variance part of "wrong card".

σ here is search noise. The outcome noise of the ground-truth estimator (Bernoulli $Z$ over ω, per-salt paired SD
≈ 0.39 mean, 0.45 RMS at #882's roots) is a different quantity and enters only the error of $\hat Q$.

### Coverage q

Codex's "probability of reaching the decisive future lines" needs a concrete event. Because $Q(s,a)$ is a martingale
value, the gap does not "appear" at a floor in expectation; what appears at a floor is the realised outcome
difference. We therefore define coverage from the real paired futures:

- For a root, competitor $i$ and salt ω with discordant outcomes ($Z(a_{\mathrm{ref}},\omega) \ne Z(i,\omega)$), let
  $T_i(\omega)$ be the floor where the losing arm's run ended: its death floor, or the Heart floor if it reached the
  Heart and did not kill it.
- Let $H_a(s;\theta)$ be the simulated horizon of one simulation of root child $a$: the floor at which its value was
  fixed (rollout end floor, or terminal floor), from the search trace; $G_a(t) = \Pr[H_a \ge t]$ over the child's
  simulations.

$$q_i(s;\theta) = \mathbb{E}\big[\,G_i(T_i(\omega)) \,\big|\, \text{discordant}\big]$$

is the fraction of the realised outcome differences between $i$ and $a_{\mathrm{ref}}$ that happen inside the horizon
the search actually simulates (with real combats replaced by CTM). $1 - q$ is the share the leaf value must carry.
It is a proxy: a death at floor $T$ can be caused by a deck consequence of the root that only shows there, which is
exactly the case the leaf has to price. The tree-shape version (fraction of child visits reaching tree depth $\ge d$)
is recorded as a covariate.

### Derived quantities

- Simple regret: $r(s;\theta,u) = Q(s,a^*) - Q(s,\hat a)$. PAC target: $\Pr[r \le \varepsilon] \ge 1-\delta$.
- Regret decomposition: $\mathbb{E}_u r = \underbrace{Q(s,a^*) - Q(s,\bar a_\infty)}_{\text{bias regret}} +
  \underbrace{\mathbb{E}_u[Q(s,\bar a_\infty) - Q(s,\hat a)]}_{\text{variance regret}}$.
- Advantage over production (identifiable): $\mathcal{A}(s;\theta) = \mathbb{E}_u\, \delta_{\hat a(s;\theta,u)}(s)$.
  Then $\mathbb{E}_u r = c(s) - \mathcal{A}(s;\theta)$ with $c(s) = \max_j \delta_j(s) \ge 0$ independent of θ.

## Identification and the cost of ground truth

**Per-root Δ is too expensive.** At #882's roots the per-salt paired SD of a Heart difference was 0.39 on
average, 0.45 RMS (per-root SE median 8.8 pp, range 0–21 pp at 16 salts; recomputed from §710's analysis.json). An
SE of 1 pp on one δ needs ≈ 2,000 paired futures; with all K = 4 actions per salt at ≈ 13 core-min per forked game
that is ≈ 1,750 core-h per root (≈ 440 core-h for 2 pp). Gaps at
card rewards are mostly below 2 pp (§707: 63 % of leading sibling gaps in leaf units), so per-root ground truth, and
with it per-root $a^*$, is out of reach. Estimating the spread of true gaps by deconvolution has the same problem
(≈ thousands of roots for a 3 pp SD).

**Population (pooled) estimands are affordable.** Over a root population $S$ (card-reward roots of a cohort):

| quantity | pooled estimand | identified? |
|---|---|---|
| advantage of rule θ | $\bar{\mathcal{A}}(\theta) = \mathbb{E}_s \mathcal{A}(s;\theta)$ | yes, unbiased from one paired salt per root; but the expected size is ≈ −0.5 pp per root (§712: −19 pp per game over ≈ 38 card searches), far below an affordable SE (≈ 2 pp at ≈ 1,600 games) |
| E[simple regret \| N, h] | $\bar c - \bar{\mathcal{A}}(\theta)$ | up to the constant $\bar c = \mathbb{E}_s c(s)$; curve shape fully |
| variance regret | $\bar{\mathcal{A}}(L,h,\infty) - \bar{\mathcal{A}}(L,h,N)$ | yes, and precise (only roots where the choices differ contribute) |
| bias regret | $\bar c - \bar{\mathcal{A}}(L,h,\infty)$ | bracketed: $\bar c \ge$ cross-fitted hindsight gain and $\ge \max_\theta \bar{\mathcal{A}}(\theta)$ |
| relative bias | calibration of the search's seen difference: $\mathbb{E}[\delta_i \mid \mu_i - \mu_{a_{\mathrm{ref}}} = x] = \alpha + \beta x$ | yes; unbiased search: α = 0, β = 1; $b(x) = (1-\beta)x - \alpha$ |
| σ, $P_{\mathrm{self}}$ | per root, then averaged | yes, cheap (search runs only) |
| q | pooled $\mathbb{E}[G(T) \mid \text{discordant}]$ | yes (needs discordant pairs: ≈ 15–25 % of paired salts) |
| P(wrong card \| N, h) | $\mathbb{E}_s \Pr_u[\hat a \ne a^*]$ | not without per-root $a^*$; reported as $P_{\mathrm{self}}$ (variance part), $\Pr[\hat a \ne a_{\mathrm{ref}}]$, and a model-based (empirical-Bayes) estimate, labelled as such |

The key design consequence: if every action of a root is played under the same salt, the table
$Z(s,a,\omega_m)$ serves every search configuration at once (look up the action θ picks). Searches are cheap
(≈ 2 core-min at 16,384 simulations), forked games are not.

## Prior evidence that bounds the answer

- §712: at whole-game level, card picks from uniform 8,192-sim search lose −19.1 pp (X2-B, h = 3) and −9.4 pp (SR
  leaf) against student_sel. So $\bar{\mathcal{A}}$ of these θ is negative; the question is how much is variance and
  how much is bias.
- Search noise at card rewards is small at 8,192: Q noise ≈ 0.5 pp per child between widening variants
  (single-seed diagnostics, 2026-10-25); §707: single-sample sibling SD 14–26 pp unpaired, so
  $\sigma_D \approx 0.2/\sqrt{2048} \approx 0.4$ pp at 2,048 simulations per child. **Expectation:** variance regret is
  small at 8,192 and $\bar{\mathcal{A}}<0$ is mostly bias; the measurement tests this.
- §710 (#882): leaf gap vs real Heart difference r = −0.10 over 26 roots (3 of them rewards). §707: leaf-vs-act-end
  bias at card rewards −0.26 pp (same policy and CTM, so not bias against π).
- §703: swkeyed rollouts give 0.21× sibling-difference variance per CPU at card rewards; relevant only if the
  variance part turns out to matter. §700: more SR data does not improve the head.

## Measured (§717, card rewards, 128 roots)

- σ / P_self: at 8,192 simulations, h = 3, uniform root, P_self = 0.25 (X2-B) and 0.21 (SR). This is "variance-limited"
  by the pre-registered rule, but the search's own regret is about 0.1 pp, and P_self on roots with a > 1 pp lead is
  about 0.06. Disagreements are mostly near-ties. ρ_eff ≈ 1.
- The leaf and the horizon decide more than the seed: X2-B h3 and SR h3 agree on 59% of roots, and X2-B h3 agrees with
  student_sel on 52%.
- Δ, B_rel, β and q are not measured. The phase-2 gate projected SE(β_SR) = 0.39 > 0.35, so no forks were run.
  [RESULT](../../../experiments/evidence/ooc_root_quality_20261028/RESULT.md).

## Open questions

- Whether the bias part shrinks with h (horizon ladder) or is carried by the leaf's card pricing regardless of h.
- Whether the SR leaf's larger card spread is calibrated (β near 1) or only larger.
- Generalisation beyond card rewards (map, rest, shop roots) uses the same definitions; costs differ.

## Related

[variance-reduction.md](variance-reduction.md) (#883), §707 (#881), §710 (#882), §712 (#874), §706 (#888),
[operations/environment-variables.md](../../operations/environment-variables.md) (`STS_OOC_ROOT_PROBE`,
`STS_OOC_FORCE_DECISION`, `STS_OOC_MCTS_CARD_RULE`).
