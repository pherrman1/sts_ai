# Root quality at A20 card rewards: Δ, B_rel, σ, q (pre-registration)

Status: **phase 1 frozen for launch (see `campaign.manifest`, `FREEZE.md`); phase 2 frozen by rule, launched only
after the gate.** Written 2026-10-28 in the project thread "Measure root quality at card rewards" (Philipp,
2026-10-28 20:17Z). Definitions: [root-quality.md](../../../knowledge-base/research/ooc/root-quality.md).
Authorization: Philipp 2026-10-28 20:29Z "Let's go with 32 workers", re-confirmed on the corrected costs 20:32Z
(decision card: "Ja, Phase 1 + gated Phase 2"). The coordinator starts workers.

## Question

For the uniform-root OOC search on real A20 card-reward roots: how does the simple regret of its card choice
depend on budget N and leaf horizon h, and how much of the regret is search variance (fixable by N or variance
reduction) versus relative bias of the search's values (not fixable by N)? Produce the curves
$\bar{\mathcal A}(N \mid L,h)$ (= E[simple regret] up to a constant), $P_{\mathrm{self}}(N \mid L,h)$, the bias
calibration (α, β) per leaf, and coverage q(h).

## Baseline and existing evidence

- §712: whole-game Heart kills with card picks by uniform 8,192-sim search: X2-B M0 leaf −19.1 pp, SR leaf −9.4 pp,
  SR head argmax −17.6 pp versus student_sel (28.1 %). Root-level decomposition not measured.
- §707/§703/single-seed diagnostics: search Q noise at 8,192 ≈ 0.4–0.6 pp per child; most sibling gaps < 2 pp.
- §710: per-root real-play paired SD ≈ 0.39 mean / 0.45 RMS per salt (per-root SE median 8.8 pp at 16 salts); leaf gap does not predict real difference (r = −0.10, 26 roots).

## Hypotheses (competing)

- **H_var:** at production-like budgets the card choice is noise-limited: regret falls with N.
- **H_bias:** the search's limit choice is worse than production: $\bar{\mathcal A}(L,h,N_{\max}) < 0$ and flat in N.
- **H_horizon:** a longer simulated horizon (larger h, higher q) reduces the bias.
- **H_leaf:** the SR leaf's seen differences are informative (β > 0) where X2-B's are not.

Expectation from prior evidence: H_bias, not H_var. The run can contradict it.

**What this design can and cannot resolve (power).** §712's whole-game effects (−19.1 / −9.4 pp) come from rules that
depart from student_sel at 38–49 % of ≈ 38 card searches per game: ≈ −0.5 pp per root, ≈ −1 to −1.5 pp per differing
root. A per-root advantage $\bar{\mathcal A}$ at the affordable scale has SE ≈ 1.9 pp, so tests of H_bias and
H_horizon through $\bar{\mathcal A}$ have ≈ 5–10 % power; resolving −0.5 pp per root would need ≈ 10⁵ forked games.
Those questions are better answered by whole-game A/Bs, where the effect compounds over all card roots (§712 did
exactly that). This design therefore tests only what it can power: **search variance** (phase 1, precise) and
**calibration of the search's seen differences** against real outcomes (phase 2, β), where the SR leaf's seen
differences are large enough. $\bar{\mathcal A}$ curves and q are reported descriptively, without decision rules.

## Cohort and roots

- **Seeds:** replays of the used §712 seeds 111387000–111387255 with the arm-A environment of
  [card_rule_ab_20261026/run_unit.sh](../card_rule_ab_20261026/run_unit.sh) (today's A20 default as of the §712 run).
  No new seeds. **Replay finding (smoke):** main at the run commit plays these seeds deterministically (probe-on ==
  probe-off, 141/141 rows) but not bit-exactly as the §712 record: on 111387000 the first difference is a late map
  MCTS decision (decision 58, floor 13; the search's Q drifts after ~2,000 simulations). The games are therefore
  replays of used seeds under today's code; roots are selected from the §712 record and validated on main (below).
- **Population S:** card-reward OOC roots (REWARDS screen with a card reward, after the rule chain, decided by
  student_sel, floor ≥ 1) of the arm-A games, each game weighted equally.
- **Phase-1 pool:** the first 144 seeds of the block whose §712 A-arm game has a card-reward root (128 + 16 spares),
  one root per seed, chosen uniformly among that game's card-reward roots by `splitmix64(seed ^ 0x524f4f5451)`
  ([select_roots.py](select_roots.py) → [roots.tsv](roots.tsv), [units.txt](units.txt)). A probed root is **valid**
  when main's state at that decision index is a card reward (candidates = Skip + cards); the first 128 valid roots in
  seed order are the sample, the rest are reported and unused.
- **Phase-2 sample:** 96 of the 128, selected on phase-1 output only (rule under Phase 2); inclusion
  probabilities are recorded and population estimates are Horvitz–Thompson weighted.

## Phase 0 — implementation (one PR, research flag default off, independent review)

Implemented as `STS_OOC_ROOT_PROBE_GRID` (+ `_GRID_SEEDS`, `_GRID_SIMS`, `_GRID_SR`, `STS_OOC_ROOT_PROBE_EXIT`), see
`operations/environment-variables.md`:

- per listed root, uniform-root searches (as the probe's `uniform`) for each (L, h) of the grid and R seeds, with
  root checkpoints at 256, 512, …, $N_{\max}$ (uniform allocation is non-adaptive at the root, so checkpoints of
  one run are the smaller budgets of that run);
- per root child and checkpoint: visits, mean Q, **sum of squared backed-up returns** (for σ_a), tree depth reached,
  and the histogram of the floor at which each simulation's value was fixed (for $G_a$);
- the leaf model per search (X2-B M0 or the SR head via the existing heart1 value path) and h via
  `STS_OOC_MCTS_LEAF_COMBATS` semantics;
- the boss edge of §712's card rule (the map step into the act boss is a tree edge), no stops, no root noise;
- forked children only; play unchanged (checked: probe-on game == probe-off game on main, 141/141 rows);
- `STS_OOC_ROOT_PROBE_EXIT=1` ends the process after the probe row, so a phase-1 unit plays only up to its root.

Ground truth uses `STS_OOC_FORCE_DECISION=INDEX:SALT:KEY` (on main since #904) unchanged: one game per (root, salt,
key). Check: the forced $a_{\mathrm{ref}}$ game equals the `-` game for the same salt on the smoke seed.

## Phase 1 — search grid (no forked games)

- Leaves L ∈ {X2-B M0 (A20 default), SR `SR_crn_r2_s2_ep20` (`28523fb5…`, as §712 D)}, horizons h ∈ {0, 1, 3, 5}:
  8 configurations; R = 4 search seeds each; $N_{\max}$ = 16,384 (4,096 per child at K = 4); plus the probe's
  production PUCT root (live budget, real search seed) for reference.
- Outputs per root: $\hat Q$ curves, $\sigma_{D,i}(N)$, $\sigma_a$, $\rho_{\mathrm{eff}}$, $P_{\mathrm{self}}(N)$,
  $\Pr[\hat a \ne a_{\mathrm{ref}}](N)$, $G_a$, tree depth.
- $P_{\mathrm{self}}$ is **cross-fitted**: checkpoints of one run are nested, so a seed's 8,192 pick is correlated with
  its own 16,384 pick. $\bar a_\infty$ is the argmax of the mean $\hat Q$ of seeds {1, 2} at $N_{\max}$, and the
  checkpoints of seeds {3, 4} are scored against it; then the roles swap, and the two halves are averaged. A root is
  "unresolved" in a half when its two reference seeds have different argmaxes at $N_{\max}$. Unresolved roots stay in
  the primary mean, which biases $P_{\mathrm{self}}$ upward (toward "variance-limited", the conservative direction
  for the stop decision). $P_{\mathrm{self}}$ over resolved roots only and the share of unresolved roots are
  reported next to it.
- Cost (measured, smoke 111387001/9): one seed of all 8 configurations = 1,006 core-s (h = 0: 11–19 s, h = 5:
  204–244 s), so ≈ 67 core-min per root plus the replay to the root and the PUCT reference: 144 units ≈ **170 core-h**,
  ≈ 2 h on 32 workers × 4 lanes. Answers σ, $P_{\mathrm{self}}$, the search side of q, and the seen gaps; not Δ or B.

## Phase 2 — ground-truth forks

- **Gate (frozen):** phase 2 runs only if the phase-1 spread of the SR leaf's seen differences
  $x = \bar\mu_i - \bar\mu_{a_{\mathrm{ref}}}$ (h = 3, $N_{\max}$) over the selected roots projects SE(β_SR) ≤ 0.35
  with per-salt SD 0.45 and root clustering. Otherwise stop after phase 1 (the result is then "β not measurable at
  this scale") and report.
- **Root selection for phase 2 (replaces the D/A strata):** 96 of the 128 roots: the 64 with the largest SR seen
  spread $\max_i |x_i|$ plus 32 at random from the rest. Selecting on x does not bias the regression of real
  differences on x (selection on the regressor); $\bar{\mathcal A}$ and q use HT weights.
- 96 roots × M = 4 salts (1–4) × all K actions (≈ 4.1 mean) ≈ 1,580 forked games, Heart kill and Act-4 arrival,
  death floor. **≈ 340 core-h** at ≈ 13 core-min per game (#882: ≈ 12; card roots are earlier, so slightly longer).
- Every θ of phase 1 is evaluated by lookup in the same $Z(s,a,\omega_m)$ table.

- Gate, selection and units: [make_fork_units.py](make_fork_units.py) (DEFF = 3 for root clustering, M = 4). Phase 2
  is a second campaign (same run commit and binary) launched only if the gate passes; its units file is generated by
  that script from the phase-1 tars and committed, with the phase-2 analysis script, before launch.

**Total ≈ 510 core-h (≈ 4–5 h on 32 workers × 4 lanes)**. Phase 1 alone (≈ 170 core-h) measures σ,
$P_{\mathrm{self}}$, the seen gaps and the search side of q. Phase-1 analysis: [analyze_phase1.py](analyze_phase1.py).

## Estimators and their error

Per (root s, salt m) and rule θ: $Y_\theta(s,m) = \sum_a p_\theta(a \mid s)\,[Z(s,a,\omega_m) - Z(s,a_{\mathrm{ref}},\omega_m)]$,
$p_\theta$ = share of the R search seeds choosing a. All CIs: two-stage bootstrap (roots with HT weights, then salts),
10,000 resamples, seed-clustered.

- $\bar{\mathcal A}(\theta)$: weighted mean of $Y_\theta$. Projected SE ≈ 1.9 pp per θ (per-unit variance ≈ 0.45² ×
  share of differing choices, HT inflation included); expected size ≈ −0.5 pp, so descriptive only; contrasts between N at fixed (L, h) are much tighter (only differing roots count).
- **E[simple regret | N, h] curve** = $\bar c - \bar{\mathcal A}$; reported as $-\bar{\mathcal A}$ with the bracket for
  $\bar c$: lower = max(cross-fitted hindsight gain [choose on salts {1,2}, evaluate on {3,4} and swap],
  $\max_\theta \bar{\mathcal A}(\theta)$, 0); upper = in-sample hindsight gain (biased upward in expectation).
- Variance regret: $\bar{\mathcal A}(L,h,N_{\max}) - \bar{\mathcal A}(L,h,N)$.
- Calibration per (L, h) at $N_{\max}$: weighted least squares of $Z(s,i,\omega) - Z(s,a_{\mathrm{ref}},\omega)$ on
  $x = \bar\mu_i - \bar\mu_{a_{\mathrm{ref}}}$ over all (root, i ≠ $a_{\mathrm{ref}}$, salt), root-clustered SE;
  attenuation from search noise in x corrected with the measured $\sigma_D$ (reliability ratio, computed on the selected phase-2 roots). Projected SE(β) (≈ 400 effective root-clustered pairs, per-salt SD 0.45): ≈ 1.0
  for X2-B (seen spread ≈ 2 pp, so uninformative; reported only) and ≈ 0.3 for SR (spread ≈ 5–10 pp, before the
  spread-based root selection, which lowers it). Reported with
  Spearman ρ between x and the root's $\hat\delta_i$.
- σ: per-root sample SD over R = 4 (χ² CI per root, ≈ ±40 %), pooled as mean variance; $P_{\mathrm{self}}$ cross-fitted as above.
- q(h): weighted mean of $G_i(T_i)$ over discordant (root, i, salt) triples; root bootstrap. Expected ≈ 250–400
  discordant triples.
- P(wrong card | N, h): reported three ways, labelled: $P_{\mathrm{self}}$ (variance part, exact), $\Pr[\hat a \ne
  a_{\mathrm{ref}}]$ (observable), and a model-based empirical-Bayes estimate (normal hierarchical model on
  $\delta_i(s)$ with the measured salt variance; posterior $\Pr[\hat a \ne a^*]$). Only the first two are evidence.

## Decision rules (diagnostic; no default, model or training change follows from this run)

Per leaf L at h = 3 (primary) and for each h (secondary):
- **Variance-limited at 8,192 (phase 1):** mean $P_{\mathrm{self}}(8192) > 0.20$ with the root-bootstrap lower bound
  > 0.10. **Not variance-limited:** upper bound < 0.10. Otherwise inconclusive. Next step only if variance-limited:
  swkeyed rollouts in search (§703).
- **SR leaf informative (phase 2):** β_SR lower CI bound > 0. **Uninformative:** upper bound < 0.5. **Calibrated:**
  β CI contains 1 and α CI contains 0. Otherwise inconclusive.
- **Descriptive only (no rule, underpowered):** $\bar{\mathcal A}(N \mid L,h)$ curves, the $\bar c$ bracket, the
  horizon contrast, β for X2-B, q(h), the model-based P(wrong card).

## Known limitations

- Q is relative to the frozen π (arm-A stack); bias against a better policy is not measured.
- 96 roots from 96 games: per-root Δ stays unresolved by design; conclusions are about the population.
- One salt-redraw kernel (`sampleNoncombatFuture`) defines the future distribution.
- q is a horizon proxy (floor of realised discordance), not a causal attribution.
- Uniform root only; PUCT/Gumbel roots, widening variants and other screen types are not covered.
