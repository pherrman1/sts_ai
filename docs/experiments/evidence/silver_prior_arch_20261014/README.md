# Silver tree-prior MLP: architecture and training sweep (offline, 2026-10-14)

Philipp (2026-10-14 07:40Z) asked for a thread that experiments with the Silver tree-prior MLP's
size, structure and training parameters. Everything here is offline. No game seeds were used,
nothing was evaluated online, and no defaults changed. This is exploratory evidence, not a
ledger entry. A later online test gets its own § with a pre-registration.

## Setup
- **Data:** the gen-4 training pack (`/mnt/project-files/silver-az-mlp/gen4/pack`, sha256
  b6805ff9…, 2,124,899 roots: orig, x5, g2, g3, g4). Folds are seed % 5: train 0-2, validation 3,
  test 4. Selection used fold-3 CE only; fold 4 was read once, for the shortlist (`fold4.json`).
- **Trainer:** `scripts/arch.py` imports `tools/silver_az_mlp.py` (main d45864a) for data, batching
  and metrics, and generalizes the net:
  - optional state tower, third layer, card embedding width and dot head;
  - `--enc-emb`: encounter id embedding; `--mon-emb`: per-slot embeddings of the monster id and of
    the `mKIntent` feature, which is the incoming damage, not an intent category (`arch.py` calls it
    intent);
  - `--teacher LOGP --alpha`: distillation; `--sched cosine`.
  - All runs are from scratch: AdamW, batch 1,024, value weight 0.1.
- **Paths:** the scripts write to `/root/arch` (cloud container). Queues `scripts/q*.txt` with
  `lane2.sh` give the exact commands.
- **Cost:**
  - `scripts/bench.cpp` is a copy of the `CombatValueNet::predictPolicyMlp` loops, generalized to
    each variant; it uses 4,000 random fold-4 roots, 5.9 edges/root (`timing-bench.txt`).
  - The shipped-layout candidates were also timed with `one_combat silverpolicymlpcheck` built
    from this branch (`timing-native.txt`).
  - All numbers are min of 3 passes on a shared cloud machine; read ratios, not absolutes
    (gen 4: bench 9.9 µs, native 9.3 µs).
- **Baselines reproduce:** `b0` (gen-4 recipe from scratch) 1.2713 vs 1.2718 in the gen-4 report;
  `t512` 1.2610 vs 1.2616.

## Main result: cosine LR 1e-3, 25 epochs, two training seeds per arm (128/64 throughout)
| arm | val CE s0 / s1 | fold-4 orig CE (s0 / s1) | fold-4 orig top-1 | native µs/root |
|---|---|---|---|---|
| gen 4 as deployed (warm start, LR halving) | 1.2678 (gen-4 report) | 1.2103 | 57.2% | 9.3 |
| dropout 0.35 | 1.2692 / 1.2763 | 1.2137 / - | 56.9% | |
| dropout 0.15 | 1.2597 / 1.2630 | 1.1980 / 1.2000 | 57.6% | |
| dropout 0.15 + distillation | 1.2550 / 1.2556 | 1.1949 / - | 57.9% | 9.8 |
| dropout 0.15 + encounter embedding | 1.2544 / 1.2557 | 1.1891 / - | 57.9% | |
| dropout 0.15 + distillation + encounter | 1.2510 / 1.2506 | 1.1893 / 1.1892 | 58.3% | 9.9 |
| … + monster id and incoming-damage embeddings | 1.2484 / 1.2504 | 1.1871 / 1.1899 | 58.4% / 58.6% | 9.9 / 10.2 |
| 512/256 teacher (dropout 0.35, LR halving) | 1.2610 | 1.1965 | 57.7% | 3.9x (bench) |

- **Distillation:** the target is 0.5 × visit shares + 0.5 × the 512/256 teacher's softmax, on
  train roots only.
- **Encounter embedding:** a 16-d embedding of state column 1 (`encounter`). Raw it enters only as
  one number times one weight vector, so the net cannot treat fights as categories.
- **Monster embedding:** 16-d embeddings of `mKId + 1` and `mKIntent` for each occupied slot.
  `mKIntent` is the slot's incoming damage (0 when it is not attacking); the features carry no
  intent category (buff, debuff, defend).
  Its gain over encounter + distillation is small and not consistent: val −0.0026 / −0.0002,
  fold-4 −0.0021 / +0.0007. **Inconclusive.**
- **Cost:** the embeddings add one table row per node, with no measurable cost.

## Other variants (one seed; LR-halving recipe unless marked)
| variant | val CE | bench µs/root |
|---|---|---|
| 128/64 dropout 0.35 / 0.25 / 0.15 / 0.15 seed 1 / 0.05 | 1.2713 / 1.2629 / 1.2609 / 1.2673 / 1.2677 | ~10-11 |
| card embedding 64 (dropout 0.35) | 1.2707 | 9.8 |
| 128/64/32 third layer (dropout 0.15) | 1.2659 | 10.7 |
| 256/64 / 256/32 (dropout 0.15) | 1.2655 / 1.2674 | 15.8 / 13.8 |
| state tower 1766→256→128 | 1.2746 | 14.3 |
| two-tower dot head (32-d) | 1.3335 (diverged) | 28.6 |
| 64/32 dropout 0.15 (halving / cosine / cosine + distillation) | 1.2704 / 1.2688 / 1.2687 | 6.2 |

- **Halving is noisy:** the LR-halving schedule halves on any stalled epoch, which makes it
  seed-noisy (dropout 0.15: 1.2609 vs 1.2673). The main table therefore uses cosine with two seeds.
- **Size and depth don't help:** depth, width and a state tower do not help at this data size once
  dropout is lower. 64/32 at dropout 0.15 matches the gen-4 recipe at 128/64 for 0.62x the cost.

## Native support for the embedding tables (this PR)
A new header `combat_policy_mlp_v2` takes the v1 body plus optional `enc 128`, `mon_id 128` and
`mon_dmg 128` tables (128 × h1, projection folded in).
- Loaders older than this PR reject the v2 header instead of silently dropping the tables (review
  finding on 12d90213); the new loader rejects tables under a v1 header. Files without tables stay v1.
- `predictPolicyMlp` adds them once per node:
  - the encounter row is the rounded value, clipped to 0..127;
  - per slot, `id + 1` and the incoming damage count only when the id is nonzero and not −1
    (empty or dead slot), matching the sparse training rows.
- Files without tables load and score as before. The gen-4 file stays within 1e-6 of the float64
  reference.
- `scripts/export_native.py` writes these files and checks them:
  - exported files match torch within 3e-6 (`parity-native.json`);
  - the unit test `test silver_searcher` covers a hand-computed v2 case, including an empty slot,
    and the rejection of tables under the v1 header.

## Files
- `summary.json`: every run. `runs/*.json`: per-run training reports. `fold4.json`: the shortlist
  on fold 4.
- `models/`: native files `combat_policy_mlp_c_*.txt`.
  - `c_dist_s0` (v1) needs no new code.
  - `c_encdist_s0` and `c_mon_s*` (v2) need this PR's loader.
  - `gen6/`: the gen-6 thread's GPU arms E (enc + mon, distilled) and Eenc (enc only), trained on the
    gen-6 pack (branch `claude/silver-gen6-gpu-data` at cf900813), exported here as v2 with parity in
    `parity-native.json`. Their reported val / fold-4 orig: E 1.1937 / 1.1749, Eenc 1.1955 / 1.1769,
    against D (distilled, no embeddings, v1) 1.2029 / 1.1831. One seed each.
  - Torch checkpoints for the shortlist, the teacher `t512` and `b0` (`SHA256SUMS`).

Knowledge impact: `docs/knowledge-base/architecture/combat-search.md` documents the optional
tables. The results are exploratory and stay here until an online test.
