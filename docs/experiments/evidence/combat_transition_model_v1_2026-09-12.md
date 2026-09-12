# Combat-transition model v1 — first offline comparison

Date: 2026-09-12. This is an offline experiment on the already-collected
whole-combat transition corpus. No simulator collection, runtime Silver
replacement, model export, gameplay gate, or GCP job change was made.

## Decision

**XGBOOST_SUFFICIENT.** The validation-only composite selected the XGBoost
depth-6 finalist. DeepSets and attention did not satisfy the preregistered
strict held-out improvement rule. TEST was evaluated once after the family and
hyperparameter selection freeze.

## Frozen corpus and provenance

- Producer Git SHA: `f0bbd7721e7cc1453976ebb91ee11ebe6127a2bf`
- Release executable SHA256:
  `d0a1c66faa931498660811a7406fbc6be93d63c5e7ef4f6f24c910e4f57c2872`
- Teacher: `silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77`
- Frozen teacher model hashes: policy
  `24793bd39dd1a35c8865035e458c3aa40616ef021cb26b05f914f72fb5e5a321`,
  floor `3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3`,
  win `fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`
- Input contract: `combat_predictor_input_v1`, field-schema hash
  `1a92692da9247008`; transition row: `combat_transition_row_v2` under
  `combat_transition_v1`.
- Source range: 25,000 requested seeds `4100016..4125015`; 24,999 completed;
  one quarantined source, `4102275` (`process_exit_134`).
- Corpus: 510,030 rows, 2,859,877,223 bytes, SHA256
  `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
- Final manifest SHA256:
  `33669cd99eed8317987192825b5111a68d1e60269c166def2fe568364e20ad59`.
- Shard audit: 322/322 shard manifests validated; no overlapping or
  out-of-range source groups; every row had exactly one valid raw capture.
  The external `corpus_audit.json` preserves the path, row count, and data/
  manifest SHA256 for every shard.

Collection configuration was `combattransitiongen`, ordinary project-fair
Silver/Searcher2, `STS_FAIR=1`, native OOC source policy
`runFullRunOOC_policy_v1`, `STS_NATIVE_OOC=1`, Searcher3 off, exact 10,000
simulations/root, allocated reuse cap 32,768, adaptive/pruning/learned-PUCT/
direct-leaf/sequential-halving off, Silver telemetry on, heuristic map routing,
card-skip threshold `-0.5`, no key collection or opt-in gates, shop value on,
rest value off, Ascension 0, and `OMP_NUM_THREADS=8`. The frozen Silver
widening parameters were chance/end-turn `c=3.7028`, `alpha=0.52389`, with
exploration parameter 25.0; particle/belief modes were not applicable to this
private-chance Silver search.

The source-group split is
`SHA256("combat-transition-model-v1:" + sourceSeed)` interpreted as a
big-endian 64-bit value modulo 100: `<80` train, `<90` validation, otherwise
test. Counts are train 19,986, validation 2,496, test 2,517; the split
manifest SHA256 is
`e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32`.

## Corpus audit

There were 491,897 wins and 18,133 deaths, with 18,133 distinct source seeds
containing a death. Rows/source were min 2, median 21, mean 20.4020, p95 29,
max 34. Observed coverage counts are:

| Dimension | Counts |
| --- | --- |
| Act | 1: 238,946; 2: 171,452; 3: 99,632 |
| Room | NORMAL: 329,935; ELITE: 118,335; BOSS: 53,934; EVENT: 7,826 |
| Floor band | 1–15: 214,418; 16–30: 163,799; 31–45: 102,405; 46+: 29,408 |
| Starting HP fraction | <25%: 7,306; 25–49%: 34,424; 50–74%: 89,886; 75–100%: 378,414 |
| Burning elite | false: 483,012; true: 27,018 |
| Potion count | 0: 104,996; 1: 154,974; 2: 131,638; 3: 112,586; 4: 3,434; 5: 2,402 |
| Deck size | 0–10: 18,525; 11–15: 123,846; 16–20: 130,227; 21–30: 201,605; 31+: 35,827 |

Encounter counts, by encoded encounter ID, were:

```text
1:18631, 2:18817, 3:18827, 4:18679, 5:10455, 6:5845, 7:10361,
8:9784, 9:5355, 10:8294, 11:8384, 12:5814, 13:9824, 14:10556,
15:18046, 16:17864, 17:17849, 18:8533, 19:8669, 20:8583, 21:9003,
22:8967, 23:8970, 24:8826, 25:9009, 26:4837, 27:4864, 28:12137,
29:8883, 30:12189, 31:6954, 32:7019, 33:6968, 34:13471, 35:13597,
36:13617, 37:6381, 38:6179, 39:6208, 40:12780, 41:8607, 42:8772,
43:4595, 44:4442, 45:4409, 46:4601, 47:4477, 48:4523, 49:4477,
50:8157, 51:8086, 52:7962, 53:3576, 54:3456, 55:3606, 58:156,
61:3373, 62:877, 63:1849
```

Persistent changes were present in the following rows (source counts in
parentheses): HP 375,184 (24,999), max HP 17,870 (5,320), gold 21,781
(16,062), potion count 147,060 (24,908), potion slots 148,005 (24,908),
relic data 124,080 (13,329), at least two relic counters 21,036 (3,921),
deck structure/upgrades 1,151 (1,140), deck misc 109 (101), stolen gold
37,894 (14,756), Smoke Bomb 3,001 (2,819), and other persistent fields 1,151
(1,140). The most common changed relic IDs were 52 (37,165 rows), 44
(35,448), 26 (26,193), 31 (22,557), 68 (12,918), 30 (10,878), 116 (1,968),
and 46 (298). Changed card IDs were 243 (1,151) and 278 (109).

The observed label summary is `P(win)=0.9644472`,
`E(post HP fraction | win)=0.7828707`, and implied
`E_alive_hp=P(win)*E(post HP fraction | win)=0.7550374`.

## Model protocol and results

Inputs were restricted to the predictor contract: 14 globals, canonical typed
card/relic/potion tokens, relic acquisition order, and potion slot. Source
seed/RNG/future queues, post-state, hidden monster state, and old features were
not used. The flattened XGBoost representation had 2,846 fields; 721
nonconstant TRAIN fields were retained. DeepSets had 89,338 parameters and
attention had 107,970 parameters (global/card/relic/potion tokens, width 64,
two layers, four heads, no arbitrary card positional embeddings).

Exact fit command:

```text
OMP_NUM_THREADS=8 /usr/bin/time -v -o /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/fit-time.txt python3 tools/combat_transition_model_experiment.py fit --prepared-dir /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1 --output-dir /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1 --device cuda --threads 8 --xgb-rounds 400 --nn-batch 2048 --nn-epochs 12 --nn-patience 3 --training-seed 20260911 --bootstrap-reps 1000
```

CUDA was required and used for XGBoost and both neural families. XGBoost’s
prespecified depth-4/depth-6, learning-rate .05, min-child-weight 1 grid chose
depth 6 at 400 rounds. The validation composite scores were XGBoost 0.179493,
DeepSets 0.180073, and attention 0.180856.

Aggregate TEST metrics (lower is better except AUC) were:

| Family | Survival AUC / Brier / logloss | Winning-HP MAE / RMSE / bias | Joint alive-HP MAE / RMSE / bias |
| --- | --- | --- | --- |
| XGBoost | 0.974918 / 0.018980 / 0.065256 | 0.075240 / 0.111074 / +0.000264 | 0.082444 / 0.125727 / −0.000735 |
| DeepSets | 0.975461 / 0.018809 / 0.064157 | 0.076545 / 0.112429 / +0.011146 | 0.083051 / 0.126736 / +0.011100 |
| Attention | 0.975634 / 0.019448 / 0.065977 | 0.076256 / 0.115493 / +0.022280 | 0.083308 / 0.130533 / +0.024990 |

Source-bootstrap 95% intervals for model-minus-model error were:

| Difference | Brier | Winning-HP MAE | Joint alive-HP MAE |
| --- | --- | --- | --- |
| DeepSets − XGBoost | [−0.000492, +0.000159] | [+0.000907, +0.001695] | [+0.000144, +0.001045] |
| Attention − XGBoost | [+0.000154, +0.000787] | [+0.000576, +0.001477] | [+0.000347, +0.001353] |
| Attention − DeepSets | [+0.000360, +0.000923] | [−0.000573, −0.000003] | [−0.000063, +0.000577] |

Selected-XGBoost TEST slices show the main weakness is the hard tail: Brier
was 0.006391 / 0.028482 / 0.032663 for acts 1 / 2 / 3; 0.004375 / 0.021462 /
0.024955 / 0.094614 for NORMAL / EVENT / ELITE / BOSS respectively; and
0.137486 for starting HP below 25%. The five worst survival-Brier
encounter slices were IDs 53 (n=386, 0.152318), 37 (646, 0.144974), 38 (639,
0.131578), 39 (619, 0.131173), and 55 (379, 0.127001). Full calibration and
all fixed slices remain in the external model-evidence JSON.

## Cost, validation, and outputs

- Wall time: 825.60 s (13:45.60).
- CPU time: 878.81 s user+system (844.72 + 34.09).
- Peak resident memory: 16,113,592 kB (15.367 GiB).
- GPU: RTX 3060 Ti, CUDA `cuda:0`; peak observed fit use was approximately
  5.5 GiB VRAM at 100% utilization.
- Serialized model sizes: XGBoost survival 2,428,762 bytes; XGBoost winning-HP
  2,629,384 bytes; DeepSets 366,310 bytes; attention 446,453 bytes.
- Serialized model SHA256: XGBoost survival
  `3b5031a482ddd63b32a40cbe9d841fbf59035852c9bfe0324400a0517d3b55f0`,
  XGBoost winning-HP
  `d2d4a11c348df7cea3feb1f4ea5cd6f7c8df99a59ab9f9b9554119a25895236d`,
  DeepSets `ee6d4caf53773dbe667f18f02e98e1a69827b612b16ddff191752aa6ee23e8ef`,
  attention `d8f5d2cac39e2041ff19dc61461dea0b435ba5aee9a32a0e571243dc520becd8`.
- Validation-only warm inference timing (CUDA, host-to-device input staging
  included; 100 batch-1 or 20 batch-2,048 repetitions): XGBoost
  `0.260/0.391 ms` median/p95 at batch 1 and `3.659/4.119 ms` at batch 2,048;
  DeepSets `0.633/0.866 ms` and `9.332/9.887 ms`; attention
  `0.943/1.438 ms` and `85.508/86.092 ms`.
- Repository validator: PASS, exit 0; 510,030 rows, 24,999 source seeds,
  zero quarantined rows, and outcomes 491,897 wins / 18,133 deaths.
- Unexpected health failures: zero. The one quarantined source is the recorded
  `process_exit_134` source above.

Derived evidence is preserved at:

- Corpus run: `/home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/`
- Experiment run: `/home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/`
- Audit: `corpus_audit.json`; split: `split_manifest.json` and
  `split_manifest.sha256`; prepared data: `prepared.npz`;
  final validator: `final-transition-validation.json`.
- Model evidence: `model_evidence.json`; timing: `fit-time.txt`.

The experiment code and focused tests are committed; raw corpus/prepared data,
logs, and fitted model binaries remain external and are not added to Git.
