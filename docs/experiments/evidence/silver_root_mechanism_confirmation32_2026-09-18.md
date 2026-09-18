# Silver root mechanism: pooled 32-seed confirmation (2026-09-18)

## Scope and decision

This report records the preregistered fresh-seed extension at frozen
implementation SHA `06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e`, baseline SHA
`be5b6ac2c9914b0a56244f2522b7573f81360067`, and Silver upstream SHA
`84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`. The preregistration was committed
and pushed before collection at commit
`5bff722b002a747e8d24ecbdbec9e99f8aad1748`.

Fresh seeds `17..32` contributed two deterministic roots per seed. They were
pooled with the existing seeds `1..16`, producing 32 source-seed units and 64
roots. Every source seed has exactly two roots; each root has four common
replicates per arm at exactly 32 simulations.

The preregistered primary gate fails:

- `C-A` mean B-regret delta: `-0.143262`.
- Source-seed bootstrap 95% CI: `[-0.553535, +0.250062]`.
- Exact two-sided sign test: `p=0.8388`, with improved/worsened/tied source
  seeds `11/13/8`.

Classification: **`ROOT_GUIDANCE_SIGNAL_NOT_CONFIRMED`**. The interval includes
zero and the sign test does not pass. Per preregistration, the learned-PUCT
line stops here: no additional roots, PUCT tuning, policy training, gameplay
qualification, runtime integration, or default change.

## Frozen protocol

- Fresh capture: seeds `17..32` only; 5,724 eligible roots.
- Selection: lowest two `SHA256(UTF8(root_id))` values per source seed, with
  `root_id` breaking hash ties.
- Teachers: frozen 10,000-simulation Teacher-A and independent 25,000-
  simulation Teacher-B labels.
- Replay: arms `A/B/E/F/C/D`, four common deterministic replicates, and 32
  simulations per root/arm/replicate.
- Reduction: four replicates within root, two roots within source seed, then
  paired source-seed pooling across seeds `1..32`.
- Bootstrap: 10,000 paired source-seed resamples, seed `20260918`.
- Sign test: exact two-sided binomial test over non-tied source-seed mean
  deltas; beneficial `C-A < 0`; exact ties excluded.
- Search controls: root-only intervention; ordinary internal UCT, evaluator,
  rollout, chance handling, DPW, RNG contract, unvisited-first behavior, and
  no tree reuse unchanged.

## Results

Lower B-regret is better. B-best probability counts exact B-Q ties.

| Arm | Mean B-regret | B-best probability | Mean within-root SD | Mean within-root range |
| --- | ---: | ---: | ---: | ---: |
| A | 3.406648 | 44.1406% | 2.216593 | 5.182857 |
| B | 2.727984 | 51.9531% | 2.253708 | 5.335434 |
| E | 3.785182 | 39.8438% | 2.239021 | 5.355865 |
| F | 3.715229 | 42.1875% | 2.243973 | 5.357932 |
| C | 3.263386 | 45.7031% | 2.371489 | 5.684414 |
| D | 3.244009 | 48.0469% | 2.419152 | 5.763599 |

| Contrast | Mean regret delta | 95% regret CI | B-best delta | 95% B-best CI | Improved / worsened / tied | Sign p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **C - A** | **-0.143262** | **`[-0.553535,+0.250062]`** | **+1.5625 pp** | `[-5.0781,+8.9844]` pp | **11 / 13 / 8** | **0.8388** |
| C - E | -0.521796 | `[-0.881025,-0.235779]` | +5.8594 pp | `[+0.3906,+11.7188]` pp | 16 / 3 / 13 | 0.0044 |
| E - A | +0.378535 | `[-0.097300,+0.881566]` | -4.2969 pp | `[-9.3750,+1.1719]` pp | 7 / 19 / 6 | 0.0290 |
| B - A | -0.678663 | `[-1.467371,-0.127664]` | +7.8125 pp | `[+0.7813,+14.8438]` pp | 13 / 4 / 15 | 0.0490 |
| D - B | +0.516025 | `[-0.073563,+1.449947]` | -3.9063 pp | `[-9.7656,+1.9531]` pp | 10 / 13 / 9 | 0.6776 |
| F - B | +0.987244 | `[+0.340612,+1.935914]` | -9.7656 pp | `[-15.6250,-3.9063]` pp | 6 / 21 / 5 | 0.0059 |
| D - F | -0.471220 | `[-0.744156,-0.236014]` | +5.8594 pp | `[+3.1250,+8.9844]` pp | 16 / 1 / 15 | 0.0003 |

The informative prior continues to beat uniform PUCT, but that is not the
primary decision comparison. Oracle-informed PUCT does not clearly beat
ordinary UCT, so an imperfect learned approximation is not justified by this
evidence. Because the primary gate failed, B-best and harmful-tail review are
not promotion gates for this run.

## Provenance and artifacts

The fresh raw artifacts are retained under
`build/scientific-root-confirm32-06d9de3/`. The pooled replay contains 1,536
rows (`64 × 6 × 4`).

| Artifact | SHA-256 |
| --- | --- |
| `capture-all.jsonl` | `451adbf65487fc4d13df749d8c9d291cd4463e445185b9559037fca97ce4ebda` |
| `selected-roots.jsonl` | `57eec83832cb954c3c5ed066487169b43cd4325e4fae08830729c4621b20df1e` |
| `selected-roots.jsonl.manifest.json` | `a72bfc545db97079ad4e0eb3354413a87fed6d60afb95d3016dd3e8b7a8c2b8f` |
| `teacher-labels.jsonl` | `fb6b7bcd9cf3f261758bda2d930d609b7c8ee48bad0e44c4b40a660b92cfd25c` |
| `replay.jsonl` | `20ad3b46c3de49155d29501c7883e77cc79c7889972d8acd9eae2ff8939d9e2b` |
| `replay-pooled.jsonl` | `e07633bd6d43ec9a75399532aa80dcb56f13f5d8ab5ec5476fdd021290f78d03` |
| `analysis-pooled-source-seed.json` | `38ed15b3a41366b11f5f59d543632ca11a4f1c1fa4b48430e895c7527eb4d5ae` |
| `run-manifest.json` | `21d0ff35be5b1308b70557d2c70879ea33840538524cf3e9a6188694e69811cc` |

The frozen executable hashes were restored after the temporary gate-only
32-root orchestration build: `one_combat`
`0bdac1524e9074400b79e0f8f8cedfc0f7b0d5bb5ed754ad60de282be8c1137f`,
`silver_leaf_relabel`
`2f7fe3db2ae735d6ca269f1664db18f00827132b03573ab5326e44beaeeee5af`, and
`silver_root_mechanism`
`e1f056cfbc12fe18a8bf08431b3faedf3586929d56481b15f19be1308fbd0200`.

**Knowledge impact:** current research status and experiment evidence updated;
learned-PUCT line stopped with no training or default change.
