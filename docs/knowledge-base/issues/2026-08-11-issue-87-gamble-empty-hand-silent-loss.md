# Issue 87: Gambler's Brew at an empty hand ends the run as an invisible loss (hpEnd > 0, deathEnc = -1)

- **Status:** partially fixed (Gambler's Brew empty-hand trigger fixed; generic
  empty-hand multi-select behavior remains open)
- **Detection:** the runtime simulator health monitor (2026-08-11, see
  [`behavior/simulator-health-monitor.md`](../behavior/simulator-health-monitor.md))
  now automatically flags this seed: seed 126711 at the recorded stack fires
  `[sim-health][HARD] NO_LEGAL_PROGRESSION` + `UNDECIDED_BATTLE_EXIT` at
  `CARD_SELECT/GAMBLE/hand=0/UNDECIDED` without `STS_DEBUG_BATTLE_BREAKS`, and
  `STS_SIM_HEALTH_CAPTURE_DIR` writes a reloadable `.bin` snapshot of the broken
  decision. Detection only — the mechanism below and the invisible-loss row are
  unchanged.
- **Tier:** High
- **Date:** 2026-08-11
- **Source:** user-reported seed 126711 from the A0 1k/128-seed GCP rerun
  `build/rerun_2026-08-10_a0_gates_1k_128.csv` (commit `5959e4c`, decision-log
  `2026-08-10-full-stack-rerun.md` §166); reproduced on local HEAD (`b750cc6`)
  at the same configuration.

## Phase 10 disposition

The narrow Gambler's Brew trigger is fixed in
`src/sim/search/Action.cpp::isValidPotionAction`: the potion is now illegal at
`PLAYER_NORMAL` when `cardsInHand == 0`, while remaining legal with a non-empty
hand. This prevents the simulator from creating the documented
`CARD_SELECT/GAMBLE/hand=0` state through an illegal potion action.

The generic `pushMultiSelectActions` empty-hand behavior is intentionally not
changed. `EXHAUST_MANY` and any other path that can independently create an
empty-hand multi-select state remain follow-up work; this issue is not closed
as a general empty-hand bug-class fix.

The historical seed-126711 reproduction was not observed on the requested
current baseline before the Phase 10 edit: the exact guarded configuration
completed with `win%=100.0`, `avg_floor=51.0`, and no battle-break diagnostic.
That result does not invalidate the source-level legality defect or the focused
regression; it means only that the historical integration reproduction is not
currently reproducible from this checkout.

## Symptom

The rerun row for seed 126711 is a loss at the Act-3 boss floor with positive
HP and no recorded combat death:

```
seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter
126711,0,50,3,39,83,0,-1,-1
```

`won=0` (run lost), `floor=50` (Act-3 boss), `hpEnd=39`, `fightsLost=0`,
`deathCombat=-1`, `deathEncounter=-1`. The run died at floor 50 but the player
never lost HP in any recorded fight, and no combat was recorded as a loss.

## Evidence

Local reproduction at the identical config (single seed, deterministic):

```
STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64
STS_LIVE_VALID=1 STS_DEBUG_BATTLE_BREAKS=1
STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1
./build/one_combat bestbench 1000 1 0 126711
```

prints

```
[battle-break] state=2 task=9 pickCount=1 hand=0 outcome=0
BEST   win%= 0.0   avg_floor= 50.0   avg_hp_end= 39.0
```

and writes the CSV row above (hpEnd 39, fightsLost 0, deathCombat -1,
deathEncounter -1) — matching the GCP row exactly. Decode of the break state:
`state=2` = `InputState::CARD_SELECT`, `task=9` = `CardSelectTask::GAMBLE`,
`hand=0` = empty hand, `outcome=0` = `Outcome::UNDECIDED`.

Mechanism chain (each step confirmed in current code):

1. **Trigger — the search drinks Gambler's Brew with an empty hand.**
   `isValidPotionAction` (`src/sim/search/Action.cpp:70-112`) allows a
   GAMBLERS_BREW "use" action at any `PLAYER_NORMAL` state: the potion does not
   require a target and no hand-size gate exists. Real StS disables the potion
   when the hand is empty. `drinkPotion` → `addToBot(Actions::GambleAction())`
   (`src/combat/BattleContext.cpp:2402-2404`, `src/combat/Actions.cpp:996-1001`),
   which fires immediately (the action queue was drained before the decision),
   so the hand at the resulting CARD_SELECT is still 0.
2. **The GAMBLE select with an empty hand is unplayable.**
   `Action::enumerateCardSelectActions` → GAMBLE →
   `pushMultiSelectActions` (`src/sim/search/Action.cpp:544-588, 662-664`)
   early-returns on `n = cardsInHand <= 0` and emits **zero** actions — not even
   the empty subset ("discard none", mask=0).
3. **Both searchers enumerate CARD_SELECT through the shared enumerator**
   (`src/sim/search/BattleScumSearcher3.cpp:2966-2974`,
   `src/sim/search/BattleScumSearcher2.cpp:838-840`), so the search root has
   zero edges at this decision; `s3PickRootAction` returns `have=false`
   (`src/sim/search/ScumSearchAgent2.cpp:46-68`).
4. **`playoutBattleFair` breaks the battle loop with `bc.outcome == UNDECIDED`**
   (`src/sim/search/ScumSearchAgent2.cpp:419-427`) — unlike the stall guard,
   which sets `bc.outcome = Outcome::PLAYER_LOSS` first.
5. **`BattleContext::exitBattle` maps UNDECIDED to a run loss** (issue-48 guard,
   `src/combat/BattleContext.cpp:532-538`), ending the run at floor 50 with
   `hpEnd = 39`. This guard is correct (it prevents the old §113 skip-win
   exploit), but the loss is only materialized at `GameContext` level.
6. **`runFullRunOOC` records `deathCombat`/`deathEncounter` only when
   `bc.outcome == Outcome::PLAYER_LOSS`** (`apps/one_combat.cpp:2892`); here it
   never was, so both stay `-1` and `fightsLost` stays `0`.

## Why it matters

- The search forfeits a fight — and the whole run — via a move the real game
  forbids. The same defect class already aborts known-RNG Searcher2 runs
  (EXHAUST_MANY/empty-hand, documented in
  `docs/knowledge-base/architecture/combat-search.md` "Known limitations" and
  decision-log `2026-08-06-searchdiag-rollout-usage.md`); the GAMBLE variant is
  observable under the recommended fair-S3 config as a *silent loss* instead of
  an abort.
- The run-level metadata is untruthful: `won=0` with `hpEnd=39`, `fightsLost=0`,
  `deathEnc=-1`. Downstream consumers (`paired_analysis.py`, `check_replay.py`,
  the fightrep harness) cannot distinguish "died in the boss fight" from this
  state; the fightrep harness treats floor-50 losses as boss deaths, so one of
  the 14 recorded floor-50 losses is this mechanism, not a boss defeat.
- Prevalence is unknown beyond this seed; scanning the GCP 128-seed CSV for
  `won=0 ∧ deathEnc=-1 ∧ hpEnd>0` rows would quantify it. The health monitor's
  8-seed fair smoke (2026-08-11) already caught a second instance of the same
  invisible-loss shape on seed 4 via the EXHAUST_MANY/empty-hand variant
  (`won=0, floor=50, hpEnd=80, deathEnc=-1`, DONU_AND_DECA).

## Candidate fix directions

1. Gate GAMBLERS_BREW (and other multi-select-producing effects) on
   `cardsInHand > 0` in `isValidPotionAction` (matches the real game), so the
   search can never create the stuck state.
2. Make `pushMultiSelectActions` emit the empty subset (mask=0) when
   `cardsInHand == 0`, so an empty-hand multi-select resolves as "discard
   none". This also covers the EXHAUST_MANY/empty-hand abort limitation.
3. Make the UNDECIDED battle-break record a loss consistently: set
   `bc.outcome = Outcome::PLAYER_LOSS` before the `!have` break (matching the
   stall guard), or record the run-level loss in `runFullRunOOC` regardless of
   `bc.outcome`, so `fightsLost`/`deathCombat`/`deathEncounter` stay truthful.

## Relevant code

- `src/sim/search/Action.cpp:70-112` (isValidPotionAction), `544-588`
  (pushMultiSelectActions), `662-664` (GAMBLE enumeration)
- `src/sim/search/ScumSearchAgent2.cpp:46-68` (s3PickRootAction), `419-427`
  (battle-break), `536-541` / `619-621` / `676-678` (stall guard comparison)
- `src/combat/BattleContext.cpp:532-538` (exitBattle UNDECIDED guard), `2402-2404`
  (GAMBLERS_BREW), `3127` (chooseGambleCards)
- `src/combat/Actions.cpp:996-1001` (GambleAction)
- `apps/one_combat.cpp:2892` (deathCombat/deathEncounter recording)
- `src/sim/search/BattleScumSearcher3.cpp:2966-2974`,
  `src/sim/search/BattleScumSearcher2.cpp:838-840` (CARD_SELECT enumeration)
