# Value-net leaf V2 (smoke): the Q head as Silver's leaf value, or as a Q-init, in boss fights (result)

Status: final, smoke only (cloud, 2026-11-16). Follows V0 / V1 ([../value_leaf_v0v1_20261114](../value_leaf_v0v1_20261114/RESULT.md),
LEAF_PAYS offline). A fight gate on all of §770's boss states was drafted but not run: the smoke below was clear
enough, and the gate would have cost about 6x g16mb's CPU per leaf arm. Philipp chose the Q-init test on 2026-11-16
at 15:10 CET (decision card); the line was to close if that did not help on the same bosses.

## Question

V1's `V1_d64` Q head orders the actions of played boss roots like about 23 playouts (offline). Does Silver play boss
fights better when (a) its new tree leaves take that Q head's value instead of a playout, or (b) the head only starts
the edge values of well-visited nodes (Q-init) and the playouts stay?

## Code (this branch; all default off)

- Native Q head in `CombatTokNet` (loaded when the file has `qh.*` tensors). Parity with PyTorch on 32 D2 gate-split
  roots (191 edges): max |ΔQ| 1.1e-4 score units; ctest `combat_tok_net_q_parity` (16 rows, small untrained Q net).
- `SilverSearcher::leafQNet` behind `STS_SILVER_LEAF_QNET=boss|all` and the `expertfights` arm part `lq` (boss rooms
  and Act-4 elites): a new or unvisited child of a decision node takes Q(parent, edge); one forward per parent, cached.
- Diagnostics: `STS_SILVER_LEAF_QNET_SHADOW=PATH[:N]` (leaves keep their playout; the net's value is logged next to
  it), `STS_SILVER_LEAF_QNET_CALIBRATE=K` (first K net leaves of each search played out, then net + their mean offset),
  `STS_SILVER_LEAF_QNET_QINIT=K:M` (Q-init: at a non-root node with ≥ K visits one forward; selection values edge e
  at (M (Q_e + offset) + n_e v_e) / (M + n_e); leaves keep playouts).
- Per-copy records in `expertfights` add `rolloutPlayouts`, `leafQValues`, `leafQForwards`.

## Smoke design

- §770's environment, states and copy seeds (`run_unit.sh`: §774's script; arms `gsh16+flat16000+mb4` (g16mb),
  `gsh16+flat16000+mb4+lq`, `lq` (production + leaf) in the act's boss fights, `STS_EXPERT_FIGHTS_MAX_ACT=<act>`,
  `STS_SILVER_PRIOR_MLP_FMA=0`). Units: §770's two smoke runs 1675881103 (act 1) and 1648247344 (acts 1-3): five
  bosses (Hexaghost, The Guardian, Automaton, Time Eater, Donu and Deca), 4 copies per side. Binary of this branch,
  default preset, 4-core cloud container (four units in parallel, so CPU ratios are within-unit).
- Variants: the same script with one more variable (`_CALIBRATE=64`; `_QINIT=64:16`; `_SHADOW=…:8` on three units)
  and the leaf arms only. Not part of any pre-registered analysis; 4 copies per boss give no CIs.

## Result (`results/smoke.json`, `results/shadow.json`)

- **Switch off is unchanged:** production and g16mb equal §772's g16mb units copy for copy (20 / 20 copies each:
  won, exit HP, turns, decisions, simulations, potions), with the model loaded.
- **(a) Net as leaf:** HP lost per boss fight, g16mb+lq − g16mb: Hexaghost +25.0, Guardian +7.3, Automaton +9.7,
  Time Eater +13.6, Donu and Deca −0.5; **mean +11.0**. Production + leaf − production: +6.0 / +8.3 / +22.8 / +5.2 /
  +5.0, mean +9.5. Leaf fights last longer (Hexaghost 7-9 turns against 4-6). CPU per simulation 5.9x g16mb's on
  average (168-249 µs against 30-64 µs; 3.0-3.9 leaf values per forward pass, 0.8 ms per forward).
- **Diagnosis on real tree leaves** (shadow, 403,782 leaves of 3 bosses): within a parent the net's value follows the
  playouts (slope of playout on net 1.10, correlation 0.41 with single playouts, 74.5% of sibling pairs ordered like
  the playout). The level is off per fight: net − playout +4.3 (Hexaghost), +4.4 (Guardian), −8.6 (Automaton), +4.7
  for potion edges. Offline, the head compresses the gaps of rarely visited edges (edges with 1-3 visits: −18.6
  below the root's most visited edge against −59.8 in the search; 27% of unvisited edges above it), since training
  used edges with ≥ 64 visits only.
- **Level calibration** (first 64 leaves per search played out): no repair, g16mb+lq − g16mb +16.0 / +11.8 / +21.0
  (Hexaghost, Guardian, Automaton).
- **(b) Q-init** (K 64, M 16): g16mb+qinit − g16mb +1.2 / +5.2 / +3.0 / +3.2 / −0.8, **mean +2.4**, at 1.18x CPU
  (7.6k-12.9k forwards per boss over 4 copies); turns as g16mb.

## Interpretation (Inference)

- Good sibling order at played roots did not make a good leaf. Inside a tree every net leaf carries its parent's
  level error, the same at every visit and correlated across a subtree, while playout noise averages out; the
  search then misjudges which lines end the fight well and plays longer, worse fights. Removing the per-search
  offset does not help, so the error is not one constant per fight. The head also never saw targets for bad actions.
- Even a fixed leaf would cost about 6x per simulation at this forward speed, more than §774's 64k budget (3.8x,
  −1.13 HP in these bosses). As a cheap Q-init it neither helps nor costs much.
- What could still work, untested: a value trained on the states the search actually evaluates (tree nodes, with
  bad actions), a much cheaper forward, or AlphaGo-style mixing with the playout at equal CPU.

## Decision

NOT_SHOWN (smoke): neither the leaf nor the Q-init improves g16mb on five Baalorlord bosses; the leaf is clearly
worse. The fight gate is not run; the value-net leaf line is closed. Code stays default off (research switches
documented in `environment-variables.md`). No new seeds. Cost: about 6 core-hours on one 4-core cloud container.

## Files

- `run_unit.sh` (smoke unit script), `smoke_show.py`, `smoke_compare.py` (per-boss tables), `shadow_analyze.py`.
- `results/smoke.json` (every side per boss, reproduction check), `results/shadow.json`.
- Nets: `/mnt/project-files/combat-plan/value-leaf/v1/nets/V1_d64/` (`model.pt`, `V1_d64.ctn` sha256 4584901e…4e4c).
  Smoke fight records: `/mnt/project-files/combat-plan/value-leaf/v2/`.
