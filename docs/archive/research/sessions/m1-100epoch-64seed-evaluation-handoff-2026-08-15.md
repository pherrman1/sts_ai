# Handoff: Evaluate M1 100-epoch checkpoint on the verified 64-seed block

Date: 2026-08-15  
Repository: `/home/philippherrmann/Documents/sts/sts_lightspeed`  
Branch at handoff: `phase12/encounter-marginalization-decision`  
HEAD at handoff: `0b93c61dfc3741d0386478837b51c567f0ac3e1f`

## Objective

Run the newly trained M1 100-epoch checkpoint on the exact 64-seed gameplay
block previously used to verify the M1 40-epoch win rate, then compare paired
outcomes. Do **not** retrain; training and offline comparison are complete.

## Completed training evidence

Both runs use the same Phase-12 M1 data, split, model seed, rung-4 token-net
architecture, and absolute-Q target:

- Dataset: `build/phase12b_m1.csv` (2,000 source seeds, 210,838 rows)
- Split: `build/phase12b_split.json` (1,600 train / 400 validation seeds)
- Model seed: `STRAT_MODEL_SEED=42`
- Target: `STRAT_Q_TARGET=absolute`
- 40-epoch metrics: `build/phase12b_m1_best_ce_metrics.json`
- 100-epoch metrics: `build/phase12b_m1_e100_best_ce_metrics.json`
- 100-epoch checkpoint: `build/phase12b_m1_e100_best_ce.pt`
- 100-epoch training log: `build/phase12b_m1_e100_train.log`

Offline best-CE comparison:

| Metric | 40 epochs | 100 epochs | 100 − 40 |
|---|---:|---:|---:|
| `val_pol_ce` ↓ | 0.511808932 | 0.495763987 | −0.016044945 |
| `policy_top1` ↑ | 0.790981501 | 0.797404933 | +0.006423433 |
| `margin` ↑ | 5.709117889 | 7.359033585 | +1.649915695 |
| `value_mae` ↓ | 29.819683075 | 31.355741501 | +1.536058426 |
| `value_rmse` ↓ | 36.199400637 | 38.488549053 | +2.289148416 |
| `q_top1` ↑ | 0.250532381 | 0.248778655 | −0.001753727 |
| `q_mae` ↓ | 20.986976624 | 21.628076553 | +0.641099930 |
| `q_rmse` ↓ | 27.469944000 | 28.770730972 | +1.300786972 |

The 100-epoch run reached epoch 100; its best CE checkpoint is epoch 100.
Training used eager CUDA (`STRAT_TOK_COMPILE=0`) because the installed Torch
compile path hit a fake-tensor `aten.baddbmm` SymInt error. The architecture,
data, split, and optimizer recipe were otherwise unchanged.

## Exact verified 40-epoch gameplay baseline

The established baseline is:

- Seeds: `900000..900063` (64 seeds)
- Mode: `bestbench 1000 64 0 900000 <csv>`
- Ascension: 0
- Sims: 1,000
- Threads: 12
- Fair Searcher3
- Searcher3: belief off, chain off, prune on, live-valid on, 64 particles
- Native floor/win OOC models on
- Strategic token gates: card, rest, event, shop, treasure, boss relic all on
- Strategic margin: 1.0
- Combat VNet: `build/v_combat_7k_tuned.txt`, alpha 0.3
- Policy prior: on; PVNet and DistVNet off
- Keys: not collected; Act-3 evaluation behavior as recorded

Baseline files:

- CSV: `build/phase12b_m1_64.csv`
- Metadata: `build/phase12b_m1_64.csv.meta.json`
- Log: `build/phase12b_m1_64.log`
- Result: 16/64 wins = **25.0%**

The metadata sidecar is authoritative for the exact parsed configuration.

## 100-epoch native export

Already completed and parity-checked:

```bash
python3 export_strategic_tok.py \
  build/phase12b_m1_e100_best_ce.pt \
  build/phase12b_m1_e100_best_ce.native
```

Export result: 32/32 parity checks passed. Native artifact:
`build/phase12b_m1_e100_best_ce.native`.

## Required next action

The first attempted 100-epoch evaluation was invalid/incomplete: it produced
only 13 data rows plus a header before the launcher was terminated. Do not use
`build/phase12b_m1_e100_64.csv` for comparison.

Run a fresh, persistent job with a new output path. Use the repository seed
guard and preserve all output files:

```bash
cd /home/philippherrmann/Documents/sts/sts_lightspeed
rm -f build/phase12b_m1_e100_64_full.csv \
      build/phase12b_m1_e100_64_full.csv.meta.json \
      build/phase12b_m1_e100_64_full.log \
      build/phase12b_m1_e100_64_full.exit

setsid nohup sh -c '
  env OMP_NUM_THREADS=12 \
    STS_FAIR=1 \
    STS_SEARCHER3=1 \
    STS_S3_BELIEF=0 \
    STS_S3_CHAIN=0 \
    STS_S3_PARTICLES=64 \
    STS_S3_PRUNE=1 \
    STS_LIVE_VALID=1 \
    STS_OOC_STRATEGIC_TOK_NN=build/phase12b_m1_e100_best_ce.native \
    STS_OOC_STRATEGIC_REST=1 \
    STS_OOC_STRATEGIC_EVENT=1 \
    STS_OOC_STRATEGIC_SHOP=1 \
    STS_OOC_STRATEGIC_TREASURE=1 \
    STS_OOC_STRATEGIC_BOSS_RELIC=1 \
    STS_OOC_STRATEGIC_MARGIN=1.0 \
    STS_VNET=build/v_combat_7k_tuned.txt \
    STS_VNET_ALPHA=0.3 \
    STS_COLLECT_KEYS=0 \
    STS_NATIVE_OOC=1 \
    tools/seed_guard.sh build/one_combat bestbench 1000 64 0 900000 \
      build/phase12b_m1_e100_64_full.csv
  echo $? > build/phase12b_m1_e100_64_full.exit
' > build/phase12b_m1_e100_64_full.log 2>&1 < /dev/null &
echo $! > build/phase12b_m1_e100_64_full.pid
```

Poll separately. Completion requires all of the following:

```bash
test "$(wc -l < build/phase12b_m1_e100_64_full.csv)" -eq 65
test -s build/phase12b_m1_e100_64_full.csv.meta.json
test "$(cat build/phase12b_m1_e100_64_full.exit)" -eq 0
```

Do not treat a partial CSV as a result. Confirm the sidecar reports the same
seed block, 64 seeds, 1,000 sims, A0, 12 threads, fair Searcher3, 64 particles,
and the same OOC/VNet settings as the baseline.

## Comparison command

After completion, compare by seed, not CSV row order. A compact first-pass
summary can be produced with:

```bash
python3 - <<'PY'
import csv
from pathlib import Path

def load(path):
    with open(path, newline='') as f:
        return {int(r['seed']): r for r in csv.DictReader(f)}

old = load('build/phase12b_m1_64.csv')
new = load('build/phase12b_m1_e100_64_full.csv')
assert set(old) == set(new) == set(range(900000, 900064))

def mean(rows, key):
    return sum(float(r[key]) for r in rows.values()) / len(rows)

old_w = sum(int(r['won']) for r in old.values())
new_w = sum(int(r['won']) for r in new.values())
discord = sum(int(old[s]['won']) != int(new[s]['won']) for s in old)
print(f'40 epochs: {old_w}/64 = {old_w/64:.1%}')
print(f'100 epochs: {new_w}/64 = {new_w/64:.1%}')
print(f'win delta: {(new_w-old_w)/64:+.1%}')
for k in ('floor', 'hpEnd'):
    a, b = mean(old, k), mean(new, k)
    print(f'{k}: 40={a:.3f} 100={b:.3f} delta={b-a:+.3f}')
print(f'discordant seeds: {discord}/64')
print('100-only wins:', [s for s in old if not int(old[s]['won']) and int(new[s]['won'])])
print('40-only wins:', [s for s in old if int(old[s]['won']) and not int(new[s]['won'])])
PY
```

## Interpretation constraint

This is a 64-seed paired gameplay comparison, useful as a follow-up check but
not a promotion-grade statistical result by itself. Report the paired win delta,
discordant seeds, mean floor, and end HP. Do not claim that the improved offline
policy CE proves improved gameplay; the 100-epoch offline Q/value metrics were
slightly worse.

## Working-tree note

At handoff creation, the only pre-existing untracked artifact was an accidental
`--help` file from probing the exporter; remove it before completion if it is
still present. Do not commit ignored `build/` artifacts unless explicitly asked.