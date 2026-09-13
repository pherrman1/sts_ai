# Frozen offline composed transition qualification

Knowledge impact: the offline ancestral sampler, strict pre-combat support,
common original-TEST qualification and sampled-upstream exposure. No runtime
integration, model training, support expansion or gameplay experiment.

Baseline: `7316c715bac7fe4559ead59cde1eb374d3437b5b`, clean current main in the
existing Codex app-managed worktree. Recipe:
[composed_transition_recipe_2026-09-14.json](composed_transition_recipe_2026-09-14.json).

The named uncertainty is whether qualified components remain useful when all
upstream outcomes are sampled. Fixed operational artifacts use seed 20260912
by prior convention. Every model and frozen corpus/split/representation hash
is checked before loading or scoring. Independent implementation review and
focused checks precede execution on a frozen reviewed SHA.

Original source-grouped TEST is a **reused engineering TEST**. Historical
survival/maxHP training saw original TRAIN+VALIDATION, including the later
nested HOLDOUT; original TEST is the common partition. No tuning, model
selection, temperature adjustment, refitting or new data collection occurs.

`tools/combat_transition_composed.py::ComposedSampler.sample_transition`
accepts only pre-state, visible predictor input and an independent sampling
RNG. Full support is outcome-independent and checked before survival. It
requires global supported-v1, certified potion consumption closure, valid
native relic counters/recognized mutable set, qualified trajectory groups,
no nondeterministic active Lizard Tail, the frozen HP envelope and legal
class support, valid inherited RNG and all six successfully loaded artifacts.
Fallback is `FULL_SURROGATE_FALLBACK`. Death is terminal before downstream
encoders/heads. Victory samples maxHP, signed HP, potion consumption mask and
shared trajectory residues in that order. HP is never clipped. The HP state
encoding is reused by the relic decoder. Historical encoders retain their own
checkpoint normalization and remain separate. Historical survival/maxHP/potion
FP32 attention uses enabled MHA fastpath; qualified stochastic HP uses disabled
MHA fastpath and AMP FP16 on CUDA. Each component restores the global backend
flag after encoding. These are historical arithmetic conventions, not tuning.

Persistent assembly copies exact supported fields and derives potion count.
`oocContinuationRng` holds copied potionRng and exact encounter-initialization
miscRng replay, including bounded rejection. This is the normal OOC
continuation state, **not** reproduction of all six historical RAW battle RNG
bytes. Four battle-local streams are recreated at battle initialization.

The evaluation driver audits all corpus rows, source/fight order against the
frozen representation, original split membership, native potion/relic/copy
and inherited-RNG contracts. Visible TEST encoding and observed targets are
reconciled with the frozen arrays. Saved TEST rows and support receipts are
hashed. Support rates are reported for the corpus and original TEST, by act
and room. Labels are held only by the driver, never passed to the sampler.

A reproduces observed-conditioning survival, maxHP, signed-HP, joint potion
mask and relic constraints. Historical survival metrics and maxHP probability
vectors are reconciled with the frozen original TEST outputs under the
existing 1e-5 numerical reproduction convention. Downstream scores use full
support victories; survival reproduction also retains the original global
support partition for direct historical comparison.

B computes HP exposure with the **exact weighted marginal over all 11 frozen
maxHP classes**: `P(true signed HP | S) = sum_d P(d | S) P(true signed HP | S,d)`.
The HP head reuses cached state encoding for each class; illegal observed HP
under a class contributes zero through the native support mask. Probabilities
are summed before taking log. HP exposure is exact marginal NLL minus
teacher-forced true-maxHP NLL. The original 32-draw HP estimator remains a
diagnostic only and never enters classification. Potion and relic exposure
retain their original 32 ancestral draws and probability-before-log mixtures.
Relic gaps are normalized by observed learned groups per informative row, as
#173. HP, potion and relic must each have mean gap at most 0.1 nat; a good
component cannot cancel a bad one. The same source-bootstrap 95% CIs (1,000
repetitions, seed 20260917) remain descriptive. No thresholds or models change.

C performs 32 complete draws on every full-support TEST row, including
survival. Its batch counterpart runs survival first and then executes each
downstream encoder/head on sampled survivors only. It does not reuse A/B's
downstream predictions or encodings. Per-stage row-call counters are saved;
focused batch/direct equivalence and death-call tests cover this counterpart.
Every sampled victory uses the sampler's shared native assembly/validation.
All eleven hard validity counters must be zero. Native invalidities retain
row/draw/state/error evidence and reject qualification.

Diagnostics report outcomes, maxHP changes, empirical post-HP CRPS/mean MAE
and inclusive equal-tail 50/80/95% intervals, potion mask/count frequencies,
reconstructed relic vectors/tokens and per-relic errors, and exact modeled
persistent-state sample frequencies. HP/potion/relic diagnostics condition
on sampled victories on observed victory rows; no-sampled-victory rows are
reported explicitly. Persistent exact frequencies additionally include
unconditional frequencies, counting sampled deaths as nonmatches.
Teacher-forced joint NLL reports outcome plus each victory factor's
contribution averaged over all full-support rows.

One-thread CPU batch-1 latency runs the direct sampler, including the support
gate, visible encoding, required forwards/sampling, native reconstruction,
RNG replay, persistent assembly and validation. Death and victory measurements
force only the branch uniform after the actual survival forward; mixed uses
model survival sampling. Each path has 10 warmups and 100 measured draws.
No optimization is performed.

Raw TEST rows, probabilities and 32-draw trajectories remain external at
`/home/philippherrmann/sts_sweep/runs/composed-transition-20260914/`.

```bash
python3 -m tools.combat_transition_composed_evaluate prepare \
  --output-dir /home/philippherrmann/sts_sweep/runs/composed-transition-20260914
# After focused checks and independent review, on a clean reviewed commit:
python3 -m tools.combat_transition_composed_evaluate evaluate \
  --output-dir /home/philippherrmann/sts_sweep/runs/composed-transition-20260914 \
  --reviewed-sha REVIEWED_SHA
```

## Executed results

**`COMPOSED_TRANSITION_QUALIFIED`** after exact HP metric correction on reviewed
SHA `dc1499f36055491fec8ff44143f879c124bf230d`. The original complete-draw,
component, potion/relic and latency evidence was executed on
`abe2c6ea50f55d37e4d594ceb6575247e91c32fa` and is preserved unchanged.
Independent implementation/design review passed for both executions;
15 original direct sampler tests and four focused Python CTest checks passed;
the correction passes 18 direct tests and the composed CTest. The
corrected composed CTest was rerun after the arithmetic repair. Preflight,
submodule check, environment doctor, configure and repository health passed;
health has a descriptive active-Markdown-growth warning and no hard failure.
No gameplay seeds, new combat data, operational model fitting/refitting,
temperature tuning or C++ runtime integration ran.

The initial loading sanity check stopped before ancestral sampling because a
global disabled MHA backend differed from historical FP32 maxHP inference by
0.000983208. An inference-only probe isolated fastpath arithmetic, with no
padding or head-selection effect. Restoring each component's historical
backend reduced the final full-TEST maximum maxHP probability discrepancy to
8.344650269e-07. Survival Brier/log-loss
absolute differences are below 7e-9; AUC is identical. The initial report and
probe are preserved in the parent external directory. The corrected run is
in its `qualification/` subdirectory; no result was overwritten.

Original TEST: 51,441 rows / 2,517 source groups.
Full pre-combat support: 32,164 (62.526001%);
fallback: 19,277 (37.473999%).
Observed full-support victories: 31,150; observed deaths: 1,014.
Whole corpus support: 322,644/510,030 (63.259808%); fallback 187,386.
Full act/room support tables and every hash are in the
[machine-readable evidence](composed_transition_2026-09-14.json).

| Component reproduction | Metric | Value |
| --- | --- | ---: |
| Historical globally supported TEST survival | Brier / log loss / AUC | 0.019039775 / 0.063621790 / 0.978065501 |
| Full-support victory maxHP | NLL / mode accuracy | 0.049227638 / 0.978587480 |
| True-maxHP signed HP | NLL / CRPS / expected-HP MAE | 2.371751655 / 3.432251382 / 5.036823990 |
| True-HP/maxHP potion | Joint mask NLL / mode exact | 0.504139860 / 0.805264848 |
| True-HP/potion relic | Constraint NLL / full-vector mode exact | 0.490337976 / 0.814060995 |

| Composed upstream exposure | Mean gap, nat | Source-bootstrap 95% CI | Frozen 0.1 gate |
| --- | ---: | --- | --- |
| HP, exact 11-class marginal | +0.012241622 | [+0.009743450, +0.014807776] | PASS |
| Potion | +0.000810765 | [+0.000591005, +0.001033385] | PASS |
| Relic, row/group normalized | -0.001521621 | [-0.004191767, +0.001475988] | PASS |

HP/potion exposure includes all 31,150 victories / 2,474 sources. Relic
normalization uses 7,414 informative rows / 909 sources. Exact marginal HP NLL
is 2.383993276 versus teacher-forced 2.371751655; every row has positive exact
mass. The HP-only correction verifies all frozen artifact/data and source
receipts, preserves original TEST membership, reconstructs the same original
512-row TEST encoding batches with frozen HP/maxHP encoders only, and evaluates
the HP head for all 11 classes. Teacher NLL maximum reproduction difference is
**0.0**. No survival/potion/relic scoring, training, sampling, complete draws,
latency measurement or gameplay seeds ran in the correction. Raw corrected
probabilities, encodings and bootstrap inputs are saved in
`qualification/exact-hp/hp_exact_cache.npz`.

**32-draw diagnostic only:** “8/31,150 rows received zero empirical mass with
32 ancestral draws.” These span seven sources (0.025682% of rows). Every
observed HP exceeds every sampled maxHP. For example, row 32892 starts at
80/80 and ends at 84/84; its sampled maxHP deltas are 0 (20 draws) and 3
(12 draws). The native mask explains all eight zeros, but the finite Monte
Carlo miss does not establish model zero probability. All eight exact marginal
probabilities are positive (minimum 0.0000588206). The retained empirical NLL
and bootstrap are +infinity, excluded from classification. No resampling,
finite-row exclusion, clipping, model changes or substitute threshold occurred.

All eleven hard validity counts are **zero** over 1,029,248 draws:
HP below one, HP above sampled maxHP, invalid maxHP class/state, invalid potion
transition, creation/swap/substitution, illegal relic counter, shared-residue
inconsistency, unsupported mutable mutation, deterministic native mismatch,
invalid inherited RNG reconstruction and downstream invocation after death.
Actual stage row calls: survival 1,029,248; each maxHP/HP encoder/HP head/potion
encoder/potion decoder/relic decoder 996,730. Sampled deaths: 32,518. No failed
sampled assembly was discarded.

On full support, outcome Brier/log loss are 0.016413115 / 0.054881630;
observed death rate 3.152593%, mean predicted death
probability 3.171317%, sampled death
rate 3.159394%. On observed victories, sampled maxHP
change frequency is 4.097662% versus observed
3.537721%. Empirical sampled-victory HP CRPS is
3.558434257, sample-mean HP MAE 5.118528503;
one observed victory has no sampled victory and is reported, not assigned HP zero.

| HP interval | Coverage | Mean width, HP |
| --- | ---: | ---: |
| 50% | 66.117692% | 7.917461 |
| 80% | 84.699348% | 14.257215 |
| 95% | 96.141128% | 24.481524 |

Potion no-change frequency is 73.611421% (observed
73.833066%); row-weighted empirical observed-mask
probability 0.733622552, draw-weighted exact
observed-mask frequency 0.736970168.
Consumed-count distributions and per-relic diagnostics are in the JSON.
Relic full-vector exact sample frequency is 0.808758071,
changed-token exact 0.204630150, changed-token MAE
2.376905452. Exact (HP,maxHP,potions,relic counters) and
complete modeled-persistent-state frequencies both equal
0.222741848 conditional on sampled victory,
and 0.219030899 unconditionally on observed victory rows.
These are descriptive, not gates.

Teacher-forced factorized joint mean NLL is
3.362663299 nat per full-support row:
outcome 0.054881630,
maxHP 0.047675691,
HP 2.296979979,
potion 0.488246382,
relic 0.474879616.
Death contributes outcome only.

| Full-path one-thread CPU batch-1 | Mean, ms | Median, ms | p95, ms |
| --- | ---: | ---: | ---: |
| death | 0.982839 | 0.918531 | 1.314706 |
| mixed | 3.324840 | 3.320516 | 3.540134 |
| victory | 3.322606 | 3.316057 | 3.562699 |

Each path uses 10 warmups and 100 draws. The recorded benchmark state is
source 4100018 / corpus row 89; mixed draws use model survival sampling and
contain zero deaths. This measures that state, not a population-wide latency
mixture or a runtime performance qualification. No optimization ran.

The exact HP gap passes the frozen 0.1-nat gate, alongside the unchanged potion,
relic and hard validity gates. The prior finite-draw rejection is superseded
by this metric correction. No maxHP investigation or repair is justified by
the eight Monte Carlo misses. The next separately scoped action is a native
runtime adapter / OOC MCTS integration; this offline qualification does not
establish runtime or gameplay performance.

Independent raw-evidence verification passed without scoring or new draws:
original sampled mean-before-log mixtures, teacher differences, informative groups and source
bootstrap CIs reproduce exactly; all hashes/membership/receipts pass. Native
HP/maxHP/potion/relic/shared-residue validity, exact persistent match arrays,
copy-through/inherited RNG, stage counts and joint likelihood contributions
were crosschecked from saved arrays. Commands (scripts preserved externally):

```bash
PYTHONPATH=. python3 /tmp/independent-composed-evidence-check.py
PYTHONPATH=. python3 /tmp/independent-composed-complete-check.py
```

Both independent commands completed successfully. The receipt and scripts are
preserved under the corrected external qualification directory.

The HP correction additionally reproduces the raw 11-class weighted sums,
native illegal-target zeros, exact NLL/teacher differences and the same source
bootstrap. All eight empirical-zero rows have positive exact mass. Other
metrics and frozen artifacts are unchanged. Independent correction verification
and its script are preserved under `qualification/exact-hp/`.

```bash
python3 -m tools.combat_transition_composed_evaluate correct-hp \
  --source-dir /home/philippherrmann/sts_sweep/runs/composed-transition-20260914/qualification \
  --output-dir /home/philippherrmann/sts_sweep/runs/composed-transition-20260914/qualification/exact-hp \
  --reviewed-sha dc1499f36055491fec8ff44143f879c124bf230d
```
