# §444 evidence: X2-B public (E1 arm P0) native export

Offline engineering qualification. No game seeds driven, no retraining, TEST
never opened. Base `fcd253f1` (origin/main), branch
`claude/x2b-public-retrain-444-r5hv5v`, local run 2026-10-12.

## Inputs (all SHA-256 verified)

| Input | SHA-256 |
|---|---|
| E1 `P0-s0/model.ubj` (278 trees) | `ed8d95dcb93469cd4383d072c29ab5c21d268193f70e0348ab2f2a7c8f1d9de5` |
| E1 `P0-s1/model.ubj` (355 trees) | `227a110ea579657f9f843f0f7197977c7ad25863efb5c9b6491024b1acc13410` |
| E1 `P0-s2/model.ubj` (373 trees) | `e74b7740065742caf06c50abf0dff4dfe8080de78a70d57eb73c66f1f7e35e9c` |
| E1 `SHA256SUMS` (all 21 entries `sha256sum -c` OK) | `9742cf6356bb38806672b0720ebdcc88b4572d38e0e496f61bfb1a232e041064` |
| E1 `validation-predictions.npz` | `8a1ec54fbf5a14db48d25f9eee5bfa31035732eb73052b592517658b7d1d5633` |
| Frozen X2-B `tune/X2/model.ubj` | `99dbac6b5b082c46fe07242d2d15d8ccc6818041cb851efa79d6b423cdcb52dd` |
| Corpus index `corpus-mixed-1024.json` | `ae56f9633ce8da8a72e341978d707c9f145c1f1b6479afa438067af5570dfa00` |
| Sealed VALIDATION rich cache `cache-seal.json` (#334 a4) | `7b4ed6e19615b1d7746297be31c649ed2189c443f56d02a316c91f34ba26a019` |

Local roots: `~/Documents/sts/artifacts/vwin-refresh-334/` —
`e1-focal-20261007-36b5b14f/`, `a3-final1024-x2b-finalist-20261003-49c28d80/`,
`a2a-scale-1024-extra512-8175c9dc-20261002/`, `a4-mlp-structured-screen-20261003/`.
P0 recipe (from E1 report): X2-B recipe (depth 6, eta 0.06, min_child_weight 10,
curHp monotone, subsample 0.8, colsample 0.7, hist), all TRAIN MAP rows,
457 public features (X2-B's 461 minus nextEliteId, nextFight0..2), seeds 0/1/2.
The VALIDATION cache rows are checked identical in order to E1's npz
(sourceSeed, label, rowIdx, branchId) and every source hashes to VALIDATION.

## Output

`models/candidates/v_win_x2b_public_trees.txt`
sha256 `e2d3aa65291df2914119f5d8129fb3aa6b7339ba6fa72eeaf9e86b9402beca90`;
1006 trees, 428 used features (of 457), `logistic 1`, `base_score 0.7728025`,
margin average of the three seeds (leaves scaled 1/3). `grep -c 'nextEliteId\|nextFight'` = 0.
Identity: `models/candidates/v_win_x2b_public_identity.json` (same shape as the
X2-B identity; `source_sha256` is the list of three seeds, `freeze_sha256` is
the E1 `SHA256SUMS`, `ordered_names_sha256` hashes the 457 compact-JSON names).

## Commands

```
python3 -m tools.vwin_export_ensemble models/candidates/v_win_x2b_public_trees.txt \
  $E1/P0-s0/model.ubj $E1/P0-s1/model.ubj $E1/P0-s2/model.ubj \
  --check $A/a2a-512-20260930-1e93bd66/shards/seed-13001025.map.csv   > export-report.json
python3 x2b_public_444.py prepare $O        # parity.csv (1,780 rows, sha 82168faa…, kept in $O)
cmake --preset linux-gcc-release-ccache && cmake --build --preset linux-gcc-release-ccache-build --target one_combat
OMP_NUM_THREADS=1 build/linux-gcc-release-ccache/one_combat winnettest \
  models/candidates/v_win_x2b_public_trees.txt $O/parity.csv 100000 > native.txt
python3 x2b_public_444.py report $O          # report.json
STS_NATIVE_OOC=1 STS_OOC_MCTS=0 STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt \
  build/linux-gcc-release-ccache/one_combat oocmctsconfigselftest   > load-selftest.log
```

`$O` = `~/Documents/sts/artifacts/vwin-refresh-334/x2b-public-444-20261012/`
(also holds parity.csv and report stdout). Release build: GCC, `-O3 -flto`, base `fcd253f1`.

## Results

Export `--check` (762 rows of VALIDATION source 13001025): max |export − xgb
margin mean| 1.51e-7; vs probability mean 6.45e-3 (expected: different ensemble rule).

Native parity (same deterministic selection as §379: 1,024 MAP rows across all
155 VALIDATION sources, acts 1–3, plus nine HP sweeps = 756 rows):
max |native − Python xgb margin mean| **2.46e-7** (mean 3.19e-8, p99 1.21e-7;
worst row 966: Python 0.66970019, native 0.669700434); native vs Python tree-file
walker max 2.96e-9. Gate `<1e-5`: **pass**. Native explicit load:
`CompactTreeNet: 1006 trees, 428 feats`, `PASS live OOC MCTS configuration startup`.

VALIDATION, all 141,566 MAP rows, 155 sources:

| Arm | NLL | Brier | AUC | ECE |
|---|---|---|---|---|
| Export (margin mean, this file) | 0.423623 | 0.138498 | 0.791924 | 0.03164 |
| P0 probability mean (E1) | 0.423700 | 0.138476 | 0.791806 | 0.03095 |
| Frozen X2-B (461 feats) | 0.422608 | 0.137768 | 0.790709 | 0.02774 |

Paired deltas, source-clustered bootstrap (2,000 reps, seed 0, resample sources):

| Comparison | ΔNLL [95% CI] | ΔBrier [95% CI] |
|---|---|---|
| Export − X2-B | +0.001015 [−0.004109, +0.005765] | +0.000731 [−0.000903, +0.002343] |
| P0 prob mean − X2-B | +0.001092 [−0.004084, +0.005878] | +0.000708 [−0.000944, +0.002319] |
| Export − P0 prob mean | −0.000077 [−0.000307, +0.000184] | +0.000022 [−0.000043, +0.000099] |

The P0−X2-B NLL delta reproduces E1's `X2B_minus_P0` (−0.0010917, CI
[−0.005878, 0.004084]) exactly with sign flipped. Removing the four hidden-future
fields costs a small, statistically unresolved amount of VALIDATION NLL; this is
an offline calibration statement only, not a gameplay result.

## Not run

Gameplay/latency benchmarks, TEST, any retraining, CI (local only). The default
`models/v_win_trees.txt` and `models/candidates/v_win_x2b_trees.txt` are untouched.
