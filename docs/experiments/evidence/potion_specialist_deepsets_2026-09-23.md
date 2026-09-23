# Potion-specialist DeepSets encoder and trajectory decoder

**Decision:** `POTION_DEEPSET_SPECIALIST_REJECTED` by the existing teacher-forced gate. The primary warm-start arm is a narrow miss under the preregistered follow-up rule: overall validation NLL improves substantially, while the strongest remaining failure is recursive Brew (+13.31%) on 12 rows. No follow-on architecture arm was started.

## Question and fixed protocol

Can jointly training a dedicated 64-wide DeepSets potion encoder and the existing exact potion trajectory decoder close the gap left by substituting the maxHP/HP DeepSets representation?

The implementation is based on `c62f3694517bf622d2670a9fbf3c20a70380a763`; experiment code is `3d1db667f0859c5a1d4788cb4232eaf6f6670bb7`. It preserves the canonical input domains, slot embeddings, sum pooling, 64-action DAG, legality masks, Brew/Smoke semantics, and hidden-trajectory marginalization. The two arms used FP32, seed `20260912`, batch 512, AdamW, encoder/decoder learning rates `1e-4`/`1e-3`, weight decay `1e-4`, clip 1.0, 12–40 epochs, patience 6, earliest strict VALIDATION minimum, and identical TRAIN batch order.

- W initialized the encoder from `bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663` and decoder from `06eda953b523ed6b3b9dbc3031bf44408c3bc67f0bc8b7862d28c150448819c1`.
- S used deterministic seed `20260912` initialization.
- Population: TRAIN 393,677 rows / 19,986 sources; VALIDATION 48,590 / 2,496 sources. The run receipt records zero TEST encoding and inference rows. Existing loaders read the prepared cache as a whole; TEST was not encoded, scored, used for selection, or used for debugging.
- Cache, row-order, split, source-sequence, and initialization hashes are recorded in the JSON receipt. The three frozen prepared artifact hashes were reproduced using the cache-provenance source revision before this run.
- Hardware: NVIDIA GeForce RTX 3060 Ti, CUDA available, PyTorch 2.5.1+cu121. W ran 33 epochs (selected epoch 27, 296.98 s); S ran 40 epochs (selected epoch 34, 360.07 s).

## Results

Dedicated Attention reference validation trajectory NLL was `0.5068032282`.

| Arm | Selected epoch | Trajectory NLL | Relative to reference | No-change Brier | Normal action-mode accuracy | Normal count accuracy | Recursive Brew NLL (n=12) |
|---|---:|---:|---:|---:|---:|---:|---:|
| W warm start | 27 | 0.487162724 | -3.8754% | 0.086596849 | 0.816036359 | 0.824688321 | 2.734195133 (+13.3126%) |
| S scratch | 34 | 0.498382425 | -1.6616% | 0.088550722 | 0.813096777 | 0.822395030 | 3.219932560 (+33.4429%) |
| Attention reference | — | 0.506803228 | baseline | 0.092057790 | 0.806321144 | 0.814556144 | 2.412967235 |

Both arms had exactly zero illegal probability, finite normalized distributions (maximum normalization error `2.14e-7` W / `2.04e-7` S), and checkpoint reload reproduced validation metrics. The W arm improves no-change Brier and both reported accuracies versus the reference. Relative Brew NLL is +7.09% W / +4.47% S; Smoke NLL is -16.55% / -10.99%; trajectory-special NLL is +3.18% / +1.91%. The strongest observed degradation is recursive Brew; because that slice has only 12 rows, its estimate is limited. These diagnostics do not establish why the model behaves this way.

The existing gate marks both arms `TEACHER_FORCED_REJECTED` because of the obvious slice regression, so the overall experiment decision remains rejected. Under the requested stop rule, W is a narrow miss: it beats the prior frozen DeepSets result (`0.537569223`, +6.0706%) and the Attention reference overall, but does not qualify. This does not qualify the architecture or runtime component.

## Stop and next experiment

No ancestral draw, TEST evaluation, export, Python/native parity, CPU latency, gameplay, or default/runtime change was run. Do not proceed to width or hyperparameter sweeps from this result. A focused next architecture experiment could add one bounded interaction layer to the potion-specific set encoder so potion slots can interact with one another and card/relic context, while keeping the same target, data, width/output contract, and evaluation gate. First inspect the 12 recursive-Brew examples and their legal trajectories to ensure the slice is not dominated by a data/target corner case; keep that inspection on TRAIN/VALIDATION only. This is a recommendation, not evidence that pairwise interaction will resolve the failure.

## Artifacts

- [Complete machine-readable receipt](potion_specialist_deepsets_2026-09-23.json), including all epoch histories, gate output, reload metrics, diagnostic slices, hashes, and row counts (SHA256 `31a26d11553b30ecfd3f495d21e8cce61dd74129bcf5516d160cc94a66621a44`).
- W checkpoint SHA256: `71d88a71cf7579e1092c3b3c27e000538a6aafe35bbf5228c10c15fa0edd4ace`.
- S checkpoint SHA256: `b0bac3affcf389e6317cc90424ad58d69fc10a6f623a320e8db0a22379367c62`.
- Run output: `/tmp/deepset-potion-specialist-20260923`.

**Knowledge impact:** this experiment updates the current potion-representation result and evidence. Qualified components and runtime defaults remain unchanged.
