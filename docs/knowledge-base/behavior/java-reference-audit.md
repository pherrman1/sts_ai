# STS1 Java reference audit

Last verified: 2026-10-01 against `desktop-1.0.jar` V2.3.4 and the
`monster_ai_java_parity` unit test.

## Purpose

The installed Slay the Spire 1 game is a static reference oracle for
simulator mechanics (#348). It explains *what* the simulator should do once a
divergence or suspicious mechanic is identified. Dynamic Java/native lockstep
([differential correctness](../evaluation/differential-correctness.md))
remains the stronger detector. Neither the JAR nor any disassembled or
decompiled output is committed; this page records behavior in our own words.

## Pinned reference

| Field | Value |
|---|---|
| Artifact | `desktop-1.0.jar` from the user's Steam install (`steamapps/common/SlayTheSpire/`) |
| SHA-256 | `cfad868ac8d65a88e71a0bf096fb09f78811e553effe0787c5309a655e081673` |
| Game version | `CardCrawlGame.VERSION_NUM` = `[V2.3.4] (12-18-2022)`; `TRUE_VERSION_NUM` = `2022-12-18` |
| Inspection tool | `javap -c -p -constants` from the JDK 1.8.0_504 install; no third-party decompiler |

`javap` shows exact bytecode, so a branch condition, constant, or move byte is
unambiguous. Runtime-only behavior (action-queue interleaving, render-driven
actions, `ModTheSpire` patches in a live session) is not settled by static
inspection; use the differential harness or a live capture for those.

Reproduce an inspection (output stays in a scratch directory):

    javap -cp <path>/desktop-1.0.jar -c -p -constants \
        com.megacrit.cardcrawl.monsters.exordium.SlaverRed

## Java to native navigation

| Java location | Native location |
|---|---|
| `monsters.<act>.<Monster>.getMove(int)` | `Monster::getMoveForRoll` (`src/combat/MonsterSpecific.cpp`) |
| `monsters.<act>.<Monster>.takeTurn()` | `Monster::takeTurn` switch on `MonsterMoveId` (same file); deterministic follow-up moves are often set here instead of re-rolling |
| Monster move byte (`setMove(byte, …)`) | `MonsterMoveId` enum; the live byte-to-enum table is `apps/one_combat/live_silver_mapping.cpp` |
| Monster HP / move damage | `Monster::initHp` (`MonsterSpecific.cpp`), `src/combat/MonsterMoveDamage.cpp` |
| `AbstractMonster.lastMove` / `lastMoveBefore` / `lastTwoMoves` | `Monster::lastMove` / `lastMoveBefore` / `lastTwoMoves` (`src/combat/Monster.cpp`), over `moveHistory[0..1]` |
| `cards.red.<Card>.use` | `BattleContext::useCard` switch (`src/combat/BattleContext.cpp`) |
| `actions.*` | `src/combat/Actions.cpp` |
| Relic and power hooks | `Player::applyStartOfTurnRelics` and related hooks (`src/combat/Player.cpp`), `BattleContext::initRelics` |
| `AbstractDungeon.aiRng` | `BattleContext::aiRng`; the move roll is `aiRng.random(99)` in `Monster::rollMoveFromInputs` |

Java's ascension gates read `AbstractDungeon.ascensionLevel`; native reads
`bc.ascension` (`asc17`, `asc18` locals in `getMoveForRoll`).

## Bounded Ironclad Act 1 audit

Scope: for every `monsters.exordium` class, `getMove`, `takeTurn` (including
the private move helpers and the `damage` hooks for split, wake, and mode
shift), constructor HP ranges, and move damage and power constants. Also the
base and upgrade constants of the Ironclad attacks in `BattleContext::useCard`.

### Move selection (`getMove`)

| Mechanic | Java reference | Native path | Status | Evidence |
|---|---|---|---|---|
| Red Slaver repeat Stab after Entangle | `SlaverRed.getMove`: roll ≥ 55 | `getMoveForRoll` `RED_SLAVER` used ≥ 50 | **Mismatch, fixed** (all ascensions) | `monster_ai_java_parity` |
| Red/Blue Slaver Scrape/Rake repeat at A17 | A17: no immediate repeat; below A17: no third in a row | combined both rules with OR, which allowed one repeat at A17 | **Mismatch, fixed** (A17+) | `monster_ai_java_parity` |
| Gremlin Nob A18 pattern | A18: Skull Bash unless one occurred in the last two moves; else Skull Bash after two Rushes; else Rush | Rushed whenever the last two were not both Skull Bash, so it never Skull Bashed after Bellow | **Mismatch, fixed** (A18+) | `monster_ai_java_parity` |
| Acid Slime (L) A17 spit guard | A17 roll < 40: no third consecutive Corrosive Spit | checked the Acid Slime (M) move id, so the guard never fired | **Mismatch, fixed** (A17+; restores the guarded `aiRng.randomBoolean(0.6)` call) | `monster_ai_java_parity` |
| Gremlin Nob below A18 | roll < 33 or two Rushes → Skull Bash | same | Parity | inspection |
| Acid Slime S/M, Acid Slime L below A17 | threshold/guard tree | same | Parity | inspection |
| Spike Slime S/M/L | threshold/guard tree | same (A17 `lastMove` subsumes `lastTwoMoves`) | Parity | inspection |
| Jaw Worm, Cultist, Fungi Beast | first move and thresholds | same | Parity | inspection |
| Red/Green Louse | A17 and base guards | same | Parity | inspection |
| Sentry first move | even slot Bolt, odd slot Beam | `idx % 2` | Parity | inspection |
| Gremlins, Looter, Slime Boss, Guardian, Hexaghost first move | fixed first move | same | Parity | inspection |

### Monster turns (`takeTurn`) and state hooks

| Mechanic | Java reference | Native path | Status | Evidence |
|---|---|---|---|---|
| Red Slaver Entangle flag | `takeTurn` sets `usedEntangle` when Entangle resolves | never set `miscInfo` in simulation, so Entangle could repeat and the post-Entangle Stab branch never fired; the live importer supplies the flag, so only simulated Entangles were affected | **Mismatch, fixed** (all ascensions) | `monster_ai_java_parity` |
| Lagavulin waking on its third sleeping turn | changes to its open state, which removes the 8 Metallicize before the end of the turn | switched to Attack but stayed `ASLEEP` with Metallicize 8, gaining 8 block each turn until it took unblocked damage | **Mismatch, fixed** (all ascensions) | `monster_ai_java_parity` |
| Hexaghost Inferno | after six hits, `BurnIncreaseAction` upgrades every Burn in the discard and draw piles (not the hand) and adds three upgraded Burns to the discard pile | attacked only | **Mismatch, fixed** (all ascensions) via `Actions::HexaghostBurnIncrease` | `monster_ai_java_parity` |
| Lagavulin woken by damage | any HP change while asleep sets a Stunned turn and removes Metallicize | clears `ASLEEP` and Metallicize on unblocked damage; the pending `SLEEP` move acts as the Stunned turn | Parity | inspection |
| Lagavulin awake cycle | `debuffTurnCount` < 2 and attack guard | `lastTwoMoves(ATTACK)` in `takeTurn` | Parity (**Inference**: equivalent for reachable histories) | inspection |
| Large slime split | float `hp <= max/2` when not already splitting; spawns two medium slimes at its current HP | integer `curHp <= maxHp/2` in `onHpLost` | Parity | inspection |
| Slime Boss | Goop Spray (Slimed 3, 5 at A19) → Preparing → Slam → repeat; split into Spike (L) then Acid (L) | same, slots 0 and 2 | Parity | inspection |
| The Guardian | Mode Shift 30/35/40 (A9/A19), +10 per cycle; Charging Up 9 block; Defensive Mode 20 block; Sharp Hide 3 (4 at A19); Vent Steam Weak/Vulnerable 2; Whirlwind 5×4; Twin Slam 8×2 | same values and cycle | Parity | inspection |
| Hexaghost cycle | Activate → Divider (HP/12+1 ×6) → Sear, Tackle, Sear, Inflame, Tackle, Sear, Inferno, repeat; Inflame 12 block, Strength 2 (3 at A19); Sear Burns 1 (2 at A19) | same | Parity | inspection |
| Hexaghost Sear Burn upgrade | upgraded after the first Inferno (`burnUpgraded` flag) | upgraded when `bc.turn > 8` | Parity (**Inference**: equal while the Hexaghost never skips a turn, which Ironclad cannot cause) | inspection |
| Looter / Mug, Lunge, Smoke Bomb | first Mug `aiRng.randomBoolean(0.6)` (dialog); after the second Mug `randomBoolean(0.5)`; gold 15 (20 at A17) | same calls and values | Parity | inspection |
| Jaw Worm, Cultist, Fungi Beast, lice, slimes, slavers, Sentry, Nob, Fat/Mad/Sneaky/Shield Gremlin, Gremlin Wizard | per-move debuff, block, Strength, Ritual, status-card counts and ascension steps | same | Parity | inspection |

### HP and damage constants

Every Act 1 monster's HP range and A7, A8, and A9 HP step matches
`include/constants/MonsterIds.h`. Its move damage and A2, A3, A4, and A17 steps
match `Monster::takeTurn` and `MonsterMoveDamage.cpp`. Status: parity, by
inspection of the constructors.

### Ironclad attack constants

Anger, Bash, Body Slam, Blood for Blood, Bludgeon, Carnage, Clash, Cleave,
Clothesline, Feed, Fiend Fire, Headbutt, Heavy Blade, Hemokinesis, Immolate,
Iron Wave, Perfected Strike, Pommel Strike, Pummel, Rampage, Reaper, Reckless
Charge, Searing Blow, Sever Soul, Sword Boomerang, Thunderclap, Twin Strike,
Uppercut, Whirlwind, and Wild Strike were checked. Their constructor
`baseDamage`/`baseBlock`/`baseMagicNumber` values and `upgrade()` deltas match
the `useCard` literals. This covers constants only, not effect ordering.

### A0 impact

Four fixes change A0 behavior:
- the Red Slaver Stab threshold and its Entangle flag (Act 1 `RED_SLAVER`
  encounter and the Act 2 Slavers elite);
- the Lagavulin natural wake;
- the Hexaghost Inferno Burns.

A0 benchmark values recorded before these fixes used the old behavior. Whether
that changed any recorded result is **Unverified**; nothing was rerun.

## Ambiguous or not yet inspected

- The Gremlin Wizard and Shield Gremlin native turns do not check
  `doesEscapeNext()`, while Java's do (`escapeNext`). Only the Act 2 Gremlin
  Leader sets it. **Unverified**; out of the Act 1 scope.
- The Guardian's switch back to offensive mode queues a block loss in Java;
  the native Twin Slam does not. **Inference**: no block exists at that point
  in reachable Ironclad play, because monster block resets at the start of its
  turn.
- Code comments in `useCard` that mark open semantics: Rampage damage when the
  card is played twice, Twin Strike block interaction, and the Sword Boomerang
  Vigor approximation. These need behavioral or differential evidence, not
  bytecode reading alone.

## Recommendation

The Act 1 audit found seven defects: four in `getMove` and three in
`takeTurn`. Four of them affect A0. The yield justifies continuing with
`getMove` and `takeTurn` for the Act 2 and Act 3 monsters. Prioritize:
- the Gremlin Leader escape path above;
- ascension-gated branches, which the A0 research loop does not exercise.

Every confirmed mismatch still needs a focused test before it is fixed.
