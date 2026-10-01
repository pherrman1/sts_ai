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

Scope: `getMove` for every `monsters.exordium` class, and the base and upgrade
constants of the Ironclad attacks in `BattleContext::useCard`. It did not cover
`takeTurn` bodies, HP ranges, or the monster damage table.

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
| Lagavulin awake cycle | `debuffTurnCount` < 2 and attack guard | `lastTwoMoves(ATTACK)` in `takeTurn` | Parity (**Inference**: equivalent for reachable histories) | inspection |
| Gremlins, Looter, Slime Boss, Guardian, Hexaghost first move | fixed first move | same | Parity | inspection |
| Ironclad attack constants (Anger, Bash, Body Slam, Blood for Blood, Bludgeon, Carnage, Clash, Cleave, Clothesline, Feed, Fiend Fire, Headbutt, Heavy Blade, Hemokinesis, Immolate, Iron Wave, Perfected Strike, Pommel Strike, Pummel, Rampage, Reaper, Reckless Charge, Searing Blow, Sever Soul, Sword Boomerang, Thunderclap, Twin Strike, Uppercut, Whirlwind, Wild Strike) | constructor `baseDamage`/`baseBlock`/`baseMagicNumber` and `upgrade()` deltas | `useCard` literals | Parity (constants only, not effect ordering) | inspection |

Only the Red Slaver threshold is reachable in the current A0 research domain.
It affects the Act 1 `RED_SLAVER` encounter and Act 2 Slavers elite, so A0
benchmark values recorded before this fix used the old Red Slaver AI.
Whether that changed any recorded result is **Unverified**; nothing was rerun.

## Ambiguous or not yet inspected

- `Monster::takeTurn` follow-up moves for Hexaghost, The Guardian (mode-shift
  threshold), Slime Boss, and Sentry alternation.
- Lagavulin waking from damage, and Large Slime split timing.
- Act 1 HP ranges and the `MonsterMoveDamage.cpp` table.
- Code comments in `useCard` that mark open semantics: Rampage damage when the
  card is played twice, Twin Strike block interaction, and the Sword Boomerang
  Vigor approximation. These need behavioral or differential evidence, not
  bytecode reading alone.

## Recommendation

The bounded slice found four defects across roughly twenty `getMove` paths.
Three are gated on A17 or A18, and one affects A0. By the issue's decision
rule, that justifies continuing the static audit with:

1. `takeTurn` follow-up moves and the damage and HP constants for Act 1
   monsters;
2. `getMove` for the Act 2 and Act 3 monsters.

Ascension-gated branches deserve particular attention because the A0 research
loop does not exercise them. Every confirmed mismatch still needs a focused
test before it is fixed.
