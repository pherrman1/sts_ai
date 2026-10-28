# Native Silver search shape by encounter (#888)

Measurement only. No search policy, rollout, cap or budget changed.

## Question

How far ahead does today's A20 native Silver combat search look, separately in the tree and in the rollouts, how
many next-turn futures does it see at its first End Turn, how does the tree grow, and how big is it, per encounter?

## Setup

- Code: base `ed2dcb2b` (main) + this PR's opt-in diagnostics (`STS_SILVER_TREE_PROFILE` `search` block,
  `STS_SILVER_TREE_PROFILE_SCOPE=real`). Release preset `linux-gcc-release-x86-64-v3`, binary SHA-256
  `3509542a5665661094f7c292a18d9c187ad60e3ea6ac798d5afe72cfe7acb2cf`.
- Roots: every real combat decision of 4 already played A20 games, arm A (today's A20 default) of
  `expert_anchored_student_ab_20261026`, seeds 111384000–111384003 (used seeds, no new seeds). Same environment as that
  campaign's `run_unit.sh` arm A ([run_game.sh](run_game.sh)): learned Silver stop (checkpoints 250…10,000, exact root
  budgets), Act-4 strong (Shield and Spear 10k, Heart 40k with reuse cap 262,144), g7f_E root prior and rollout table,
  tree prior K=8, boss prior playouts, 32,768-node reuse cap. `heartoutcomegen 1 <seed>` through `tools/seed_guard.sh`,
  `OMP_NUM_THREADS=1`, 4 games in parallel on a 4-CPU cloud container.
- Sample: 89 fights, 48 encounters, 1,939 searched decisions (no singleton skips under exact root budgets). Acts 1–4,
  hallway/elite/boss/event; seed 111384003 kills the Heart, the other three die on floors 51, 23, 33.
- Imagined OOC fights are left out (`SCOPE=real`).

**Checks.** All 4 games end exactly as recorded in the campaign (floor, HP, Heart, decision counts). Seed 111384001
played three times with this binary (profile off, on, on): game rows and CTM rows byte-identical except timing fields;
the two profiled runs give identical tree rows except CPU/wall time. Wall 633 s off vs 640 s on. Compared with the
campaign's own rows (binary `5d9ac015…`, run commit `d9aa44fa`), a few OOC MCTS root Q/visit numbers differ (3–6 rows
per game) with the same chosen actions; this comes from main's changes since then, not from the profile (the profile
on/off runs on one binary match exactly). Unit fixtures `test silver_searcher` and `test silver_rollout_limit` PASS
(they include profile on/off play parity and counter accounting).

## Definitions

- **Action**: one edge of a decision node (card play, potion, card select, End Turn). Chance-outcome edges add none.
- **Round**: one step of `BattleContext::turn` (the player turn plus the enemy turn after it). Tree rounds = turn of
  the tree leaf − root turn; rollout rounds = turn at the playout's end − leaf turn; total = sum.
- **Tree leaf**: where the descent stops (a node created in this simulation and rolled out, an already visited
  terminal node, a cycle, the 5,000-step backstop). Per-simulation numbers count only this decision's new simulations.
- **Most-visited line (PV)**: from the root, the most-visited action edge, through chance nodes by their most-visited
  outcome. "PV rounds at 10%" = round depth of the deepest PV step whose edge still has ≥ max(10, 10% of root visits).
- **First End Turn**: an End Turn edge reachable from the root without another End Turn (draw chance nodes inside the
  turn are followed through all outcomes). The one on the PV is reported; "first End Turn nodes reached" counts all
  distinct ones (different player lines are never pooled). Distinct outcome nodes = `equalForSearch` (RNG streams
  ignored); public states = a projection (HP, block, energy, powers flags, monster HP/block/moves/powers, hand
  multiset, pile sizes); RNG draws = outcomes executed.
- **Caps in force**: rollout action cap 1,000; zero-cost cap 50; descent backstop 5,000 steps; no tree depth cap.
  End Turn widening cap = ⌈3.7028·(n+1)^0.52389⌉ (≈ 200 at 2,000 visits, ≈ 450 at 10,000); at the cap the search
  re-picks an existing outcome with probability proportional to its visits.

Full per-encounter tables (48 rows): [tables.md](tables.md); numbers: [summary.json](summary.json).
Raw rows: `/mnt/project-files/silver-tree-shape-888/` (`A-<seed>.tree.jsonl.gz`, SHA-256 `b86facf2…` / `26833ad7…` /
`e67636a7…` / `84d831af…` for seeds 000–003, plus game/CTM rows and `.env`).

## Results

### 1. Explicit tree depth is about one round everywhere

Encounter-weighted (median over the 48 encounters of each encounter's pooled median):

| per simulation | median | p90 over encounters |
|---|---:|---:|
| tree actions | 4 | 5 |
| tree rounds | 1 | 1 |
| rollout rounds | 1 | 2 |
| total rounds | 2 | 3 |
| PV rounds at 10% root visits (per-decision median) | 0 | 1 |

Within encounters the tree p90 is 1–3 rounds and the max 2–5. The PV keeps ≥10% of the root's visits only inside the
current turn (median 0 rounds, max 1–2); with ≥10 visits it reaches round 1 (max 1–3). Rollout actions are ~70% of
all simulated actions (median over encounters).

### 2. Shallow tree, long rollouts: bosses and Act-3 elites

Encounters whose total horizon p90 is ≥ 6 rounds while the tree stays at median 1 (p90 1–2) round:

| encounter | tree rounds med/p90 | total rounds med/p90 | rollout share of actions | sims/decision (median) | CPU s/decision (median) |
|---|---|---|---:|---:|---:|
| Time Eater | 1 / 1 | 5 / 9 | 0.88 | 4,000 | 0.81 |
| Champ | 1 / 1 | 4 / 8 | 0.85 | 8,000 | 0.79 |
| Nemesis | 1 / 2 | 3 / 8 | 0.82 | 4,000 | 0.12 |
| Donu and Deca | 1 / 1 | 2 / 7 | 0.88 | 10,000 | 1.91 |
| The Guardian | 2 / 2 | 4 / 7 | 0.70 | 2,000 | 0.13 |
| The Heart | 1 / 2 | 3 / 7 | 0.84 | 40,000 | 8.19 |
| Three Sentries | 1 / 2 | 3 / 7 | 0.67 | 4,000 | 0.10 |
| Collector, Giant Head, Hexaghost, Slime Boss, Mysterious Sphere | 1–2 / 1–2 | 2–4 / 6 | 0.65–0.83 | | |

Hallway fights of Act 1 (Cultist, Jaw Worm, Small Slimes, Louses) end within 2–3 rounds, so the tree's one to two rounds
cover most of the fight there; that is where terminal revisits are highest (see 4).

Example, the Heart at its first decision (40,000 sims, 21 CPU s): the PV holds 36,158 → 5,733 → 3,716 → 131 visits on
the first four card plays and reaches its End Turn with 1 visit; 3,861 distinct first End Turn nodes were reached.
At decision 10 the PV's End Turn has 708 visits and 116 outcome nodes (at the cap, effective 37).

### 3. First End Turn chance coverage

Per encounter, per-decision medians of the PV's first End Turn (full table in tables.md): visits 4–16,000 (typ.
1,000–5,000), distinct outcome nodes typ. 50–250 (encounter median of medians 72), public states 58, RNG draws typ.
200–4,000. The search reaches many first End Turn nodes (median 6–2,245 per decision; bosses and multi-enemy fights
hundreds), and the top one gets a median 5–81% of all End Turn visits; in bosses typically ~10%.

Two regimes (PV End Turn nodes with ≥ 20 outcomes, all decisions):

| | nodes | outcomes (median) | visits (median) | fresh RNG draws / visit | effective children / outcomes |
|---|---:|---:|---:|---:|---:|
| at the widening cap | 667 | 239 | 2,841 | 0.09 | 0.165 |
| below the cap (outcome space smaller than the cap) | 360 | 56.5 | 1,936 | 0.85 | 0.80 |

- **Widening-limited (most mid/late-game fights):** outcomes ≈ cap, each new visit re-picks an old outcome ~91% of the
  time in proportion to its visits. The resulting visit distribution is concentrated: ~40 effective outcomes out of
  ~240 (largest child 7–10%). Concentration on early-drawn outcomes is what proportional re-picking does; whether it
  matters for decisions is not measured here.
- **Small outcome space (starter decks, Act 1 hallway):** almost every visit is a fresh RNG draw that lands on an
  existing node (sibling reuse), so visits follow the outcome probabilities. Cultist: ~21 outcome nodes but 8 public
  states.
- **Outcome nodes vs public states:** `equalForSearch` keeps physical card identity, so two draws of different copies of
  the same card are different nodes. A fixture (A0 Jaw Worm / Cultist / Gremlin Nob, turn 1 End Turn, 4,000 sims; local,
  not committed) found every pair of outcome nodes with equal player, monsters and hand-by-card differ only in hand
  unique ids and draw pile. Public/outcome ratio is 0.3–0.4 in starter-deck fights (Jaw Worm 30/105, Small Slimes
  8/36, Three Sentries 41/133) and ~1 in multi-enemy and late fights. A unique-id chance merge was screened and rejected
  in 2026-09 (`silver_uid_chance_merge_20260919`, A0 hard64: no node or time saving).
- Deterministic End Turns (no draw or monster randomness) appear as single-outcome entries (`stochastic=false`).
- Chance transpositions exist (outcome nodes are deduplicated globally by `equalForSearch`); widening draws that hit an
  existing sibling are counted as `widening_sibling_repeats`, hits elsewhere as `widening_transpositions`.

### 4. Node growth and zero-growth simulations

Nodes created per simulation (median per decision): 0.6–1.4 (encounter median 1.2). Share of simulations creating
0 / 1 / 2+ nodes: e.g. Gremlin Nob 0.38 / 0.47 / 0.15, Champ 0.06 / 0.60 / 0.34, Heart 0.06 / 0.57 / 0.37. Two nodes
= a new chance node plus its first outcome. Every zero-growth simulation was a **terminal revisit** (cycle, depth-bound
and no-action stops: 0 in all 1,939 decisions). Terminal revisits are 4–6% in bosses and 30–41% in short Act-1 fights
(Book of Stabbing 41%, Gremlin Nob 38%). A terminal node's value is the deterministic terminal evaluation of a fixed
state, so a revisit adds the same exact value again and costs no rollout; it still uses a simulation of the budget.
Whether that is waste depends on UCB still needing those visits to separate siblings; not measured.

### 5. Tree size at the end of each search

| | median of encounter medians | range of encounter medians |
|---|---:|---:|
| allocated nodes at end | 16,222 | 5,931 (Gremlin Nob) – 27,392 (Shield and Spear); Heart 175,585 |
| reused at start (allocated before the search) | | 2,742 – 21,325; Heart 125,852 |
| created in the search | | ~1.2 × simulations |
| reachable from the root | about 50% of allocated | 21% – 100% (ratio of medians) |

Allocated nodes include unreachable nodes of earlier roots, kept until the next reroot finds the pool above the 32,768
cap (Heart: 262,144) and compacts. The older `nodes` row field is `allNodes.size()`, the pool's high-water mark, which
also counts nodes freed by `setRoot`; use `allocated_nodes` (pool in use). Per-type split of reachable nodes is in the
table (decision nodes, chance nodes, outcome edges).

## Interpretation

- Silver's explicit planning horizon at today's budgets is the current player turn plus the enemy's reply (median one
  round, PV confidence only within the current turn). Everything beyond comes from greedy/prior playouts.
- **Inference:** the clearest depth limitation is in long boss fights and Act-3 elites (Time Eater, Champ, Donu and
  Deca, Heart, Nemesis), where 80–88% of simulated actions are rollout actions and the tree stays at one round while
  the fights last 5–9+ more rounds. In the Heart's first turns the root's action branching alone absorbs 40,000
  simulations before the first End Turn.
- **Inference:** at widening-capped End Turns the search sees a few hundred distinct next-turn states but its effort is
  concentrated on ~40 of them by proportional re-picking.

Possible separate experiments (not run, each would need its own pre-registration): (a) chance re-picking that follows
the outcome distribution (fresh draw or uniform over sampled outcomes) instead of visit-proportional; (b) more tree
depth in boss fights via a value leaf or turn-level macro actions instead of more simulations; (c) a cheaper terminal
revisit (no simulation charge) in short fights.

## Limitations

4 games, one policy; per-encounter samples are 1–6 fights, so encounter rows describe these fights, not the encounter
in general. Decisions inside a fight share a reused tree (graph reads include inherited visits; per-simulation counters
do not). The public projection omits hidden intent damage and card unique ids by design; it may merge states that
differ in fields not listed (e.g. monster misc info). CPU seconds per decision include the profile's own graph reads at each learned-stop checkpoint (whole game +1% wall on seed 111384001), so they slightly overstate production cost. PV and End Turn reads are at the end of the search; checkpoint
reads (`checkpoints`) exist for learned-stop roots but are not summarized here.
