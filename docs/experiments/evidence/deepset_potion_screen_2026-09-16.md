# Qualified DeepSets representation as the potion encoder

**Decision: `DEEPSET_POTION_REJECTED`.** The corrected, qualified PR #205
DeepSets representation was frozen and compared with the qualified dedicated
potion encoder. Both arms received fresh byte-identical potion decoders and
the same fixed 12-epoch decoder-only recipe. The DeepSets arm failed the
Stage-A teacher-forced gates, so the bounded ancestral stage was not run.

This is distinct from the earlier shared-Attention rejection. It rejects only
this exact frozen DeepSets representation plus the existing potion-decoder
recipe; it does not reinterpret the Attention result as a DeepSets result and
does not establish intrinsic information absence.

## Protocol and provenance

- Baseline: `b0704c755a78fc139c6859781ce899c230919a44` (`main`).
- Implementation SHA: `207db265c41badab848fe3caabe4ab2d9b47de1a`.
- Corrected PR #205 checkpoint SHA256:
  `bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663`.
- Corrected PR #205 result receipt SHA256:
  `83b2482eab347c09901c3b39f2ce7fed324f6be378ca36ff51f0d3965074c769`.
- Reused PR #208 DeepSets representation SHA256:
  `9232027d8331fd2157727276410161e3c12816b6680cb116ebc2b3afd37352af`.
  Its saved row-ID file SHA256 is
  `3dfecd1df38856c3069b1efdc3ed6cf6f6ad1c792afcbf368b3badb7b112e437`.
- Dedicated potion component SHA256:
  `ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db`.
- Preparation cache contract SHA256:
  `e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d`;
  preparation receipt file SHA256:
  `165ddba8ed9d47a592de4fc7ec037f1687fbee2ec280daca20307ddbf7d78744`.
- Source SHA: `1c31b7eb0a7660d43bc27e0849a8955dd0c3daae`.

The PR #208 representation contained 458,589 TRAIN+VALIDATION rows and zero
TEST rows. The driver bound it to the potion cache by original row ID rather
than compact-array position. All 442,267 winning potion rows were mapped;
the mapped row-ID sequence SHA256 was
`2cb23f2eac81cd30f0200c49d42f090873b5452b265bb47410d67c46d6745809`.
A checkpoint re-encoding sample differed by at most `4.77e-7`.

The population was exactly:

| Split | Winning rows | Sources |
| --- | ---: | ---: |
| TRAIN | 393,677 | 19,986 |
| VALIDATION | 48,590 | 2,496 |
| TEST encoded/inferred | 0 | 0 |

The recipe was FP32, seed `20260912`, 12 epochs, batch 512, AdamW, learning
rate `1e-3`, weight decay `1e-4`, gradient clip `1.0`, earliest strict minimum
VALIDATION exact trajectory NLL, and identical fixed batch orders. The exact
64-action native USE/DISCARD DAG, generation-body prior, legality masks, Brew
recursion, Smoke handling, and teacher-forced metrics were reused.

The dedicated encoder and DeepSets encoder were frozen. The PR #205 maxHP
head, HP delta embedding, and HP head were loaded only for the optional
ancestral path and remained frozen; no ancestral path was reached. The decoder
initial-state SHA256 was
`0ddb857bee23593b97e7f65e5a3665ffff57148ea39dc7b4a166dc967cab5f9e`, and the
fixed batch-order SHA256 was
`110ff129ce40099ba612986aabe78195cbcc37bcd11597b9e6b3d012f3cf304d`.

## Stage-A teacher-forced results

Both arms selected epoch 12. Complete epoch histories are retained in the
machine-readable receipt. The selected validation results were:

| Metric | Dedicated A | Frozen DeepSets B | Gate/result |
| --- | ---: | ---: | --- |
| Exact trajectory NLL | 0.506803228 | 0.537569223 | **+6.0706%, fail** (limit +2%) |
| Normal no-change Brier | 0.092057790 | 0.099290556 | +0.00723277, pass |
| Normal action-mode accuracy | 80.63211% | 79.41667% | **−1.2154 pp, fail** (limit −1 pp) |
| Normal count accuracy | 81.45561% | 80.18597% | −1.2696 pp, diagnostic |
| Changed-action mode accuracy | 45.74689% | 43.28690% | recorded |
| Unchanged-action mode accuracy | 94.29069% | 93.56252% | recorded |
| Illegal probability maximum | 0 | 0 | pass, exact zero |
| Normalization error maximum | 1.98e-7 | 1.99e-7 | pass (limit 1e-6) |

Required trajectory slices were:

| Slice | Dedicated NLL | DeepSets NLL | Relative change |
| --- | ---: | ---: | ---: |
| Brew | 1.800035643 | 1.849083811 | +2.7248% |
| Smoke | 0.292553837 | 0.306922152 | +4.9113% |
| Recursive Brew | 2.412967235 | 2.875917191 | **+19.1859%, obvious regression** |
| Trajectory-special | 0.971403817 | 1.001389181 | +3.0868% |

The shared `compare_teacher()` classification was
`TEACHER_FORCED_REJECTED`: overall trajectory relative degradation
`+0.0607060`, no-change Brier delta `+0.00723277`, action-mode accuracy drop
`0.0121544`, obvious-slice regression `true`, illegal probability maximum `0`,
and normalization error maximum `1.9914e-7`. The A/B decoder checkpoint
reload reproduced the metrics, and both fits recorded `optimizerScope: true`.

Because Stage A failed, Stage B was not run. There was no TEST scoring,
runtime/export work, C++ change, default promotion, gameplay, OOC MCTS,
fine-tuning, second candidate, extra epoch, or loss/architecture change.

## Reproduction and receipt

The full external receipt is
`/home/philippherrmann/sts_sweep/runs/deepset-potion-screen-20260916/results.json`
(SHA256
`1ba8b78524b8b6fc97c00a41eb33fc178cd6f36fa79a6b0af7dcad107ab45363`). Raw
A/B decoder checkpoints remain in that external run directory. The compact
tracked receipt is
`docs/experiments/evidence/deepset_potion_screen_2026-09-16.json`.

Checks run: `py_compile` for the changed Python tools; five focused unit tests
for the shared screen, including DeepSets upstream loading/freeze checks;
artifact/cache/row-ID preflight; decoder finite-gradient and exact legality
smoke; A/B checkpoint reload reproduction; and `git diff --check`. CI was not
run locally and remains authoritative. **Knowledge impact:** experiment
evidence and current research status only; qualified encoders and executable
defaults remain unchanged.
