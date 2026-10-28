# Matched expert-entry fight replay: Silver vs Baalorlord on the expert's own fight states (pre-registration)

Status: DRAFT, to be frozen after review and before launch. Philipp asked for the run on 2026-10-28 ("Yes replay the
fights", reply to the #890 follow-up); worker count and launch timing are his.

## Question

§701 (#890): the bot loses more HP than Baalorlord in every elite and boss fight, also at matched entry HP and deck
size, and with near-starter decks, but existing logs cannot hold the deck and relics fixed. On the expert's own
combat-entry states (his deck, relics, path, HP and max HP), does today's Silver lose more HP than he did?

## Design

- Seeds: the 329 vanilla-RNG Baalorlord Ironclad A20 runs of §694 (`../expert_replay_ab_20261027/units.txt`); the run
  files are the frozen `expert_runs.tar` (share `expert-replay/`, sha256 in `campaign.manifest`). External seeds, no
  111xxxxxx block.
- Mode `one_combat expertfights 1 RUN.json OUT.json` (`run_unit.sh`, one process per run):
  - the expert's logged decisions (path, rewards, chests, campfires, shops, boss relics, events, Neow) are replayed
    while exact; the run ends at the first decision that is not (a shop's other shelves may differ as long as the
    logged purchases are offered), at the end of the log, or at Act 4;
  - at every fight inside that prefix (acts 1-3, floor ≥ 2) HP and max HP are set to the logged values at the end of
    the previous floor;
  - potions are the bot's own (`STS_EXPERT_FIGHTS_POTIONS=own`): the engine's inventory, which follows the expert's
    potion rewards and shop buys (a reward is left when the bot's slots are full, counted as `potionsLeftBeltFull`)
    and the bot's own use in earlier fights of the main line. Setting them to the
    expert's inventory at every fight (`=expert`) was rejected in the smoke: it refills what the bot drank, so the bot
    drank a free Blood Potion in every act-3 fight of run 1660344805 and exited fights 15-20 HP above entry;
  - each fight (any room) whose engine encounter equals the logged one is played K = 4 times from that state by today's A20
    default Silver (learned stop, exact root budgets, g7f_E root table and prior, boss-only prior playouts,
    `STS_FAIR=1`): copy 0 on the game's battle seed (the expert's monster HP, AI and shuffle streams), copies 1-3 on
    fresh battle seeds and persistent combat streams. The run continues from copy 0 if it won (its potions carry on),
    else from the first winning copy; if all four lose, the driver plays the fight once more and the run usually ends.
- Relic counters, bottled cards and anything not logged are the engine's own (from its replay of the prefix).

## Endpoints and analysis (fixed; `analyze.py`)

HP lost = entry HP − exit HP, with exit 0 on a death, for both sides (no survivor selection). Expert exit = the logged
HP after the floor, fruit relics (Strawberry, Pear, Mango) obtained there added back. Bot = mean over the 4 copies.
Fights with any invalid copy or no logged exit HP are dropped and counted.

- **Primary:** mean over acts 1-2 elite and boss fights of (bot HP lost − expert HP lost), 95% CI by run-clustered
  bootstrap (10,000 resamples, seed 20261028).
- **Decision rule:** lower CI bound > +2 HP → COMBAT_GAP (on identical states the bot loses more; combat play,
  potions included, is a bottleneck). Upper CI bound < +2 HP → NO_COMBAT_GAP at this margin (§701's gap comes from
  upstream: deck, HP management, encounter path). Otherwise INCONCLUSIVE. Margin: §701's won-fight gaps are +3.5 to
  +4.5 (elites) and +8 to +12 (bosses) in acts 1-2.
- **Co-reported:** potions used per fight, bot − expert, with the same bootstrap CI. HP lost alone would credit the bot
  for drinking more (§701: it already drinks more); a COMBAT_GAP or NO_COMBAT_GAP verdict is read together with it.
- **Secondary (descriptive):** the same difference with copy 0 only (the expert's deal); death per fight; potions held
  at entry; by act and room (hallways, events, act 3 included); by encounter; the subset whose entry potions equal the
  expert's (Run History Plus logs); replay stop reasons and prefix length; CPU per fight.

## Caveats fixed in advance

- The expert is one sample per fight; the bot is an expectation over 4. Fair RNG does not remove selection: the
  states are those he reached with his own play.
- Engine fight mechanics may differ from the game (not testable here); copy 0 uses the same battle seed, but the
  engine's deck order and earlier stream consumption may differ from the game's.
- A direct human counterfactual under other RNG is not available; the comparison is Silver's expected HP loss vs
  his realized one.
- Potions are only partly matched: after the first fight in which the bot drinks differently from him, its inventory
  differs from his (the co-reported potion difference and the same-potions subset show how much).
- Measurement, no default change on its result.

## Cost (smoke)

See `SMOKE.md`: about 177 s per run on one core, 329 runs ≈ 16 CPU-hours; expected primary n ≈ 2,000 fights.
