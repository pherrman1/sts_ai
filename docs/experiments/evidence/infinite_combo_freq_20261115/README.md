# Infinite-combo frequency, Stage 0 (issue #1054)

Question (Philipp, issue #1054, 2026-11-15): how often do same-turn infinites occur in our runs, by act and
room, and does the played search miss them? Stages 1-2 (Silver proven win, PPO auxiliary head) only if certified
infinites or candidates occur in at least about 5% of runs or explain a measurable share of Heart losses.

Status: **done (128 seeds, 2026-11-16).** Result: 1 of 128 runs has a certified same-turn infinite (0.8%,
Wilson 95% [0.1%, 4.3%]), 2 of 128 a certified infinite or a candidate (1.6%, [0.4%, 5.5%]); the played search
won every fight with a certificate, a candidate or a turn of 25+ cards; no lost fight and no Heart fight shows a
damaging loop (one Heart turn is a STALL_LOOP, a repeat without damage; that fight was won). **No go for stages 1-2.** Descriptive, no gate, no default change.

## Design

- **States.** Replays of §775's G16 + mb4 games (Gumbel root k 16, max backup 4, 16k simulations in every fight;
  net-0420 out of combat, A20), seeds from the §775 block 111378256-111379279 only (no new seeds). Same
  environment as `gumbel_wholerun_20261108/run_unit.sh` (see `run_seed.sh`), plus the new read-only research
  observer `STS_COMBAT_STATE_CAPTURE` (`apps/one_combat/run_driver.cpp`): at each player turn's first
  PLAYER_NORMAL decision of every real fight it writes the concrete `BattleContext` as a BattleContextBinary
  snapshot, and per fight a row with outcome, turns, HP and cards played per turn. It uses the existing
  `g_onCombatDecision` hook around the real fight only.
- **Run binary.** Run commit `647dba50` = §775's code `5665d5ae` + the observer (main's search code has moved
  since), preset `linux-gcc-release-x86-64-v3` as §775, `one_combat` sha256 `5191d1d6d9ae05eb…` (in the share's
  bin-cache). A game counts only if its BEST line and its `[silver] whole-run Gumbel roots=… sims=…` line equal
  §775's (`analyze.py OUT REF`).
- **Oracle.** `combat_infinity_oracle --snapshots FILE natural 20000` (this PR; `apps/combat_infinity_oracle.cpp`).
  §671's v0 oracle cannot fire on natural states: its cycle key keeps the shuffle RNG exact (only a two-card
  Dropkick/Flash deck without relics, powers or exhaust pile is quotiented), plus HP, block, Pen Nib / Nunchaku /
  Ink Bottle counters, Kunai / Shuriken attack counts and Strength / Dexterity, so every natural loop's state
  differs from period to period. The natural mode:
  - coarsens only the **candidate** key: no RNG streams, hand as a multiset (`equalForSearch`), player HP, block
    and HP-loss counters, periodic relic counters, Strength, Dexterity, monster block and a positive Invincible
    cap are progress, not identity. Energy, ordered draw/discard piles, exhaust pile, powers, intents and every
    other field stay exact;
  - **certifies** only by replaying the witness on the untouched turn-start state with the real RNG and normal
    legality (each step must be the same physical card and target), up to an actual same-turn
    `PLAYER_VICTORY` with HP > 0 (CERTIFIED_KILL), or until every living monster's Invincible is exhausted
    (CERTIFIED_TURN_CAP, the Heart's 200 per turn). No damage extrapolation, so the coarser key cannot create a
    false certificate;
  - enumerates card selections (Headbutt, True Grit+, Burning Pact …) as DFS steps; after a period breaks
    because a monster died or changed phase, searches afresh from the replay's real state (up to 4 times);
  - prunes exact-state transpositions (64-bit hash of the v0 control state's snapshot; a collision can only
    lose recall); records the DFS's own ordinary lethal (`dfs_victory_depth`).
  - Same domain gate as v0: Ironclad, red / colorless / curse cards, no Prismatic Shard (from the run's own
    RelicContainer), concrete draw pile, visible intents. Potions and End Turn are never played.
- **Recall check ("plant").** `--snapshots FILE plant`: each real turn-start state keeps its relics, powers,
  monsters and exhaust pile, but its card zones become the fixtures' Dropkick loop (two Dropkicks in hand,
  empty draw and discard, energy >= 1, every living monster Vulnerable 3). States where the DFS kills before
  any recurrence (low enemy HP) are excluded. What the natural key misses there it would also miss in a real
  thinned deck of that run.
- Fixtures (`--fixtures`, ctest `combat_infinity_oracle`): all 13 v0 verdicts unchanged; new natural cases:
  Dropkick loop with a relic and an exhausted card (v0 NONE, natural CERTIFIED_KILL), without Vulnerable (NONE),
  with Kunai + Pen Nib (v0 NONE, natural CERTIFIED_KILL), two monsters (kill via continuation), a Heart-like
  Invincible 200 cap (CERTIFIED_TURN_CAP), Beat of Death with 8 HP (candidate, replay ends in player death) and
  with 80 HP (CERTIFIED_KILL).

## Analysis (`analyze.py`)

Per run: any certified turn / any candidate turn; by room class (hallway, elite, boss, Shield and Spear,
Heart); Heart kills with vs without a certified turn (descriptive, confounded by deck strength); missed
certified kills (fight not won on that turn, or HP lost after it); oracle CPU and bound hits; proxies: fights
with a turn of >= 25 cards played, fights at the turn cap (>= 99) or aborted, decks with known enablers
(Dropkick + a Vulnerable source, Corruption + Dead Branch, Corruption + Feel No Pain + Dark Embrace,
Unceasing Top). Run-share intervals are Wilson 95%.

## Pilot (seeds 111378256-111378263, 2026-11-15)

- 8 of 8 games reproduce §775 exactly (BEST line and Gumbel roots/sims); 192 fights, 1,012 turn-start states,
  all inside the oracle's domain.
- **0 runs with a certified infinite, 0 with a candidate** (0 STALL_LOOP either). No fight with a turn of
  >= 25 cards (maximum 15); no fight at the turn or action cap. One run has a Dropkick deck with a Vulnerable
  source.
- Oracle (natural, 20,000 nodes, Release, shared 4-core container): 25 ms mean, 1.3 ms median, 255 ms p99,
  313 ms max per state; 3.2 CPU-s per run (a G16 run takes about 500 CPU-s); node cap hit in 77 of 1,012
  states (7.6%), depth cap never.
- Plant recall: 511 of 576 eligible planted loops certified (88.7%; 436 states excluded as DFS lethal before
  recurrence). Misses: Awakened One 24 (phase 1 cannot die for good in the same turn), The Guardian 9 (Sharp
  Hide damage / mode shift), Heart 6 (14 CERTIFIED_TURN_CAP, 1 kill), Time Eater 5 (Time Warp), Transient 5,
  Snake Plant 4, Snecko 4, others 1-3. `pilot/plant_recall.json`.
- Raw data: `/mnt/project-files/infinite-combo-freq/pilot/` (logs, snapshots, oracle rows); here
  `pilot/analysis.json`, `pilot/plant_recall.json`, the `.done` files.

**Reading (Inference):** 8 runs cannot bound the share below 5% (Wilson upper limit 32%). The pilot only shows
that the pipeline reproduces §775, that the oracle can see natural loops in these runs' contexts, and that it
is cheap.

## Main run (seeds 111378256-111378383, 2026-11-15/16)

Philipp's choice on the sample-size card (2026-11-16 00:33 CET): 128 seeds, local container, no workers. 4 lanes,
21.5 lane-hours of game time plus reruns of games cut by two container restarts (`run_seed.sh` skips finished
seeds and reruns unfinished ones). Raw data `/mnt/project-files/infinite-combo-freq/main128/` (`out.tar.gz`, `deep.tar.gz`);
here `main128/analysis.json`, `main128/deep_caps.json` and the `.done` files.

- **Reproduction:** 128 of 128 games equal §775's BEST line and Gumbel roots/sims line; none dropped. 2,973 real
  fights, 15,261 turn-start states, all inside the oracle's domain.
- **Runs with a certified infinite: 1 / 128 = 0.8%** (Wilson 95% [0.14%, 4.29%]). **Certified or candidate:
  2 / 128 = 1.6%** ([0.43%, 5.52%]).

| room class | fights | runs reaching | runs certified | runs candidate |
|---|---:|---:|---:|---:|
| hallway (acts 1-3) | 1,664 | 128 | 0 | 1 |
| elite (acts 1-3) | 770 | 128 | 0 | 0 |
| boss (acts 1-3) | 336 | 114 | 1 | 0 |
| Shield and Spear | 60 | 60 | 0 | 0 |
| Heart | 60 | 60 | 0 | 0 |
| event fights | 83 | 64 | 0 | 0 |

- **The certificate:** seed 111378328, act 2 boss The Champ, turn 2 (third turn), 49 HP: Sundial + Pommel Strike /
  Pommel Strike+ in a 19-card deck. After 16 setup actions a two-card cycle (−29 Champ HP per cycle, energy ±0) kills
  after 10 repetitions, 19 replayed actions, CERTIFIED_KILL. **The search played it as well:** the real game played
  21 cards in that turn and won the fight on it (13 HP lost in that turn; the oracle's line loses none, so
  `missed_certified_kills` lists it as `hp_cost_only`, not as a miss of the kill). The run then died on floor 41.
- **The candidate:** seed 111378341, act 3 hallway Maw, turn 1: Shrug It Off+ / Pommel Strike+ cycle (−15 HP per
  cycle) in a 34-card Sundial deck with Dark Embrace ×2; the replay ends with `control_state_changed`, the continuation search stays a candidate. The game won that fight in its next turn with 25
  cards. Both hits are Sundial decks: 14 runs have Sundial, 9 Sundial + Pommel Strike.
- **Heart:** 60 runs reached it, 48 killed (80%); no Heart fight has a certified or candidate turn, so infinites
  explain none of the 12 Heart losses. One Heart turn is a STALL_LOOP (seed 111378381, turn 6, 17 HP: a repeated
  state without damage, not an infinite); that fight was won. It is the only non-NONE verdict besides the two hits. Killed with vs without a certificate: 0/0 vs 48/60.
- **Missed infinites:** none in the sense of a fight not won on that turn. Of the 80 lost fights (one per lost run:
  act 1-3 bosses 33, Heart 12, elites 26, hallway 8, event 1), none has a non-NONE verdict; their largest turn has 20
  cards; 27 of them have at least one node-capped state.
- **Proxies:** 18 fights in 11 runs (8.6%) have a turn with ≥ 25 cards played (max 41, Shield and Spear); all 18
  were won. No fight reached the turn or action cap. Enabler decks (runs): Dropkick + Vulnerable source 11,
  Corruption + Feel No Pain + Dark Embrace 24, Corruption + Dead Branch 3, Unceasing Top 13.
- **Oracle cost and bounds (20,000 nodes, depth 24):** 33 ms mean, 1.7 ms median, 265 ms p99, 419 ms max per state;
  4.0 CPU-s per run (G16 run ≈ 500 CPU-s). Node cap hit in 1,728 states (11.3%), depth cap in 101 (0.7%). On all 18
  ≥ 25-card turns the oracle is node-capped; re-run at 2,000,000 nodes and depth 64 (`main128/deep_caps.json`,
  5-28 s each) all 18 stay NONE and 17 stay node-capped: these turns are long finite draw/exhaust chains (DFS
  lethal depth up to 39) that a bounded DFS cannot exhaust, so for them NONE means "not found", not "absent".

**Reading (Inference):** same-turn infinites are rare in G16 + mb4 runs (point estimate under 1% of runs, upper 95%
limit 4.3% for certified ones) and the search already plays the one it meets. The capped big turns could hide a few
more, but all of them were won, so a proven-win shortcut (stage 1) or an infinite head (stage 2) could only save CPU
or HP there, not fights. The losses (bosses, elites, Heart) show no loop at all. Measured against the issue's
threshold (≥ 5% of runs, or a share of Heart losses) stages 1-2 are **not justified**; the cheap oracle could be
re-run on a later, stronger policy whose decks lean more on Sundial / draw engines.

## Limits

- Same-turn card cycles only: no potions, no cross-turn engines (e.g. Feel No Pain block engines that win over
  several turns), no ordinary non-repeating lethal (recorded separately as `dfs_victory_depth`).
- Bounded DFS (24 actions, 20,000 nodes per state); the turn-start state only (mid-turn draws are inside the
  DFS since the state is concrete).
- Concrete state: the oracle knows the draw order; "missed" is relative to a clairvoyant check, the search
  plays fair (ADR-0002).
- The certificate is a simulator fact for that state; Stage 1 would need an information-set version.
