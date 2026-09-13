# Fresh nested HOLDOUT potion decoder result

**Primary result: `JOINT_MASK_WINS`.** The paired source-bootstrap 95% CI for
joint minus independent potion-mask NLL is entirely below zero. This is the
preregistered classification, unchanged by secondary or ancestral results.

Executed code and independently reviewed SHA:
`9f15dba5c348f775725232d33e72d2cf8e1b6127`.
Merged #166 baseline: `cee9a97a152671bc01c93527307f7d24e2241909`.
No code change preceded the fit. Subsequent commits record evidence only.
Knowledge impact: actual experiment results in ledger §236 and this evidence;
current research status updated. No runtime default or Silver change.

## Primary decision

| Teacher-forced HOLDOUT metric | Value |
| --- | ---: |
| Victories | 25,398 |
| Eligible source groups | 1,979 |
| Independent joint-mask NLL | 0.5189140430759348 |
| Joint categorical mask NLL | 0.5166171564635460 |
| Δ = joint − independent | −0.0022968866123888503 |
| Paired source-bootstrap 95% CI | [−0.004204553691665904, −0.0006352931871017291] |
| Source resamples | 1,000 |
| Primary classification | `JOINT_MASK_WINS` |

All 25,398 eligible HOLDOUT victories participated. Bootstrap resamples sources
and preserves their paired fights, using row-weighted means, seed 20260913.
The interval's upper bound is below zero. No practical-effect threshold,
secondary-metric override or reused global TEST decoder decision was applied.

## Frozen training and provenance

Nested split SHA256:
`58e35f9f85eefd7617e616ddbfa7ee227c429ed4d312f7dacd470828f9a09094`.
Recipe SHA256:
`6e758e5df43a39a0c6438ae0841e00050809fed770f654cb6da76fc10d714541`.
Corpus SHA256:
`74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
Global support remains 413,799 / 510,030; certified supported rows 322,644,
zero contradictions. No new simulator collection or gameplay seeds.

The attention point-control state encoder trained exactly ten FP32 epochs on
264,404 supported rows from 15,971 nested TRAIN sources. Artifact metadata was
read back and matched the exact nested TRAIN source list; it contains no
VALIDATION or HOLDOUT source. Scalar normalization uses those same TRAIN rows.
Encoder parameters remained unchanged and received no decoder gradients after
freezing. Encoder artifact SHA256:
`2085010f1aeef7a7957cdc45c851b2424d640037fd0fa981eb7ae7274190f6ef`.

Both heads selected **12 epochs** independently using VALIDATION joint-mask
NLL. Each was refit from scratch for 12 epochs on the same 224,715
TRAIN+VALIDATION victories, leaving the encoder unchanged. TRAIN and VALIDATION
head row counts were 199,896 and 24,819. Architecture/settings match the
[preregistration](potion_decoder_v1_2026-09-13.md): identical full-inventory
features, width-64 hidden MLP, AdamW 1e-3/1e-4, batch 2,048, max 12 epochs,
patience 3, seed 20260912, FP32 and teacher-forced delta/HP.

Selection was written before HOLDOUT scoring; the teacher-forced decision was
written before ancestral qualification. Validation histories and epoch choices:
[selection.json](potion_decoder_v1/selection.json). Machine-readable primary,
secondary, calibration and per-act/room/encounter/potion-count/Sacred-Bark
results: [fit-evidence.json](potion_decoder_v1/fit-evidence.json).
Artifact hashes: [fit-artifact-hashes.json](potion_decoder_v1/fit-artifact-hashes.json).

## Secondary HOLDOUT metrics

| Metric | Independent | Joint |
| --- | ---: | ---: |
| Mode exact-mask accuracy | 0.797621860 | 0.797976219 |
| No-change event Brier | 0.097783834 | 0.096863662 |
| Mean zero-mask probability | 0.718813439 | 0.730809669 |
| Consumed-count accuracy from mask mode | 0.807740767 | 0.804236554 |
| Changed-row exact (6,668 rows) | 0.411067786 | 0.382723455 |
| Unchanged-row exact (18,730 rows) | 0.935237587 | 0.945808863 |
| Deterministic copy-through exact | 0.737459642 | 0.737459642 |

Calibration by predicted consumed count and full stratified NLL are in the
machine-readable evidence. Secondary metrics are descriptive; the primary
classification above follows only the frozen NLL/bootstrap rule.

## Separate ancestral qualification

16 draws per HOLDOUT row, 406,368 draws per arm, sampling frozen historical
Phase-2 max-HP delta and conditional HP, then the potion mask. Survival remains
the historical point-control component; qualification rows are observed victories.
The historical upstream model saw original TRAIN+VALIDATION, including nested
HOLDOUT sources. This is the preregistered engineering exposure diagnostic,
separate from the teacher-forced primary decoder decision.

| Metric | Independent | Joint |
| --- | ---: | ---: |
| Teacher-forced NLL | 0.518914043 | 0.516617156 |
| Ancestral mean conditional NLL | 0.520028303 | 0.517885160 |
| Ancestral Monte Carlo mixture NLL | 0.519823952 | 0.517616568 |
| No-change sample frequency | 0.718705705 | 0.730515198 |
| Mode changes under sampled upstream | 0.007808194 | 0.007690074 |
| Structurally invalid samples | 0.000000000 | 0.000000000 |
| Potion identity creation/swap | 0.000000000 | 0.000000000 |

Joint ancestral mixture NLL minus teacher-forced NLL is
`0.0009994119185607886`, below the frozen 0.1-nat exposure threshold.
Separate qualification: **`ANCESTRAL_OK`**. Consumed-count frequencies are in
machine-readable evidence; they do not alter `JOINT_MASK_WINS`.

## CPU latency and validity

AMD Ryzen 5 7500F; FP32 PyTorch 2.5.1+cu121; one CPU thread, batch 1,
10 warm-ups and 100 measured calls per arm on one held-out fixture. Training
used the local NVIDIA RTX 3060 Ti. Latencies are a fixture microbenchmark,
not a population estimate. Full composition includes visible encoding,
historical point survival, the new frozen state encoder, frozen Phase-2
upstream, potion decoder, constrained relics and persistent-state draw,
excluding RNG continuation. All measured composed draws were victories.

| Cost | Independent | Joint |
| --- | ---: | ---: |
| Decoder parameters | 9393 | 11148 |
| Decoder mean ms | 0.06811055995058268 | 0.05721267079934478 |
| Decoder p95 ms | 0.08067167655099183 | 0.07654327782802282 |
| Composed mean ms | 3.15567079000175 | 3.106291822041385 |
| Composed p95 ms | 3.3083975373301655 | 3.171166146057658 |

Native relic legality and certified potion masks have zero observed corpus
contradictions; ancestral potion draws have zero structurally invalid samples
and zero identity creation/swaps. This does not establish joint relic trajectory
reachability or native RNG-continuing rollout qualification. `combatRng[6]`
remains unmodeled; deployment remains `NOT_QUALIFIED` and Silver is unchanged.

## Raw execution

```bash
python3 -u tools/combat_transition_potion_decoder.py fit \
  --prepared-dir /tmp/sts-phase2-attention-audit-20260913 \
  --split-manifest /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/split_manifest.json \
  --output-dir /home/philippherrmann/sts_sweep/runs/joint-potion-mask-20260913 \
  --artifact-dir /home/philippherrmann/sts_sweep/runs/frozen-survival-potion-20260913 \
  --device cuda --threads 8 \
  --code-sha 9f15dba5c348f775725232d33e72d2cf8e1b6127 \
  --reviewed-sha 9f15dba5c348f775725232d33e72d2cf8e1b6127
```

Exit 0. Raw log: external `fit-reviewed.log` in the output directory above.
Checkpoints, cached state embeddings and raw HOLDOUT predictions remain external.
No fit repetition, code change, new data, architecture tuning, global TEST
replication or gameplay run followed inspection of the primary result.
Reviewed code's 53 focused tests, four affected CTests and Linux GCC CI passed
before launch. Evidence changes receive diff/metadata validation and CI.
