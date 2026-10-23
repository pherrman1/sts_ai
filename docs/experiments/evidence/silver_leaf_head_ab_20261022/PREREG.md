# A/B: learned leaf head, capped at win-now, vs production Silver (A20, fight level)

Status: written before any result of this A/B; the pre-launch review is pending. Step 3 ("fight level") of the
leaf-value plan (doc "Leaf evaluation for Silver", https://claude.ai/artifact/P8536tUChd5XLo1gV6kfbu). Philipp allowed
up to 32 workers for steps 2-4 (2026-10-22 17:08Z). The coordinator assigned seeds 111350000-111350255 and 8 workers
(2026-10-22 23:14Z) and may add workers when the value-level A/B finishes. Smoke sources 111339997-999 (this thread's
block). Thread "Exact combat solving research".

## Background

- **The head.** silver-leaf-a20 (`../silver_leaf_a20_data_20261022`): 128-64-1 on the frozen g7f_E trunk, trained on
  736k A20 self-play roots labeled with the score their fight ended with. Half head, half playout, with the head's
  value lowered by 1 point per turn the leaf lies beyond the root, passed the exact first-fight test
  (`../leaf_head_turn_penalty_20261022/RESULT.md`): regret change against the playout -0.251 ± 0.054 per fight (prod)
  and -0.283 ± 0.048 (max backup) on 300 fresh fights, about what a perfect leaf gains there.
- **The uncapped head fails at fight level.** Its smoke in this harness (sources 111339997-999) found Act-2/3 fights in
  which search with the head stops finishing the fight: off the states it was trained on, the head values a fight
  above any ending it has left. Four traced fights (production vs head, HP after the two redraws): Centurion + Mystic
  67/67 vs 14/18 (against the lone Mystic stacking Strength the head's value rose from 145 to 178), Collector 75/50 vs
  24/1 (turns ended with full energy), Slavers 55/55 vs 55/41, and Darklings, an 84-turn fight. On source 111339999
  the head took 1,146 decisions against production's 613 over the same 15 fights.
- **The guard.** `STS_SILVER_LEAF_HEAD_WIN_CAP=1` (commit 0bbc9fdb) caps the head at the leaf's win-now value (Silver's
  victory score if the fight ended at the leaf: its HP, potions and turn; `SilverSearcher::winNowValue`) before the
  turn penalty. Only value the fight can still gain lies above it: healing, Feed, gold. In the step-1b data 12% of
  the roots ended above their win-now value (median 8.6 points; the most common gain, 3-4 HP, is probably Feed's),
  so the cap also removes some real value from the head's half of the leaf. With the cap the four fights end at
  68/67, 75/59, 55/55 and 40/52 HP (production 67/67, 75/50, 55/55, 46/35), the Darklings fight in 7 turns. On the
  exact first fights the capped head keeps about 60% of the gain: -0.149 ± 0.054 (prod) and -0.174 ± 0.050 (max
  backup) on the same 300 fresh fights.
- **The other guard lost.** A shortfall head (`../silver_leaf_head_shortfall_20261023`), which predicts how far below
  win-now a fight ends, fits better offline but lost the pre-registered first-fight comparison with the capped head
  (-0.068 and -0.094), so the capped head is the candidate.
- §638: a change that halved the first-fight regret lost HP on bosses at fight level. This A/B asks whether the capped
  head's gain carries over to whole-run fights (later decks, elites, bosses).

## Candidate

`STS_SILVER_LEAF_HEAD` (commit 824c58d2; the faster forward with the same values, 2060cf46; the cap, 0bbc9fdb): an
undecided leaf is worth 0.5 x (min(head, win-now) - 1 x (leaf turn - root turn)) + 0.5 x playout. Head `a20.txt`
(sha256 049d08a2232a396e19cad0a9c2b69eadcd9eb2ee5e4cf80e597a34b952d12e61), trunk g7f_E (c45dcc0a...). Campaign code
75afdee0 (it adds shortfall heads, unused here: `a20.txt` ends at its offset), binary `83de6c12...` (preset
linux-gcc-release-x86-64-v3).

## Design

- **Harness.** `one_combat ctmsilvergen` at Ascension 20, armset `leafhead` (commits 824c58d2, a7726af9, 0bbc9fdb),
  the §541 harness exactly as `../silver_maxbackup_ab_20261022`: source runs from student C (`eff2f74f...`) with the
  g7f_E root prior (`c45dcc0a...`) at weight 400 and the ADR-0046 root table, every 3rd hallway fight replayed,
  R = 2 combat-RNG redraws (the same redraw seeds in every arm), keys off (runs stop after Act 3 unless the source
  collects Act 4 by itself), no OOC MCTS and so no imagined fights.
- **Arms.** All use the root prior and the tree prior (K = 8) under a rollout override that plays production's prior
  playouts in boss rooms (ADR-0050, boss only by ADR-0056) and greedy playouts elsewhere; flat exact budgets, no
  learned stop (it was trained on trees without the head; the plan judges the leaf apart from the stop). Bosses are
  compared with production, as the plan asks.
  - `base10000`: production Silver, 10,000 simulations.
  - `base12000`, `base15000`: the same at 12,000 and 15,000, the CPU-matched control candidates.
  - `head10000`: the candidate, 10,000 simulations.
- **Env** (`run_unit.sh`): `STS_CTMSILVER_ARMSET=leafhead`, `STS_CTMSILVER_SWEEP_SIMS=10000,12000,15000`,
  `STS_CTMSILVER_HEAD_SIMS=10000`, `STS_CTMSILVER_HALLWAY_EVERY=3`, `STS_CTMSILVER_LEAF_HEAD=$RUN/a20.txt`,
  `_TRUNK=models/combat_policy_mlp_g7f_E.txt`, `_BLEND=0.5`, `_TURN_PENALTY=1`, `_WIN_CAP=1`; otherwise as
  `../silver_maxbackup_ab_20261022/run_unit.sh`. The smoke used exactly this environment.
- **Campaign.** 256 units, one source seed each (111350000-111350255), `campaign.manifest`: queue schedule, 4 lanes
  per worker, `workers 32` (Philipp's limit; the coordinator starts 8 and may add more, which changes only the wall
  time).
- **Smoke and CPU check** (sources 111339997-999, this environment; binary `977a9c99...` built from 0bbc9fdb's
  code, and the frozen binary reproduces source 111339998's arms, samples and states exactly, CPU times apart). All
  three sources finished with rc 0: 50 valid replayed fights (18 normal, 19 elite, 10 boss, 3 other; 2 in Act 4), no
  invalid arm rows, no escapes. CPU per fight: head10000/base10000 1.108 (per simulation 1.055), head10000/base12000
  0.919, head10000/base15000 0.732, so base12000 would be the matched arm. No stall: no fight in which head10000
  took more than twice base10000's decisions (52.96 against 50.44 decisions per fight). Descriptive only, three
  sources: score head10000 - base10000 -0.77 points per fight, HP lost -0.39. Source wall times 6, 27 and 67 minutes
  (the last reached the Heart), three sources at once on 4 cores. Files: `smoke/analysis.json` (this `analyze.py`),
  `smoke/fights.txt`; raw rows `/mnt/project-files/silver-leaf-head-ab/smoke/smoke_raw.tgz` (sha256 243a64a0...).
- **Expected cost.** About 111 CPU-seconds per replayed fight over all arms (bosses with prior playouts cost the
  most) and about 17 fights per source: about 33 minutes per source, about 140 lane-hours for 256 sources, so about
  5 hours on 8 workers (4 lanes each) or 1.5 hours on 32.

## Analysis and decision rule

`analyze.py` on the extracted unit tars: the maxbackup analyzer with these arms, plus act subsets, decisions per fight
and a stall count (fights where `head10000` takes more than twice the decisions of `base10000`), all descriptive. Per
arm: fight score (0 on death, else 53 + HP + 11 x potions + 0.25 x gold + 2 x max HP), win, HP lost, CPU per fight and
per simulation. Paired contrasts per fight, 95% bootstrap over source seeds, for all, boss, elite, normal and Act 1-4
fights. A fight counts only if every arm row is valid and every arm has both redraws.

**Primary label: `head10000 - base10000`, all fights.**
- Score: BETTER if the CI lower bound > 0, WORSE if the upper bound < 0, else NOT_SHOWN.
- HP lost: BETTER if the CI upper bound < 0, WORSE if the lower bound > 0, else NOT_SHOWN.

**Secondary label: `head10000 - matched`**, same rule. `matched` is the smaller of `base12000` and `base15000` whose
seed-pooled per-fight CPU ratio head10000/base (point estimate) is <= 1.10, chosen by CPU alone; if neither is, both
secondary labels read NOT_MATCHED and support no claim.

**Step-3 gate** (the plan's bar; it decides only whether a whole-run A/B is proposed to Philipp): the
`head10000 - matched` score contrast over all fights has a CI lower bound above -1, and on boss fights neither its
score nor its HP-lost contrast is WORSE. NOT_MATCHED fails the gate. `analyze.py` computes it. Everything else is
descriptive.

Power: the maxbackup A/B (64 sources, same harness) had 95% half-widths of about 2.7 points (score) and 0.5 HP (HP
lost) over all fights; 256 sources should give about 1.4 and 0.25. The gate then passes when the point estimate is
above about +0.4 points per fight: a neutral head will usually fail it, which is intended, since step 4 costs about
900 core-hours.

No default change. A whole-run A/B needs Philipp's typed go and a worker count.
