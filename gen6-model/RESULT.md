# Silver MLP prior gen 6 (written 2026-10-14 ~17:10Z)

Self-play: 40k sims, gen-5 prior (5e9f975a) K=8 w=400, root bonus off; frozen commit f73e6ad7, binary b4586cfc;
seeds 97000000-511 natural + 97001000-511 perturbed; 8 workers, 256/256 units rc=0, no stalls, all tar shas match
their DONE files. 407,179 new roots.

Pack: window orig + x5 + g3 + g4 + g5 + g6 (`--drop-no-fight g3 g4 g5 g6`, #535 packer): 2,531,313 roots,
15,300,967 edges, sha 7efd43f0 (on branch claude/silver-gen6-gpu-data, gzipped parts). missingValue 1000 = the known
x5 stalled seed.

Arms (PLAN-train.md; D added before any gen-6 data arrived):
- A/B/C: warm start from gen 5, tools/silver_az_mlp.py train on CPU (A 2 epochs d0.15; B 40/patience 8/lr-decay
  d0.35; C as B with d0.15).
- D: 128/64 from scratch, distilled (0.5 visit shares + 0.5 softmax of a 512/256 teacher trained on the same pack,
  d0.35, LR halving), d0.15, cosine lr 1e-3, 25 epochs. Teacher and D trained on Philipp's GPU with the net-arch
  thread's arch.py + `--device` (CPU smoke byte-identical); converted with convert.py, exported in the current
  `combat_policy_mlp_v1` format.
- E / Eenc (offline only, need the native loader change from draft PR #541, Philipp's call): D + encounter
  embedding + monster id/intent embeddings / encounter embedding only.

All CE below by gate_eval.py (tools evaluator, each net with its own stored scales, same pack and splits).

| arm | val fold 3 | fold 4 orig (gate) | fold 4 all | fold 4 g6 | TV vs gen 5 |
|---|---|---|---|---|---|
| gen 5 (reference) | 1.2128 | 1.1954 | 1.2091 | 1.1447 | 0 |
| A | 1.2104 | 1.1927 | 1.2072 | 1.1389 | 0.045 |
| B (d0.35) | 1.2135 | 1.1964 | 1.2104 | 1.1473 | 0.055 |
| C (d0.15) | 1.2056 | 1.1877 | 1.2026 | 1.1322 | 0.064 |
| **D (distilled, cosine)** | **1.2029** | **1.1831** | **1.1982** | **1.1302** | 0.078 |
| teacher 512/256 | 1.2044 | 1.1852 | 1.2012 | | |
| E (enc + monster emb) | 1.1937 | 1.1749 | 1.1905 | | |
| Eenc (enc emb) | 1.1955 | 1.1769 | 1.1929 | | |

Teacher/E/Eenc numbers are arch.py's own evaluation (GPU run logs); arch.py reproduces D's numbers exactly.

Selection (lowest fold-3 val among A-D): **D**. Gate: fold-4 orig 1.1831 < 1.1954 -> **PASS** (-0.0123).
Gen 6 = D: `combat_policy_mlp_gen6.txt` sha fe23a54e0e79cca420913e16e0d35807b899ffd9da355ad6106f7a614fe9f811;
`model-gen6.pt` (tools format) 6d525f18. Native parity: max |diff| 2.3e-6 (g6 unit) and 1.5e-6 (orig unit), pass.
Cost: same 128/64 net as gen 5, ~8-9 µs/root (noisy, machine busy).
All arms single seed. Notes: B (gen-4 recipe) no longer improves on gen 5; recipe gains (C over B, D over C) now exceed
the gen-to-gen data gain. E beats D by 0.008 on fold-4 orig; the format change is Philipp's decision.

## Decision (Philipp 17:13Z: "yes switch to E")
Gen 6 = **E**: `model/combat_policy_mlp_g6_E.txt` (header `combat_policy_mlp_v2`, enc + mon_id + mon_dmg tables),
sha ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228, exported by the net-arch thread in PR #541
(branch claude/project-thread-i1z756 at 0f1b70f, native vs torch max |diff| 2.4e-6). arch.py checkpoint
`model/model-g6_E-arch.pt`. Needs a binary built with #541 (old binaries reject v2). D
(`combat_policy_mlp_gen6.txt`, v1) stays as the current-format fallback. Note: the "intent" table is incoming damage
(mKIntent), renamed mon_dmg.
