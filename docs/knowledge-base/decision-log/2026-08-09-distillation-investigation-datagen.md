# 2026-08-09 — Distillation investigation + large-scale vnet datagen

Date: 2026-08-09
Session/task: Investigate whether model distillation is worthwhile; generate
large-scale combat data for vnet retraining as the recommended alternative.

## Decision: distillation is not a worthwhile standalone investment

Five parallel subagent investigations, synthesized by the architect agent,
concluded that every prior distillation/compression experiment in this repo
failed at gameplay gates (§56 MLP, §57 entity, §58 policy prior, §104
Phase F soft-target, §106 chain compression, §137 mixture retrain). The
only successful cost reduction was pure tree truncation (§52). The
successful quality path is data/target improvement (§126: +12.5pp from
fresh labels).

**Priority-ordered follow-up:**
1. (HIGH) Data-side vnet improvement — the proven lever
2. (LOW) Tree→tree KD as a one-off — cheap, near-zero infra
3. (DO NOT PURSUE) Transformer→MLP, transformer→trees, KD of transformer, int8

## Decision: large-scale combatgen on GCP (Option B: heuristic-OOC distribution)

Chose heuristic-OOC `combatgen` over gate-stack distribution because:
- §126 proved this distribution transfers (+12.5pp from 1,500 seeds)
- §129 gate-stack distribution was NULL at 1,500 seeds
- More data on the proven distribution is lower risk

## Run configuration

- **Mode:** `combatgen 100000 1000 0 0.3` on GCP `sts-test` (24 threads)
- **Regime:** `STS_FAIR=1 STS_SEARCHER3=1`, S3−belief−chain/64p, vnet default ON
- **OOC:** Heuristic (no gate stack — `ooc_strategic_tok_final.native` fails to
  load due to magic-string format mismatch; see below)
- **Seeds:** 3,000–102,999 (fresh, after §126 0–1,499 and §129 1,500–2,999)
- **Output compression:** `/dev/fd/3` → gzip pipe; progress to log file

## Results

| Metric | Value |
|---|---|
| Seeds completed | 14,800/100,000 (crashed) |
| Crash cause | `ActionQueue::pushBack` assertion — capacity 50 overflowed |
| Data saved | 3,355,244 rows, 181 MB gzipped |
| Seed range in data | 3,000–17,860 |
| Filed as | [issue #50](../issues/2026-08-09-issue-actionqueue-overflow.md) |

## VNet training on 7k-seed subset

Extracted seeds 3,000–9,999 (1,580,243 rows, 87,414 fights) to fit in 31 GB RAM.

| | §126 (deployed) | New model |
|---|---|---|
| Rows | 287k | **1,580k (5.5×)** |
| Fights | 16k | **87k (5.3×)** |
| Features | 733 | 751 |
| Trees | 804 | 1,500 |
| Val RMSE | 7.99 | 8.04 |
| Val R² | — | 0.895 |
| Parity | — | PASS (max diff 0.000193) |

## Gate (preliminary, heuristic-OOC, no gate stack)

⚠️ The token net model (`ooc_strategic_tok_final.native`) fails to load on
both GCP and local binaries. Root cause: the model file has magic
`OOC_STRAT_V42` (13 bytes with version suffix) but the loader reads 12-byte
magic then interprets byte 12 ('2' = 0x32 = 50) as the first dimension.
NGLB=41 ≠ 50 → "truncated payload." Both arms ran with heuristic OOC.

256 seeds (126700–126955), 1,000 sims, S3−belief−chain/64p, 24 threads:

| Arm | Model | Trees | α | Win% | Floor | HP | cpu-s/run |
|---|---|---|---|---|---|---|---|
| Control | `v_combat_honest.txt` | 804 | 0.3 | **28.9%** | 39.1 | 11.3 | 24.1 |
| Candidate | `v_combat_7k.txt` | 1,500 | 0.5 | 25.8% | 39.9 | 10.5 | 40.7 |

⚠️ Alpha mismatch: candidate ran at α=0.5 (default for non-default
`STS_VNET`), not the intended α=0.3. Also 1,500 vs 804 trees makes the
candidate ~1.7× slower. Proper α=0.3 comparison not run — initial read is
not promising given the speed disadvantage.

## New facts

- **Token net loader format bug:** the `ooc_strategic_tok_final.native` file
  (Aug 5) has a version-suffixed magic that the loader misinterprets. The
  gate stack is effectively broken on both GCP and local binaries until
  either the model is re-exported or the loader is fixed to skip the version
  byte.
- **ActionQueue capacity-50 crashes** occur under fair-S3+vnet at
  ~1/15,000 seeds. Blocking for long-running datagen.
- **Gzip compression of combatgen CSV:** 59× ratio (1.4 MB → 23 KB for
  small sample; 181 MB for 3.35M rows).
- **RAM limit:** 3.35M rows × int16 → ~12 GB DataFrame, plus ~24 GB float32
  X matrix = ~36 GB peak. Requires subsetting for 31 GB desktop.

## Rationale

- **Inference:** the higher val RMSE (8.04 vs 7.99) despite 5.5× more data
  is consistent with vnet-default runs producing harder/longer fights with
  more state variance. The offline metric doesn't predict gameplay quality
  (§62 rule).
- **Inference:** the gate result (−3.1pp) is confounded by the α mismatch
  and shouldn't be treated as a definitive rejection of more-data training.
  The 1,500-tree model at α=0.3 might match or slightly exceed the 804-tree
  deployed model, but would still be slower — a proper gate needs both
  α=0.3 AND a tree count closer to the deployed 804.

## Evidence

- Investigation reports: 5 subagent outputs (model inventory, prior
  distillation experiments, bottleneck analysis, technical feasibility,
  gate framework)
- `build/vcombat_honest_100k.csv.gz` — 181 MB, 3.35M rows (GCP + local)
- `build/vcombat_7k.csv` — 5.3 GB, 1.58M rows (local subset)
- `build/v_combat_7k.json` — XGBoost model
- `build/v_combat_7k.txt` — native deployable (751 features, 1,500 trees)
- `build/vnet_ctl_1k.csv` — control gate (28.9%, 256 seeds)
- `build/vnet_7k_1k.csv` — candidate gate (25.8%, 256 seeds)
- `docs/knowledge-base/issues/2026-08-09-issue-actionqueue-overflow.md`

## Status and follow-up

- Distillation investigation: complete. Recommendation recorded.
- Datagen: partial (14.8%), blocked by ActionQueue overflow.
- VNet training: complete on 7k-seed subset.
- Gate: preliminary, confounded by α mismatch. Not a rejection of the
  more-data hypothesis.
- **Open:** fix ActionQueue overflow to enable larger datagen runs.
- **Open:** fix token net loader format mismatch to re-enable gate-stack
  benchmarks.
- **Open:** proper gate of the 7k model at α=0.3 with tree count matched
  to deployed (truncate to 804 trees via `export_combat_model.py MAXTREES`).
