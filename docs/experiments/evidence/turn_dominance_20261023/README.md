# Turn-level enumeration with end-of-turn dominance: opportunity in Silver's real decisions (2026-10-23)

Thread "Turn-level action enumeration with dominance pruning". Philipp 2026-10-23 12:17Z asked whether a combat
search over whole turns (every way to play cards up to the next chance node, pruned by a dominance check) was ever
tried; 12:22Z "yes set up the cheap experiment, you can use 8 workers". Seeds from the coordinator (12:22Z):
111380000-111380999 for the experiment, 111389990-111389999 for smokes.

## Why

Only `exact_combat_solver` has it (§623, `turnValue`): every deterministic line of a turn is followed to its end
and an end-of-turn state is dropped when another one is at least as good in player block and every monster's HP,
block, Vulnerable and Weak and equal in everything else. It removed about two thirds of the end-of-turn candidates
there, and it is exact only in monotone fights (starter cards, Burning Blood, no potions, eight Act-1 monsters).
Silver has transpositions (`equalForSearch`), so different orders of the same plays already share a node, but no
dominance. Related negatives: §320 (an unconditional same-turn Bash/Strike rule is unsound), §328 (macro edges, no
wall-time gain), §106 (Searcher3 chain compression, -4.7 pp).

Turn-level pruning can only help Silver where Silver actually picks a root edge whose turn can only end in a
dominated state. This measures how often that happens in production play before anything is built into the search.

## What

`one_combat turndomgen N SIMS ASC SEED_OFFSET OUT.jsonl [MAX_EXECS] [MAX_SNAPSHOTS]`
(`apps/one_combat/turn_dominance.cpp`, research only, observation only). Plays whole runs as bestbench does
(`runFullRunOOC`). At every searched Silver root it follows, from each root edge, every line of the player's actions
to the end of the turn while the line is deterministic (no RNG stream advances: the search's own chance test). A
line ends where END_TURN is legal in a normal input state (an end-of-turn candidate) or the fight ends (a terminal
candidate, always kept). Candidates are grouped by the solver's end-of-turn projection without player HP and block;
in a group a candidate is dominated when another one has at least the player HP and block and at most every live
monster's HP and block and at least its Vulnerable and Weak, and is better in one of them. A root edge is
**closed** when all its lines are deterministic and stay in the turn, and **dominated** when it is closed and every
candidate it reaches is dominated. Roots whose enumeration exceeds `MAX_EXECS` = 200,000 action executions are
`capped` and not classified. Each row also records `gateSafe` (the solver's monotone gate) and Silver's visits and Q
per edge; the first 40 flagged (raw) roots per run carry a state snapshot (endgamerootgen format) for exact follow-up.

Configuration (`run_unit.sh`): A20, production Silver in combat (learned stop, exact root budgets, g7f_E root table
and root prior weight 400, tree prior K = 8, boss prior playouts), student_sel argmax out of combat (`STS_OOC_MCTS=0`,
as the silver-leaf campaigns), full runs to the Heart. One run per unit, 512 units, seeds 111380000-111380511,
queue schedule, 8 workers x 4 lanes.

The dominance is naive outside the gate (on-death effects, splits, HP-threshold moves, Reaper-style heals and similar
can make "less monster HP" worse). Flagged roots outside the gate are therefore an upper bound on the opportunity.

## Smoke (seeds 111389990-111389994, run_unit.sh as on a worker, v3 build of this commit's code)

| seed | end | searched roots | capped | raw flagged choices | material | enumeration / run wall |
|---|---|---|---|---|---|---|
| 111389990 | floor 16, act 1 boss lost | 217 | 0 | 3 | 0 | 0.13 s / 35 s |
| 111389993 | floor 21 | 272 | 0 | 4 | 0 | 0.17 s / 19 s |
| 111389994 | floor 56, act 4 | 1,069 | 3 | 9 | 2 | 4.3 s / 261 s |

(111389991 and 111389992 ran an earlier build without the material split; 111389990 was rerun.) Observation only:
`bestbench` on 111389990 with the same environment gives the same run (floor 16, act 1, 0 HP, death in combat 10).
Most raw flags are Silver ending the turn with energy and a playable Defend at near-tied Q while nothing attacks
(Lagavulin asleep, Sentries); the two material ones are End Turn instead of a Strike+ on a Looter (Exordium Thugs)
and Strike instead of Twin Strike on the same Darkling.

## Decision rule (pre-registered)

A dominated edge is **materially** dominated when every candidate it reaches is dominated by one that is better in a
field that can change the fight on its own: more player HP, a monster dead or with less HP or more Vulnerable or
Weak, or more block while the dominated candidate's block is below the public incoming attack damage. Extra block
the enemy cannot use and less monster block do not count (the smoke showed most raw flags are End Turn with an
unneeded Defend in hand, at near-tied Silver Q).

Headline: the share of classified (`ok`) searched roots where Silver's chosen root edge is materially dominated,
with a seed-clustered bootstrap 95% interval.

- **< 1%: DROP.** Turn-level dominance pruning has no real target in Silver's play; record the negative result.
- **>= 1%: INSPECT.** Solve a sample of the flagged roots (snapshots in the rows) with `exact_combat_solver roots`
  or check them by hand for soundness before proposing any search change (a separate go from Philipp).

Descriptive: the same share by room, act and the monotone gate; the raw (any-field) dominated share; how many roots
have any dominated edge; Silver's visit share on dominated edges; Silver's own Q gap at flagged roots; how many roots
are closed; enumeration cost.

## Analysis

```
python3 tools/cloud/verify_campaign.py docs/experiments/evidence/turn_dominance_20261023 --extract $HOME/turn-dominance-units
python3 docs/experiments/evidence/turn_dominance_20261023/analyze.py $HOME/turn-dominance-units result.json
```
