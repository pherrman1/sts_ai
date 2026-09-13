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

B uses 32 ancestral draws on observed full-support victories. Each mixture
averages observed-event **probabilities before taking log**. Exposure is
mixture NLL minus observed-conditioning NLL. Relic gaps are normalized by
observed learned groups per informative row, as #173. HP, potion and relic
must each have mean gap at most 0.1 nat; a good component cannot cancel a bad
one. Source-bootstrap 95% CIs (1,000 repetitions) are descriptive. Zero
mixture mass is positive-infinite rejection evidence, never a reason to
resample. No post-hoc thresholds are introduced.

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
