# Result: shortfall head vs the capped head (2026-10-23)

**The capped `a20` stays the fight-level A/B candidate.** The shortfall head `a20sf` fits the step-1b data better
offline, but on the 300 fresh first fights its regret change against the playout is smaller than the capped head's in
both configs, so by the pre-registered rule (README step 5) it does not replace it.

## Exact first fights (README step 4; `first_fights.txt`, `cmp_modes.py`)

Paired regret change against none (the playout), per fight, mean ± SE:

| fights | config | none | a20 /1 (uncapped) | a20 /1 + cap | **a20sf /1** | a20sf − cap |
|---|---|---|---|---|---|---|
| 300 fresh (111333000-099) | prod | 0.790 | −0.251 ± 0.054 | −0.149 ± 0.054 | **−0.068 ± 0.057** | +0.081 ± 0.048 |
| | prod@mb=4 | 0.456 | −0.283 ± 0.047 | −0.174 ± 0.050 | **−0.094 ± 0.044** | +0.079 ± 0.032 |
| 150 held-out (111149650-699) | prod | 0.872 | −0.331 ± 0.076 | −0.117 ± 0.073 | −0.097 ± 0.082 | +0.021 ± 0.062 |
| | prod@mb=4 | 0.498 | −0.265 ± 0.055 | −0.159 ± 0.058 | −0.119 ± 0.048 | +0.040 ± 0.039 |

- Rule: `a20sf` needed a lower pooled change than the capped head in both configs on the fresh fights. It is higher
  in both (+0.081 and +0.079), so the capped head stays. The encounter condition did not come into play; for the
  record, `a20sf` is above none on fresh Cultist (+0.092, prod) and Two Louse (+0.077, prod; +0.024 with max backup),
  within the +0.10 bar.
- All fights are won in every mode. The played outcome (end HP − 0.4 x turns, paired, no turn cap) of `a20sf`
  against none: +0.01 ± 0.15 (prod) and −0.06 ± 0.13 (max backup) on the fresh fights.
- Rows: `a20sf` from the solver built with this directory's code (`a214254f...`); none, /1 and +cap from the capped
  run of the same fights (solver `efc038dd...`, code 0bbc9fdb). The new solver reproduces those rows exactly: 54 of
  54 checked (3 fights per encounter, all six config and mode pairs). Raw rows:
  `/mnt/project-files/exact-combat-research/leaf-value/shortfall/raw_first_fights.tgz` (sha256 2ee57767...).

## Offline (README step 3; `offline.txt`, `offline_report.json`)

Re-packed step-1b units (736,347 roots; the state blocks and every other column equal the original pack's), fold 4
(142,746 roots), RMSE in Silver points against the actual score:

| | shortfall `a20sf` | plain `a20` | `a20` capped at win-now |
|---|---|---|---|
| all | **19.15** (bias −0.69) | 25.00 (−0.76) | 23.19 (−4.79) |
| hallway | 10.31 | 17.37 | 14.80 |
| elite | 17.17 | 22.36 | 20.52 |
| boss | 29.56 | 35.92 | 34.50 |
| act 4 | 38.59 | 44.83 | 43.41 |

- 12.2% of the fold-4 roots end above their win-now value (act 1 3.3%, act 3 20.6%). Over all kept roots the median
  excess is 8.6 points, and the most common HP gain between such a root and the fight's end is 3-4 (26% of them),
  probably Feed, whose kill also adds max HP. The plain head is above win-now at 34.2% of the roots.
- Early stopping took epoch 1 (stop-fold shortfall RMSE 20.34; 7 epochs run).
- Better offline fit did not buy better decisions. A guess, not tested: what matters is error that differs between
  siblings, and the exact win-now term may weigh an HP difference between siblings at full value where the plain
  head discounts it.

## The four smoke fights (README step 6; descriptive)

Leafhead diagnostics replay (`STS_CTMSILVER_FIGHTS`), HP after the two redraws, decisions in brackets:

| fight | production (base10000) | a20 uncapped | a20 capped | a20sf |
|---|---|---|---|---|
| 111339997 f14 (Centurion + Mystic) | 67/67 (49) | 14/18 (136) | 68/67 (50) | 68/67 (50) |
| 111339997 f19 (Collector) | 75/50 (91) | 24/1 (108) | 75/59 (86) | 74/74 (88) |
| 111339999 f12 (Slavers) | 55/55 (36) | 55/41 (74) | 55/55 (55) | 46/55 (53) |
| 111339999 f18 (Darklings) | 46/35 (40) | 56/50 (495) | 40/52 (76) | 54/43 (58) |

Both guards end the stalls.

## Provenance

- Head `a20sf.txt`: sha256 7b2220d5ca8d9907d5d8a17c07c00288336e46e51f38e581f7d50036f5bdef76, on the share at
  `/mnt/project-files/exact-combat-research/leaf-value/heads/a20sf.txt`. Trunk: g7f_E `model.pt`, as for `a20`.
- Re-pack `a20_pack_wn.npz`: sha256 22482a77..., not kept. `../silver_leaf_a20_data_20261022/pack_a20.py` rebuilds
  it with this code's one_combat (`83de6c12...`).
- Commands:
  - `train_head_shortfall.py PACK MODEL a20_head.txt a20sf.txt offline_report.json`
  - `../leaf_head_turn_penalty_20261022/run_tp.sh SOLVER OUT fresh 111333000 100 1 "hblend:a20sf:0.5/1"
    "a20sf=a20sf.txt"`, and the same with `tune 111149650 50 1` (600 and 300 solves, no failures)
  - `python3 cmp_modes.py fresh CAPFF SFFF`, and the same with `tune`
