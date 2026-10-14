# Fight-specific Silver tree prior: offline check (2026-10-14)

Philipp 07:45Z: start from the gen-4 net and fine-tune it on one hard fight. Offline only; no game seeds used.

## Setup
- Data: gen-4 training pack (`silver-az-mlp/gen4/pack`, sha256 b6805ff9…, 2,124,899 roots, A0), split by the
  `encounter` state feature. Folds as the loop: seed % 5, train 0-2, early stop on 3, test 4.
- Base: `gen4/model/model-gen4.pt` (sha256 2a33f01c…), 128/64. Fine-tune = same trainer code
  (`tools/silver_az_mlp.py` at main d45864a, imported by `ft.py`), warm start, gen-4 input scales kept,
  AdamW wd 1e-2, dropout 0.35, batch 512, LR halving, patience 8, selection on fold-3 CE of that fight.
- Metric: fold-4 roots of that fight, paired per root, general gen 4 vs fine-tuned; 95% CI from a
  seed-cluster bootstrap (2,000 draws).

## Fight choice
The Collector (encounter 38): most deaths in the data (1,582 fights, 24.8% deaths, 392 deaths;
52,950 roots). Other boss death rates: Awakened One 27.7%, Time Eater 27.4%, Donu and Deca 26.3%,
Automaton 24.1%, Champ 19.9%. Elites are all below 8%.

## Results (fold-4 CE, fine-tuned minus gen 4; negative = better)
| fight | test roots | gen 4 CE | d CE [95% CI] | top-1 gen4 -> ft |
|---|---|---|---|---|
| **Collector, lr 2e-4** | 9,711 | 1.4411 | **-0.0030 [-0.0039, -0.0020]** | 46.3 -> 46.6% |
| Collector, lr 5e-5 | | | -0.0013 [-0.0018, -0.0008] | |
| Collector, lr 1e-3 | | | 0 (never beat epoch 0) | |
| Collector, no dropout | | | -0.0029 [-0.0049, -0.0007] | |
| Collector, half the train seeds | | | -0.0010 [-0.0016, -0.0003] | |
| Collector, from scratch (fight data only) | | | +0.0589 [+0.0509, +0.0672] | 46.3 -> 42.5% |
| Champ | 13,048 | | -0.0027 [-0.0038, -0.0017] | |
| Automaton | 10,766 | | -0.0019 [-0.0031, -0.0008] | |
| Awakened One | 7,887 | | -0.0032 [-0.0045, -0.0018] | |
| Time Eater | 5,680 | | -0.0016 [-0.0034, +0.0001] | |
| Donu and Deca | 7,020 | | -0.0031 [-0.0045, -0.0016] | |

Scale on the same Collector test roots: gen 1 1.4631, gen 3 1.4473, gen 4 1.4411, fine-tuned 1.4382.
So the fine-tune is about half of one loop generation (gen 3 -> 4: -0.0062). For reference §460 found
gen 3 vs gen 1 (all fights) NOT_SHOWN online (+0.14).

## Reading
- Fight-specific fine-tuning helps offline on every boss, but only slightly (-0.002 to -0.003 CE);
  best epoch is 0-5, so the general net already captures most of what this data holds.
- A net trained on one fight's data alone is much worse: the general net's transfer matters more than
  specialization at this data size.
- The gain grows with fight data (half the seeds -0.001, all -0.003). **Inference:** the bottleneck is
  fight-specific data volume, not the shared net.
- **Observation:** `encounter` enters the net as a raw scalar id (state feature 1, values 1-63) times one
  weight vector, like `aCardId` before the card embedding. The net can only tell fights apart through
  the monster features. An encounter embedding in the general net is an architecture question for the
  net-architecture thread. **Unverified** whether it helps.
- **Inference:** an online check of this fine-tuned net is unlikely to show a difference; not run.

Files: `ft.py` (fine-tune + paired eval), `subpack.py` (encounter sub-packs), `evalpair.py`,
`reports/*.json`, `model-collector-ft.pt` (sha256 31e9891f…, not exported to native).
