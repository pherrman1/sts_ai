# Infinite-combo frequency, Stage 0 (issue #1054)

Question (Philipp, issue #1054, 2026-11-15): how often do same-turn infinites occur in our runs, by act and
room, and does the played search miss them? Stages 1-2 (Silver proven win, PPO auxiliary head) only if certified
infinites or candidates occur in at least about 5% of runs or explain a measurable share of Heart losses.

Status: **pilot done (8 seeds)**; the sample size of the main replay is Philipp's call. Descriptive, no gate,
no default change.

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

## Limits

- Same-turn card cycles only: no potions, no cross-turn engines (e.g. Feel No Pain block engines that win over
  several turns), no ordinary non-repeating lethal (recorded separately as `dfs_victory_depth`).
- Bounded DFS (24 actions, 20,000 nodes per state); the turn-start state only (mid-turn draws are inside the
  DFS since the state is concrete).
- Concrete state: the oracle knows the draw order; "missed" is relative to a clairvoyant check, the search
  plays fair (ADR-0002).
- The certificate is a simulator fact for that state; Stage 1 would need an information-set version.
