# Native relic legality and prospective potion decoder experiment

Baseline: merged #166 `cee9a97a152671bc01c93527307f7d24e2241909`.
Knowledge impact: native legality contract in training/inference KB; audit and
preregistered decoder protocol here and ledger §235; current research status
updated. Scientific fitting is gated on independent implementation review.
No model binary, cached embedding, raw prediction, or large array is tracked.

## Native contract

The authoritative boundary is `BattleContext::exitBattle` through the RAW
observer, before victory reward callbacks. `initRelics`, `updateRelicsOnExit`,
`Player::applyStartOfTurnRelics` (turn-start counter updates), the card-use paths,
`onShuffle`, and `Player::wouldDie` supply the counter mechanisms. The native
write-back set is derived by the existing source audit, checked against the
explicit legality implementations at import; unfamiliar writes fail closed.
Three write-back cases heal HP without mutating their persistent relic data.
This is simulator legality, not a claim about original-game counters.

| Relic (native ID) | Pre domain | Legal post domain / pre-dependent rule | Native mechanism | Pre-visible legality |
| --- | --- | --- | --- | --- |
| Happy Flower (26) | 0..2 | 0..2 | Init and turn-start increment/reset at 3; exit copies | Yes |
| Incense Burner (30) | 0..5 | 0..5 | Init and turn-start increment/reset at 6; exit copies | Yes |
| Ink Bottle (31) | 0..9 | 0..9 | Card-use increment/reset at 10; exit copies | Yes |
| Inserter (32) | 0..1 | 0..1 | Init toggle, turn-start increment/reset at 2; exit copies | Yes; zero corpus tokens |
| Lizard Tail (35) | 0..1 | pre=0 → {0}; pre=1 → {0,1}, or {1} with Mark of the Bloom | Init activates only nonzero data; lethal damage clears active bit; exit writes zero if inactive | Yes, conservative reachable domain |
| Nunchaku (44) | 0..9 | 0..9 | Attack increment/reset at 10; exit copies | Yes |
| Omamori (46) | 0..2 | Retain pre outside Writhing Mass; {pre,max(0,pre−1)} there | Direct RAW exit decrement for implanted Parasite; Writhing Mass remains globally excluded | Yes with visible encounter |
| Pen Nib (52) | 0..9 | 0..9 | Internal −1 sentinel maps to persistent 9; attack increments; exit copies | Yes |
| Sundial (68) | 0..2 | 0..2 | Shuffle cycles 2→0, otherwise increment; exit copies | Yes |
| Black Blood (85) | integer saved data | {pre} | Victory healing; no data write | Yes |
| Burning Blood (86) | integer saved data | {pre} | Victory healing; no data write | Yes |
| Meat on the Bone (87) | integer saved data | {pre} | Conditional victory healing; no data write | Yes |
| Neow’s Lament (116) | 0..3 | {max(0,pre−1)} | Acquisition initializes 3; RAW exit decrements positive data once, including death | Yes |

Invalid pre domains, missing encounter for Omamori, and unknown relic IDs raise
`SILVER_REQUIRED`; they do not change global surrogate support. This contract
provides a conservative legal reachable domain, not the exact unseen combat
trajectory or joint reachability across multiple counters. It does not infer
periods from corpus values. Saved out-of-domain values need future Silver
fallback; none occurred in this corpus's supported rows.

## Stage-0 evidence

All 510,030 corpus rows checked; supported rows remain 413,799. Zero observed
supported counter contradictions; zero encountered additional-fallback states.
Unlisted relic counters were also checked for mutations; mutable counters
were reconciled with predictor-visible data, with zero mismatches. Counts and all native
IDs are in [relic-audit.json](potion_decoder_v1/relic-audit.json).

Frozen historical TEST victory logits were corrected without retraining. The
comparison first applies the historical per-relic delta mask, then intersects
with native legal post states and renormalizes. All observed targets survive.
Results are token-weighted across 60,239 present audited relic tokens in
39,919 supported victories, including healing relic counter copy-through.
This is reused TEST engineering evidence, not the decoder decision set.

| Metric | Before | Constrained |
| --- | ---: | ---: |
| Mean illegal mass per relic token | 0.02687075 | 0 |
| Invalid counter modes | 24 | 0 |
| Counter token NLL | 0.45244862 | 0.42272036 |
| Counter token exact accuracy | 0.82519630 | 0.82539551 |
| Changed-counter exact (11,180 tokens) | 0.11842576 | 0.11940966 |
| Changed-counter MAE | 2.14042934 | 2.13685152 |

Invalid modes break down as Sundial 8, Incense Burner 6, Neow's Lament 9,
Pen Nib 1; all other IDs 0. Per-ID illegal mass, NLL, exact, changed accuracy,
and MAE are in [historical metrics](potion_decoder_v1/historical-relic-metrics.json).
Full audited-counter-vector joint NLL improves `0.68275890 → 0.63789803`;
vector exact improves `0.77717378 → 0.77744933`. Mean probability of any illegal
counter in a vector is `0.03959559 → 0` (historical independent-token product).
NLL improves for every target because its probability survives conditioning.
This is no qualification of joint relic dependence, native RNG continuation,
or full sampled transitions.

The separate [potion target audit](potion_decoder_v1/potion-target-audit.json)
re-derived consumption certification from hashed prepared visible inputs,
matched the merged #166 certification exactly, and round-tripped all 322,644
certified supported pre/post inventories (including deaths) through five-bit
masks with zero contradictions. Eligible victory decoder row counts are
199,896 TRAIN / 24,819 VALIDATION / 25,398 HOLDOUT. Counts are eligibility
metadata, not decoder performance inspection.

## Frozen nested experiment

[Manifest](potion_decoder_v1/nested_split.json) SHA256:
`58e35f9f85eefd7617e616ddbfa7ee227c429ed4d312f7dacd470828f9a09094`.
Salt: `sts-potion-decoder-nested-v1-20260913`; SHA256 of `salt:source`, first
64 bits as unsigned big endian, thresholds 0.8 and 0.9. Only original TRAIN
sources participate; every source stays together. No target informed assignment.

| Nested split | Sources | All rows | Supported rows |
| --- | ---: | ---: | ---: |
| TRAIN | 15,971 | 325,998 | 264,404 |
| VALIDATION | 2,001 | 40,782 | 33,249 |
| HOLDOUT | 2,014 | 41,403 | 33,572 |

[Recipe](potion_decoder_v1/recipe.json) SHA256:
`316d44fa837fb68b0ec4b3889bcc4219274e6ade066a3bb9ff825517d763f224`.
The width-64 attention point-control encoder trains exactly 10 FP32 epochs
on supported decoder-TRAIN rows, survival BCE plus winning HP-fraction MSE.
Normalization uses those same TRAIN rows. No encoder validation selection.
Parameters freeze; cached state embeddings are detached; decoder gradients
cannot reach encoder parameters. Survival in eventual composition remains
the original historical point-control artifact, separate from this state encoder.

Both heads train on the identical supported, certified, victorious rows, using
teacher-forced true max-HP delta and HP fraction. Independent slot Bernoullis
and the exact 32-class joint head receive state, delta, HP, potion identity,
and explicit slot information. Empty/unavailable bits are deterministically
zero. Both use AdamW lr 1e−3, decay 1e−4, FP32, seed 20260912, shuffled batch
2,048, max 12 epochs, patience 3, norm clipping 1.0. The earliest strict minimum
of validation joint mask NLL selects each head's epoch independently.
Refit each head from scratch on TRAIN+VALIDATION, leaving the TRAIN-only encoder
unchanged. Write `selection.json` before any HOLDOUT scoring and write
`teacher_forced_decision.json` before ancestral evaluation. Each decoder's
HOLDOUT predictions are scored once for the primary decision.

Primary: row-weighted joint mask NLL difference (joint minus independent),
1,000 paired source-group bootstrap resamples, seed 20260913. Strictly negative
95% interval → `JOINT_MASK_WINS`; strictly positive → `INDEPENDENT_MASK_WINS`;
overlap → `NO_CLEAR_JOINT_GAIN`, prefer independent. Secondary metrics do not
select the architecture. Static decoder parameter counts with the frozen
11-class max-HP delta domain are 6,061 independent and 11,148 joint; these
are architecture counts, not evidence of trained artifacts. No global TEST
replication is needed for this decision.

Ancestral qualification uses the same HOLDOUT rows and 16 draws per row from
the existing frozen Phase-2 max-HP and conditional HP distribution. Convert
sampled HP bins to clamped native integer HP, then normalize by sampled maxHP.
Report mean conditional NLL separately from the Monte Carlo marginal mixture
NLL, sampled no-change/count frequencies, and mode sensitivity. Preregistered
engineering exposure flag: preferred decoder ancestral mixture NLL worsening
by more than 0.1 nat versus teacher forcing → `ANCESTRAL_EXPOSURE_GAP`, otherwise
`ANCESTRAL_OK`. This threshold is an explicit engineering criterion, not a
statistical hypothesis or a change to the primary decision rule. Historical
upstream weights saw original TRAIN+VALIDATION, including nested HOLDOUT;
ancestral qualification is consequently an engineering exposure diagnostic,
not an independent upstream generalization result.

## Execution status and checks

Preparation and Stage-0 inference correction completed. Encoder/head fitting,
selected epochs, encoder artifact hash, HOLDOUT primary/secondary results,
ancestral classification, and measured latency are **not available** before
independent implementation review. HOLDOUT targets have not been scored for
this decoder experiment. The required all-corpus correctness audit necessarily
read historical transition targets; it did not choose decoder architectures.
No scientific decoder conclusion is claimed.

External artifacts/logs:
`/home/philippherrmann/sts_sweep/runs/joint-potion-mask-20260913/`.
Frozen historical predictions:
`/home/philippherrmann/sts_sweep/runs/frozen-survival-potion-20260913/frozen_predictions.npz`.
Prepared arrays: `/tmp/sts-phase2-attention-audit-20260913/`.
Corpus and original split remain at their existing durable paths. No simulator
collection or seeded gameplay command was run. `combatRng[6]` remains unmodeled;
Silver replacement and RNG-continuing native rollouts remain blocked.

Focused unittest command (49 tests, OK):

```bash
python3 -m unittest tools.test_combat_transition_potion_decoder \
  tools.test_combat_transition_frozen_composition \
  tools.test_combat_transition_attention_ablation \
  tools.test_combat_transition_surrogate -v
```

Preparation command:

```bash
python3 tools/combat_transition_potion_decoder.py prepare \
  --prepared-dir /tmp/sts-phase2-attention-audit-20260913 \
  --split-manifest /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/split_manifest.json \
  --output-dir /home/philippherrmann/sts_sweep/runs/joint-potion-mask-20260913
```

Native gate command:

```bash
python3 tools/combat_transition_relic_legality.py \
  --corpus /home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/combat-transition-25k.jsonl \
  --output /home/philippherrmann/sts_sweep/runs/joint-potion-mask-20260913/relic-audit.json
```

After review passes, run `fit` with the same paths, historical `--artifact-dir`,
and equal current `--code-sha` / independently `--reviewed-sha` on a clean
checkout. This records rather than independently authenticates review approval;
the operator must verify review actually passed. It refuses to overwrite an
existing encoder or selection artifact. Recovery from interrupted training
requires an explicit follow-up plan preserving split/recipe provenance.

Additional checks: worktree preflight/check and environment doctor passed;
CMake `linux-gcc-debug-ccache` configure exit 0; four affected CTest checks
passed. Minimal uv environment ran 16 decoder tests, OK with six Torch tests
skipped. Torch environment ran all 16 decoder tests including tiny synthetic
selection/refit/ancestral and composed-latency paths. No full C++ build or
scientific fitting ran; GitHub Linux GCC is authoritative repository CI.
