# Same-session correction: shared maxHP+HP DeepSets distillation

The original 2026-09-16 DeepSets receipt is superseded. Its implementation
normalized with `arrays[train]` and initialized the HP branch freshly. This
correction makes only the two requested changes: TRAIN normalization uses
`cache["ids"][train]`, with an assertion and focused test that the selected
normalization row IDs equal the TRAIN cache's original row IDs; the HP delta
embedding and HP head copy the verified specialist used by the Attention
control. No architecture, loss, seed, population, TEST evaluation, gameplay,
downstream, or runtime scope changed.

## Stage-A result

The single fixed 40-epoch fit was rerun at code SHA
`b192275ca0584a0c1eee8916176613b428a5e1b4` on the unchanged frozen corpus,
teacher cache, source split, and 393,677 TRAIN / 48,590 VALIDATION victories.
The corrected run selected epoch 40 and passed
`SHARED_TRANSITION_ENCODER_GO` / `CHEAP_ENCODER_QUALITY_GO`.

| Model | maxHP NLL | maxHP accuracy | post-maxHP MAE | HP NLL | HP CRPS | ending-HP MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dedicated specialists | 0.042686500 | 98.1107% | 0.081489 | 2.498291492 | 3.619360053 | 5.341970 |
| Shared Attention control | 0.043219738 | 98.0552% | 0.082812 | 2.501546144 | 3.629157164 | 5.357439 |
| Corrected DeepSets candidate | 0.043216348 | 98.0572% | 0.082567 | 2.506730318 | 3.639513338 | 5.368440 |

Candidate-relative gates were maxHP NLL `+1.2413%`, accuracy drop
`0.0535 pp`, expected post-maxHP MAE `+0.001078 HP`, HP NLL `+0.3378%`, HP
CRPS `+0.5568%`, and ending-HP MAE `+0.026469 HP`. The nonzero-delta maxHP
accuracy drop was `1.0349 pp`, the nonzero NLL delta `0.025596 nat`, and the
catastrophic guard was false. Damage, healing, and low-pre-HP slices passed;
outputs were finite, normalized, and exactly legal. TEST inference rows and
TEST metrics were both zero.

Normalization used 393,677 original row IDs with SHA256
`e42a4dc3a964524a277fdcfde4cbdc552277dc358ce0d1d27e2c612a43ae3214`. The
copied specialist branch hashes were delta embedding
`8795adf502265abf3fb75161e89c42d79481fd69a218ecc485a2066820423858` and HP
head `ede45d686671629e49c016b824c0b6593fa5fbc13d7f4ec4a7d6a1e2a51997c2`,
and both matched the Attention-control specialist. Nine nonfinite-gradient
AMP updates were skipped; no forward-loss overflow occurred. The selected
checkpoint SHA256 is
`bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663` and the
result receipt SHA256 is
`83b2482eab347c09901c3b39f2ce7fed324f6be378ca36ff51f0d3965074c769`.

## Stage-B result

Because Stage A passed, the same CPU timing was rerun once: first 512
VALIDATION rows, four PyTorch threads, 10 warmups, and 100 timed repetitions.
The corrected screen passed `CHEAP_ENCODER_SPEED_GO`.

| Path | Attention median ms (IQR) | DeepSets median ms (IQR) | Speedup |
| --- | ---: | ---: | ---: |
| Encoder only | 101.934 (85.328–110.910) | 4.691 (4.515–4.939) | 21.73x |
| Complete maxHP+HP forward | 102.462 (87.421–110.615) | 4.939 (4.767–5.212) | 20.74x |

The speed receipt SHA256 is
`49784953f2d44b733ad99e5e1f9d42cfe1fafb4b9a6ae1def7975e39090ce468`.
These are implementation-level CPU timings, not native/OOC speedup claims.

## Provenance, checks, and boundary

The exact prepared representation was reconstructed from the existing frozen
corpus because its `/tmp` copy was absent; the resulting hashes exactly
matched the recorded `prepared.npz` `2badbb85…`, prepared manifest
`13b2c91f…`, and target spec `e2315620…`. Teacher checkpoints and outputs,
preparation cache, corpus, split, and source hashes are unchanged from the
superseded packet. The external corrected run is
`/home/philippherrmann/sts_sweep/runs/shared-transition-deepset-distill-corrected-20260916/`.

Focused verification: `python3 -m unittest
tools.test_combat_transition_deepset_distill` ran 4 tests successfully;
Python compilation, frozen-data preflight, legal-support/finite-probability
checks, selected-checkpoint receipt assembly, and `git diff --check` passed.

This remains an offline quality/speed handoff only. No TEST evaluation,
runtime export, default promotion, native CTM, gameplay, downstream training,
additional seed, architecture, tuning, or downstream consumer changed.

**Knowledge impact:** current experiment evidence and research status only;
no qualified component, executable default, runtime contract, or gameplay
conclusion changed.
