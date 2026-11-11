# Cheap combat roadmap, step 0: offline CPU map and top-k prior coverage (2026-11-11)

Descriptive, offline. No gameplay, no seeds, no workers. Plan: [cheap combat roadmap](../../../knowledge-base/research/combat-search/cheap-combat-roadmap.md).

## Inputs
- **0a:** §783's stop-trace data campaign (`gumbel_stop_data_20261110`): 1,024 G16 + mb4 whole runs, net-0420 out of
  combat, seeds 111430000-111431023 (used there), share `/mnt/project-files/gumbel-stop/data/units/*.tar`. One row per
  Gumbel root at `boundary == 0` (574,741 roots) with `root_cpu_seconds`, `root_sims`, act, room, legal actions.
- **0b:** §787's T1 validation split (`split_of(seed) == 1`, 562 runs, 330,542 rows, 310,371 with ≥ 2 edges), rebuilt
  from the D2/D2b raw rows (refs `ppo-xfer/t1-data/p0..p3`) with `pack_states.py` and `tensorize.py`; row count equals
  T1's `valRows`. Prior = each edge's g7f_E root prior as recorded; net = T2's generalist `pv_f1.ctn`
  (`/mnt/project-files/gumbel-distill/t2/nets/`), run in PyTorch on CPU (`netlogits.py`). Sanity: net top-1 against
  `gumbelChoice` 0.490, T1's eval 0.490.

## Scripts
`cpumap.py` + `cpumap_an.py` (0a, output `cpumap.txt`); `extract_val.py`, `netlogits.py`, `topk_t.py` (0b, output
`topk.json`). Hit@k = the teacher's final edge (`gumbelChoice`) is among the k edges with the highest prior or net
score. Regret@k = max-backed Q of the teacher's edge minus the best max-backed Q among searched edges in the top k (0
when hit), in Silver score units, measured with the teacher's own Q (favours the teacher; descriptive).

## Result 0a (CPU per run on these machines 585 s; §775 measured 509 s on others)
| act | room | roots/run | CPU s/run | share | µs/sim |
|---|---|---|---|---|---|
| 1-3 | normal + elite + other | 397 | 81 | 13.8% | 7-19 |
| 1 | boss | 30 | 35 | 6.2% | 74 |
| 2 | boss | 31 | 64 | 11.3% | 128 |
| 3 | boss (both) | 57 | 158 | 27.8% | 172 |
| 4 | Shield and Spear | 19 | 40 | 7.0% | 130 |
| 4 | Heart (40k) | 28 | 191 | 33.5% | 171 |

Bosses and Act 4 hold 86% of the CPU. A simulation there costs 10-20× one in a hallway fight: boss rooms and Act 4's
elite play prior playouts (ADR-0050, ADR-0060), which call the g7f_E MLP at every playout step. Roots have 6.3 legal
actions on average (2: 9%, 3-4: 26%, 5-8: 46%, 9-16: 18%, ≥ 17: 1%). Game CPU median 457 s, p90 1,318 s, p99 2,280 s,
max 4,976 s.

## Result 0b (all classes; per class in `topk.json`)
| k | 1 | 2 | 3 | 4 | 6 | 8 |
|---|---|---|---|---|---|---|
| g7f_E prior hit | 44.6% | 66.9% | 80.5% | 88.6% | 96.1% | 98.6% |
| distilled net hit | 49.0% | 72.1% | 84.8% | 91.9% | 97.5% | 99.2% |
| g7f_E prior regret | 2.00 | 0.76 | 0.36 | 0.19 | 0.06 | 0.03 |
| distilled net regret | 1.34 | 0.50 | 0.24 | 0.13 | 0.05 | 0.02 |

Bosses and Act 4 are the hardest (net hit@4 90.5% / 87.2%). By the plan's rule (hit@4 ≥ 95% and regret@4 ≤ 0.10)
neither prior passes at k 4; both pass at k 6, where a 6.3-action root is barely narrowed.
