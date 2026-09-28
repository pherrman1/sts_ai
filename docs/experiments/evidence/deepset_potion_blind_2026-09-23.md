# Potion-pooled-blind DeepSets experiment

**Decision: `POTION_DEEPSET_POTION_BLIND_REJECTED` under the unchanged teacher-forced gate.** P retained strong overall performance but did not fix the recursive-Brew regression. It scored better than C on 5 of 12 validation rows and worse on 7; the paired mean was slightly worse (`P − C = +0.040702` nat), and P remained +25.41% versus the Attention reference on that slice.

## Intervention and scope

P sets the pooled potion block to zero before the existing 256-wide trunk. Its potion embedding and MLP parameters remain in the module for strict checkpoint loading but are frozen and excluded from the optimizer. The exact trajectory decoder still receives the current inventory at every DAG node. As specified in the handoff pseudocode, global features remain unchanged, including `potionCount` and `potionCapacity`; therefore this tests removing the pooled potion identity/slot representation, not every inventory-derived global scalar.

No target, graph, action mask, legality, decoder, or split semantics changed. C and P loaded identical warm-start encoder/decoder state hashes and used the same fixed TRAIN order.

## Frozen provenance and execution

| Item | Value |
|---|---|
| Baseline | `1ed96f2aa564742156cc6593a1fc1915ea4e9033` |
| Reviewed implementation | `cffe964a806891908ea1082bcca632683c4d2d37` |
| Potion cache | `e1c25f2758bf56c7cff392ea02342d809f3ad7427c70b64166244a6b714a251d` |
| Preparation receipt | `165ddba8ed9d47a592de4fc7ec037f1687fbee2ec280daca20307ddbf7d78744` |
| TRAIN membership | 393,677 rows / 19,986 sources; sequence `2cb23f2eac81cd30f0200c49d42f090873b5452b265bb47410d67c46d6745809` |
| VALIDATION membership | 48,590 rows / 2,496 sources; source sequence `d843fcf1f106e8985aef32087c12745da9dfca6f050c64bcca44837578718b32` |
| Split sequence | `607782399125f7785c3a33f65934c9461b8b1e86f053637e8110f51a2294f3ca` |
| Shared batch-order hash | `7699f81a9fad65b7c8ffcde22c4efc6b681ba4dbfd14237451fc8179c85c444d` |
| Warm encoder / decoder | `bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663` / `06eda953b523ed6b3b9dbc3031bf44408c3bc67f0bc8b7862d28c150448819c1` |
| Attention component / decoder / receipt | `ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db` / `dad2df4a0d0d8a31c4707ee21bf92adf9b76c77deb520b49653b5eb789c3d48e` / `1ba8b78524b8b6fc97c00a41eb33fc178cd6f36fa79a6b0af7dcad107ab45363` |
| Runtime | Python 3.12.3; PyTorch 2.5.1+cu121; CUDA 12.1; NVIDIA GeForce RTX 3060 Ti |
| TEST access | encoded `0`, scored `0`, teacher metrics `0` |

C selected epoch 34 (NLL `0.486931329`), within `0.000231` of the PR #298 W reference (`0.487162724`) and inside the predeclared absolute `0.005` reproduction tolerance. P selected epoch 31. The control ran to the 40-epoch ceiling after a late improvement, but earliest strict minimum selection chose epoch 34. The P potion block was excluded explicitly: 107,652 total parameters, 99,292 trainable; the six named potion embedding/MLP tensors were frozen.

### Command

```bash
python3 tools/reproduce_combat_transition_deepset_potion_blind.py --source-worktree . --artifact-root /home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914 --output-dir /tmp/deepset-potion-blind-20260923 --encoder-checkpoint /home/philippherrmann/sts_sweep/runs/shared-transition-deepset-distill-corrected-20260916/student.pt --decoder-checkpoint /home/philippherrmann/sts_sweep/runs/deepset-potion-screen-20260916/B.pt --dedicated-component /home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914/full-union-potion-v1/component.pt --reference-receipt /home/philippherrmann/sts_sweep/runs/deepset-potion-screen-20260916/results.json --reference-decoder /home/philippherrmann/sts_sweep/runs/deepset-potion-screen-20260916/A.pt
```

## Teacher-forced validation

| Metric | Attention reference | C control | P candidate |
|---|---:|---:|---:|
| Trajectory NLL | 0.506803228 | 0.486931329 | 0.489927014 |
| Relative trajectory NLL | baseline | -3.9210% | -3.3299% |
| No-change Brier | 0.092057790 | 0.086665661 | 0.087477024 |
| Normal action-mode accuracy | 0.806321 | 0.816412 | 0.815202 |
| Changed-action mode accuracy | 0.457469 | 0.474956 | 0.479846 |
| Unchanged-action mode accuracy | 0.942907 | 0.950102 | 0.946504 |
| Potion-count accuracy | 0.814556 | 0.825084 | 0.824292 |
| Illegal probability maximum | 0.0 | 0.0 | 0.0 |
| Normalization error maximum | 1.98e-07 | 1.9e-07 | 1.99e-07 |

Slice NLLs for P were Brew 1.92594 (+6.99%), Smoke 0.26921 (−7.98%), recursive Brew 3.02605 (+25.41%), and trajectory-special 1.01527 (+4.52%). P’s no-change Brier improved against Attention by `0.00458`; normal action-mode accuracy improved by `0.00888`, and potion-count accuracy improved by `0.00974`. Illegal mass remained exactly zero, and maximum normalization error was `1.99e-7`.

The full requested C/P slice comparison is below. Δ is the relative P change from C; negative values favor P. These broad slices overlap and are descriptive, not independent tests.

| Validation slice | Rows | C NLL | P NLL | Δ P vs C |
|---|---:|---:|---:|---:|
| Brew present | 281 | 1.966428 | 1.925942 | −2.06% |
| Smoke present | 343 | 0.236134 | 0.269213 | +14.01% |
| Recursive Brew | 12 | 2.985346 | 3.026048 | +1.36% |
| Trajectory-special | 624 | 1.015321 | 1.015272 | −0.00% |
| No change | 47,966 | 0.480057 | 0.483093 | +0.63% |
| Requires action / trajectory-special | 624 | 1.015321 | 1.015272 | −0.00% |
| Multiple trajectories | 139 | 2.457037 | 2.376043 | −3.30% |
| Multiple occupied slots | 23,768 | 0.810127 | 0.813280 | +0.39% |
| Capacity 3 | 45,317 | 0.466580 | 0.469746 | +0.68% |
| Capacity 5 | 3,273 | 0.768707 | 0.769346 | +0.08% |
| Potion count 0 | 9,935 | 0.000000 | 0.000000 | N/A (zero NLL) |
| Potion count 1 | 14,887 | 0.295889 | 0.300633 | +1.60% |
| Potion count 2 | 12,534 | 0.636383 | 0.640232 | +0.60% |
| Potion count 3 | 10,745 | 0.964423 | 0.965954 | +0.16% |
| Potion count 4 | 301 | 1.551847 | 1.573184 | +1.37% |
| Potion count 5 | 188 | 2.387408 | 2.407786 | +0.85% |
| Act 1 | 23,613 | 0.350192 | 0.355471 | +1.51% |
| Act 2 | 15,926 | 0.620332 | 0.623696 | +0.54% |
| Act 3 | 9,051 | 0.608937 | 0.605330 | −0.59% |
| Boss | 4,275 | 1.058889 | 1.061187 | +0.22% |
| Non-boss | 44,315 | 0.431755 | 0.434818 | +0.71% |

## Recursive-Brew validation rows

| Source seed | Graph nodes / edges | Compatible trajectories | C NLL | P NLL | Attention NLL | P − C | P − Attention |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4103211 | 14 / 25 | 6 | 5.163730 | 4.376181 | 3.923493 | -0.787549 | +0.452688 |
| 4106053 | 14 / 25 | 2 | 0.200906 | 0.597247 | 0.252836 | +0.396341 | +0.344411 |
| 4106085 | 38 / 90 | 60 | 1.019845 | 0.680635 | 1.244967 | -0.339210 | -0.564332 |
| 4108025 | 26 / 53 | 2 | 0.273372 | 1.080222 | 1.099746 | +0.806850 | -0.019524 |
| 4109240 | 26 / 53 | 3 | 3.492170 | 1.928140 | 2.184992 | -1.564030 | -0.256852 |
| 4109443 | 259 / 1581 | 4 | 14.163192 | 13.983001 | 8.433895 | -0.180191 | +5.549106 |
| 4111001 | 26 / 53 | 18 | 1.683625 | 1.025416 | 1.195608 | -0.658209 | -0.170192 |
| 4116381 | 26 / 53 | 2 | 0.646446 | 1.281197 | 1.643954 | +0.634751 | -0.362757 |
| 4116985 | 17 / 30 | 12 | 1.075286 | 1.955720 | 1.517049 | +0.880434 | +0.438671 |
| 4118500 | 14 / 25 | 2 | 0.195484 | 0.220763 | 0.458698 | +0.025280 | -0.237934 |
| 4123390 | 46 / 115 | 8 | 1.934889 | 3.167251 | 1.178051 | +1.232362 | +1.989201 |
| 4123895 | 25 / 51 | 2 | 5.975208 | 6.016806 | 5.822315 | +0.041597 | +0.194491 |

P improves on C in **5/12** cases and worsens in **7/12**. Means: C `2.985346`, P `3.026048`, Attention `2.412967`. The high-error source `4109443` has the largest validation graph (259 nodes / 1,581 edges) and remains high under both C (`14.16319`) and P (`13.98300`); its improvement does not account for a slice-level fix. Several simple two-round cases move in opposite directions, so this small cohort gives no clean graph-depth pattern.

Full case metadata (inventory, capacity, boss, Sozu, generated body, target inventory, and graph data) is in the [Stage 0 audit JSON](deepset_potion_blind_recursive_audit_2026-09-23.json). It reports 90 TRAIN recursive rows from 90 seeds and 12 VALIDATION rows from 12 seeds. All audited targets have at least one compatible target trajectory; no obvious target/DAG defect was found.

## Gate and stop

Both arms are `TEACHER_FORCED_REJECTED`. P fails the unchanged gate because the recursive-Brew obvious-slice regression is `+25.41%` (threshold is unchanged), despite overall NLL `0.489927` (`−3.3299%` vs Attention). The original discrepancy is not fixed by removing the pooled potion block. The mean P−C paired delta is `+0.040702` nat; 5 rows improve and 7 worsen. No hyperparameter sweep or alternate architecture was started.

Because P fails, ancestral/exposure evaluation was not run. No TEST scoring, export, native parity, runtime default change, gameplay, or OOC qualification was run.

## Checks and artifacts

- `python3 -m py_compile` on the modified trainer, encoder, wrapper, and focused tests: passed.
- `python3 -m unittest tools.test_combat_transition_deepset_potion_specialist -v`: 13 tests passed.
- `git diff --check`: passed before both implementation commits.
- Paired CUDA execution exited 0; control reproduction check passed; checkpoint reload reproduced validation metrics.
- TEST access counters in the raw receipt are zero for encoding, scoring, and teacher-metric evaluation.
- GitHub Actions CI was not run locally; it remains the authoritative repository check.

Raw receipt: [`deepset_potion_blind_2026-09-23.json`](deepset_potion_blind_2026-09-23.json), SHA256 `16a7958fe0ea6c74ffac1fe7552a66be2215fe19e778a10bfc6254ff8e7ae4be`. Checkpoints remain outside Git at `/tmp/deepset-potion-blind-20260923/C.pt` (SHA256 `99a43bfa138021ff9f645accd1e098ec89863b9498490294837762a93b18ff1c`) and `P.pt` (SHA256 `38c2b8eadc0aa1926c6bbbbe46e952d30e652dee7887559b6b57a0f4726dcab0`).

**Knowledge impact:** updates the current potion-representation hypothesis and experiment status only; runtime defaults and qualified components remain unchanged.
