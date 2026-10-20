# STS1 Java reference audit

Last verified: 2026-10-19 for half-dead Darkling powers, block on dead monsters, the Mugger death roll and the large slime split; 2026-10-19 for the end-of-turn ethereal exhaust order; 2026-10-18 for powers on dead targets and Curl Up; 2026-10-06 against `desktop-1.0.jar` V2.3.4 and the
`monster_ai_java_parity` and `first_strong_exclusions` unit tests.

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
| Large slime split | float `hp <= max/2` when not already splitting; spawns two medium slimes at its current HP; `aiRng` only from the two spawns' `init` rolls, plus Spike Slime (L)'s own queued `RollMoveAction`; split recorded twice in `moveHistory` | integer `curHp <= maxHp/2` in `onHpLost`; two extra `aiRng` rolls for either slime; split recorded once | **Mismatch, fixed** (`STS_SLIME_SPLIT_RNG_FIX`, see below) | `slime_split_rng` |
| Slime Boss | Goop Spray (Slimed 3, 5 at A19) → Preparing → Slam → repeat; split into Spike (L) then Acid (L) | same, slots 0 and 2 | Parity | inspection |
| The Guardian | Mode Shift 30/35/40 (A9/A19), +10 per cycle; Charging Up 9 block; Defensive Mode 20 block; Sharp Hide 3 (4 at A19); Vent Steam Weak/Vulnerable 2; Whirlwind 5×4; Twin Slam 8×2 | same values and cycle | Parity | inspection |
| Hexaghost cycle | Activate → Divider (HP/12+1 ×6) → Sear, Tackle, Sear, Inflame, Tackle, Sear, Inferno, repeat; Inflame 12 block, Strength 2 (3 at A19); Sear Burns 1 (2 at A19) | same | Parity | inspection |
| Hexaghost Sear Burn upgrade | upgraded after the first Inferno (`burnUpgraded` flag) | upgraded when `bc.turn > 8` | Parity (**Inference**: equal while the Hexaghost never skips a turn, which Ironclad cannot cause) | inspection |
| Looter / Mug, Lunge, Smoke Bomb | first Mug `aiRng.randomBoolean(0.6)` (dialog); after the second Mug `randomBoolean(0.5)`; gold 15 (20 at A17) | same calls and values | Parity | inspection |
| Mugger death | `die()` starts with `playDeathSfx`, `aiRng.random(2)` (the Looter's uses `MathUtils`) | no draw | **Mismatch, fixed** (`STS_MUGGER_DEATH_RNG_FIX`, see below) | `mugger_death_rng` |
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

### A0 impact (Act 1)

Four Act 1 fixes change A0 behavior:
- the Red Slaver Stab threshold and its Entangle flag (Act 1 `RED_SLAVER`
  encounter and the Act 2 Slavers elite);
- the Lagavulin natural wake;
- the Hexaghost Inferno Burns.

A0 benchmark values recorded before these fixes, and before the A0 fixes in
the Act 2 audit below, used the old behavior. Whether that changed any recorded
result is **Unverified**; nothing was rerun.

## Act 2 audit

Scope: for every `monsters.city` class, `getMove`, `takeTurn` (including
private move helpers), the constructors (HP ranges, damage and power
constants, `monsterHpRng` use), and `usePreBattleAction`.

### Mismatches, all fixed

All are covered by `monster_ai_java_parity`.

| Mechanic | Java reference | Native before the fix | Reach |
|---|---|---|---|
| Mystic heal decision | heals when the summed missing HP of all living monsters exceeds 15 (20 at A17), unless both of its last two moves were Heal | compared its own and the Centurion's missing HP separately against 16 (21), with no repeat guard | A0+ |
| Centurion Defend target | `GainBlockRandomMonsterAction`: a random other living monster (one `aiRng` draw), or itself when none | added block to the Mystic only if it was alive, with no `aiRng` draw | A0+ |
| Shelled Parasite re-roll | after Fell on a roll below 20, `getMove` recurses with a fresh roll of 20–99 | tested `roll < 60 \|\| reroll < 60`, so it always took the Double Strike branch | A0+ |
| Gremlin Leader re-roll | with one gremlin after a Stab, `getMove` recurses on 0–80, and 80 recurses again | treated a second roll of 80 as Encourage, with one fewer `aiRng` draw | A0+ |
| Gremlin Leader Encourage block | 6, or 10 at A18 | 10 from A3 | A3–17 |
| Champ Gloat | Strength `strAmt`: 2, 3 from A4, 4 at A19 | 3/4/5 | A0+ |
| Collector Buff block | 15, 18 from A9, 23 at A19 | 18 from A4 | A4–8 |
| Collector Mega Debuff | Weak, Vulnerable and Frail 3 each, 5 at A19 | always 3 | A19 |
| Book of Stabbing single stab | at A18, also increments the stab count | the increment came after `return`, so it never ran | A18+ |
| Snake Plant Spores at A17 | no Spores if either of the last two moves was Spores | blocked only after two Spores in a row | A17+ |
| Romeo Cross Slash | at A17, repeats once before Agonizing Slash | always went to Agonizing Slash | A17+ |
| Bronze Automaton cycle | at A19, the Boost after Hyper Beam does not advance the Flail/Boost count, so Hyper Beam comes every sixth turn | the toggle advanced, so Hyper Beam came two turns early | A19 |
| Torch Head HP roll | the constructor draws a discarded `monsterHpRng` value in 38–40 before `setHp` | one draw, which shifts `monsterHpRng` alignment for every later spawn | A0+ (RNG alignment only) |
| HP ranges | Bear 38–42 (A0); Centurion 78–83 (A7) | Bear 38–52; Centurion 76–83 | Bear A0–6; Centurion A7+ |

### Parity, by inspection

- **Move selection (`getMove`):** Byrd (first move and the flying and grounded
  trees), Centurion move selection, Chosen (both ascension branches), Snecko,
  Spheric Guardian, Taskmaster, Bronze Orb (Stasis is recorded at roll time in
  both Java and native move selection), Champ, Collector, Torch Head,
  Mugger, the bandits, and the Gremlin Leader's gremlin count and pool.
- **Monster turns (`takeTurn`) and constants:** Byrd (Headbutt sets Fly
  without a roll; Stunned rolls into Headbutt), Book of Stabbing, Chosen,
  Mystic Buff and Heal, Shelled Parasite (Stunned sets Fell and then rolls in
  both), Snake Plant, Snecko, Spheric Guardian, Taskmaster, Bear, Pointy,
  Mugger (its `playSfx` draws `aiRng.random(2)` on Mug and Lunge, while the
  Looter's uses `MathUtils`), Bronze Automaton and Bronze Orb constants, the
  Champ's other moves, and the Collector's spawns.
- **Pre-battle powers:** Painful Stabs, Artifact 3 (Automaton), Flight 3/4,
  Thievery 15/20, Malleable, Plated Armor 14 with 14 block, and Spheric
  Guardian's Barricade, Artifact 3 and 40 block.
- **HP:** all other Act 2 ranges match `MonsterIds.h`.

### Live-import finding (fixed)

`STSModelInspector.bronzeAutomatonMiscInfo` used to return 1 whenever the last
two Java moves were Boost and Flail in either order. The native
`lastBoostWasFlail` is 0 at the first Boost after a Flail, so live search
expected Hyper Beam a cycle early.

Native move reconstruction now follows Java's `numTurns` directly instead of
retaining the old `lastBoostWasFlail` toggle. Ordinary capture uses
`bronzeAutomatonNativeTurns(numTurns)` and rejects missing or out-of-range
values (0–4). Under Runic Dome the observer bypasses this private accessor and
reconstructs the pre-roll counter from public executions. `CombatBoundaryTest`
checks the public mapping and JAR field type; `runic_dome_lifecycle` checks the
complete ordinary/hidden cycle and post-Hyper Beam behavior.

## Act 3 audit

Scope: the same as Act 2, for every `monsters.beyond` class, plus the
hard-mode Jaw Worm used by the Act 3 Jaw Worm Horde.

### Mismatches, all fixed

All are covered by `monster_ai_java_parity`.

| Mechanic | Java reference | Native before the fix | Reach |
|---|---|---|---|
| Spire Growth Constrict | after two Quick Tackles on a roll below 50, falls through to Constrict when the player is not Constricted | went to Smash | A0+ |
| Writhing Mass re-roll | after Flail on a roll of 70 or more, `getMove` recurses on 0–69 | returned Wither, with no `aiRng` draw | A0+ |
| Writhing Mass Flail block | equals the Flail damage (15, 16 at A2) | 16, 18 at A2 | A0+ |
| Nemesis Scythe | `scytheCooldown` is 2 on use and drops by 1 per roll, so Scythe is blocked only on the move right after a Scythe | blocked when Scythe was either of the last two moves | A0+ |
| Nemesis Debuff | 3 Burns, 5 at A18 | 5 from A3 | A3–17 |
| Reptomancer Summon | allowed while at most three other monsters live; fills only the free dagger slots (one at A18 with three daggers alive) | at most two daggers, and the summon helper assumed it could always place every dagger | A0+ |
| Darkling Chomp | two hits of 8 (9 at A2) | one hit, in both `takeTurn` and the intent-damage table | A0+ |
| Darkling Nip | the rolled `nipDmg` (7–11, or 9–13 at A2) | added another 2 at A2+ | A2+ |
| Giant Head at A18 | pre-battle lowers `count` by one, so It Is Time starts on turn 4 and its damage ramps one turn sooner | ignored A18 | A18+ |
| Deca and Donu | every turn ends with `RollMoveAction`, one `aiRng` draw | no draw | A0+ (`aiRng` alignment only) |
| Awakened One HP | 320 at A9 | 300–320 | A9+ |
| Jaw Worm Horde | hard-mode Bellow pre-battle: block 6 (9 at A17), Strength 3/4/5 | block 5 at A0–1 | A0–1 |

### Parity, by inspection

- **Move selection (`getMove`):** Orb Walker; the Exploder, Repulsor and
  Spiker shapes; the Maw (Nom hits `(turn+1)/2`, because `turnCount` starts at
  1); Darkling (the odd-slot Chomp restriction and both re-rolls); the Writhing
  Mass's other branches; Giant Head below A18; Reptomancer's re-rolls; Dagger;
  Time Eater (Haste and both re-rolls); Awakened One in both phases; Transient;
  and the first moves of Deca and Donu.
- **Turns and constants:** Orb Walker Laser (one Burn into the draw pile and
  one into the discard pile), Exploder, Repulsor, Spiker, Darkling Harden and
  Reincarnate, Spire Growth, Transient, Writhing Mass Strike, Multi-Strike and
  Wither, Giant Head, Reptomancer, Dagger, Time Eater, Awakened One, and Deca
  and Donu.
- **Pre-battle powers:** Orb Walker Strength Up 3/5, Spiker Thorns 3/4/7,
  Transient Fading 5/6 and Shifting, Awakened One (Regenerate, Curiosity, and
  Strength 2 at A4), Deca and Donu Artifact 2/3, Time Warp, Giant Head Slow, and
  Writhing Mass Reactive and Malleable.
- **HP and `monsterHpRng` use:** every other Act 3 range. The discarded rolls
  of Orb Walker and Reptomancer, the single roll of Dagger, and the Darkling Nip
  roll all match.
- **Nemesis Intangible (Inference):** Java applies Intangible 1 using its
  "just applied" end-of-round rule; native applies 2 and decrements every
  round. Both last through the player's next turn.

## Act 4 audit

Scope: the same as Act 2, for every `monsters.ending` class (Corrupt Heart,
Spire Shield, Spire Spear).

### Mismatch, fixed

Covered by `monster_ai_java_parity`.

| Mechanic | Java reference | Native before the fix | Reach |
|---|---|---|---|
| Spire Spear Burn Strike at A18 | 2 Burns on top of the draw pile: `MakeTempCardInDrawPileAction` with `randomSpot` and `toBottom` false calls `addToTop` | added no Burns: `Actions::MakeTempCardInDrawPile` with `shuffleInto=false` was an unimplemented `todo` | A18+ |

That action branch is now implemented by
`CardManager::createTempCardOnDrawPileTop`. The Spire Spear was its only
caller.

### Parity, by inspection

- **Corrupt Heart:** Debilitate first. Then, every three moves, a random Blood
  Shots or Echo, the other one, and Buff, with the same `aiRng` draws.
  Constants: Debilitate (2/2/2 and five status cards), Buff (clears negative
  Strength, +2, then Artifact 2, Beat of Death, Painful Stabs, Strength 10,
  Strength 50), Blood Shots 2×12/15, Echo 40/45, Invincible 300/200, Beat of
  Death 1/2, and HP.
- **Spire Shield:** the `moveCount % 3` cycle matches the native
  `lastMoveBefore` transitions. Constants: Bash with Strength −1 (the
  orb/Focus branch cannot trigger without orbs), Fortify 30, Smash 34/38 with
  99 block at A18, Surrounded, Artifact 1/2, and HP.
- **Spire Spear:** the same cycle with Burn Strike first. Constants: Burn
  Strike 2×5/6, Piercer +2 Strength to all monsters, Skewer 3/4×10, Artifact
  1/2, and HP.

## Monster method overrides

The per-act audits covered `getMove`, `takeTurn`, constructors and
`usePreBattleAction`. A later sweep listed every other method each
`monsters.*` class overrides (92 across 59 classes). Each override was
reduced to its gameplay operations; animation, sound and VFX were ignored.

### Overrides that matter, all modelled natively

| Override | Effect | Native |
|---|---|---|
| `Nemesis.damage` | while Intangible, every positive hit becomes 1, including thorns, power, relic, potion and poison damage. Nemesis is the only monster that gains `IntangiblePower`; the base `AbstractMonster.damage` checks only the player's `IntangiblePlayer` | the Intangible cap in `Monster::damage` and `Monster::attacked`. **Known gap:** native poison ticks (`ActData_PoisonLoseHpAction`) call `damageUnblockedHelper` directly and are not capped, whereas Java's `PoisonLoseHpAction` goes through `Nemesis.damage`. Ironclad can only poison through another class's cards (e.g. Prismatic Shard). |
| `AcidSlime_L`, `SpikeSlime_L`, `SlimeBoss` `damage` | split at half HP | `Monster::onHpLost` |
| `Lagavulin`, `TheGuardian`, `ShelledParasite` `damage`/`changeState` | wake, mode shift, plated-armour stun | covered in the Act 1 and Act 2 tables |
| `Byrd.changeState("GROUNDED")` | Stunned when Flight breaks. `FlightPower.onAttacked` drops Flight only on attack damage (not HP loss or thorns) and resets it each turn; the breaking `ReducePowerAction` removes the power (`STS_BYRD_GROUNDED_FLIGHT_FIX`) | `Monster::attackedUnblockedHelper`, `Monster::applyStartOfTurnPowers` |
| `AwakenedOne.damage` (first death) | half-dead, power and relic death hooks (e.g. Gremlin Horn), card queue cleared, debuffs removed, Rebirth | `Monster::die` |
| `TheCollector`, `BronzeAutomaton`, `GremlinLeader`, `AwakenedOne` `die` | minions die or escape | the minion-leader branch of `Monster::die` ends the fight |
| `Looter`, `Mugger` `die` | stolen gold returned as a reward | the native theft accounting |
| `SpireShield`, `SpireSpear` `die` | remove the player's Surrounded and the partner's BackAttack | the back-attack ×1.5 in `Monster::calculateDamageToPlayer` cannot apply once either has died. **Inference:** Java multiplies after Weak and Vulnerable and native before; the product is the same apart from float rounding |

### Dead code in vanilla

- Gremlin `deathReact` (switch to the escape move): the only `deathReact`
  caller is `BanditBear.die`.
- Gremlin `escapeNext()`: the method is never called.

The bandits' `deathReact` only queues dialogue.

## Ironclad cards and powers

### Card properties

A generated comparison checked all 75 `cards.red` classes against
`include/constants/Cards.h`: costs, upgraded costs, X cost, exhaust,
ethereal, innate, self-retain, type, rarity and targeting.

### Card effects

`use()` was compared with `BattleContext::useCard` and `usePowerCard` for every
card: base and upgrade values, and the actions queued.

### Mismatches, all fixed

All are covered by `ironclad_card_java_parity`.

| Mechanic | Java reference | Native before the fix | Reach |
|---|---|---|---|
| Rage cost | 0 | 1 (missing from `getEnergyCost`) | A0+ |
| Infernal Blade+ cost | 0 | 1 | A0+ |
| Seeing Red | exhausts | did not exhaust | A0+ |
| Disarm+ | −3 Strength | −2 | A0+ |
| Brutality | `atStartOfTurnPostDraw` draws, then loses HP as self-damage (triggers Rupture) | lost HP first, without the self-damage flag | A0+ |
| Pain | its HP loss is self-damage (triggers Rupture) | not self-damage | A0+ |
| Intangible card damage | `IntangiblePower.atDamageFinalReceive` caps damage above 1 at 1; 0 stays 0 | `max(damage, 1)` raised 0 to 1 | A0+ (Nemesis) |

### Parity, by inspection

- **Damage formula:** relic modifiers, then player powers in priority order
  (Strength and Vigor 5, Pen Nib and Double Damage 6, Weak 99), then the
  target's Slow, Vulnerable (Paper Frog ×1.75), Flight and Intangible, floored.
- **Powers:** Perfected Strike counts itself (damage is computed before the
  card leaves the hand); Clash's playability rule; Blood for Blood's cost
  reduction across hand, draw and discard; Combust (HP loss +1 per extra copy,
  so the native `todo` is stale); Juggernaut targets with `cardRandomRng`.
- **Other hooks:** Rage, Double Tap, Evolve (No Draw is checked when drawing),
  Fire Breathing, Dark Embrace, Feel No Pain, Corruption, Flame Barrier,
  Metallicize before end-of-turn cards, and the end-of-turn removals
  (Lose Strength, No Draw, Entangled).

### Player Intangible (parity)

`AbstractPlayer.damage` caps damage above 1 at 1 for every damage type,
including HP loss. Native applies the same cap in `Player::damage`, in
`Player::loseHp`, and in `Monster::calculateDamageToPlayer` (min 1).
`Player::loseHp` is never called with 0, because `hpWasLost` asserts
`amount > 0`.

### Powers on dead targets (mismatch, fixed)

Read with `javap -c -p` from the pinned JAR (2026-10-18):

- `ApplyPowerAction.update` begins with
  `if (target == null || target.isDeadOrEscaped()) { isDone = true; return; }`.
  It runs on every tick, for buffs and debuffs alike.
- After the `onApplyPower` hooks and the Champion Belt trigger it checks a
  monster target again, and only then applies Ginger, Turnip and Artifact.
- `shouldCancelAction` is never called by this action, so a dying source does
  not cancel it.
- `AbstractCreature.isDeadOrEscaped` is
  `isDying || halfDead || (monster && isEscaping)`; native
  `Monster::isDeadOrEscaped` is the same set.
- The constructor makes the action a no-op when
  `areMonstersBasicallyDead()`.

Native applied debuffs and buffs to dead monsters; the combat parity canary
saw it when Uppercut killed its target. `STS_DEAD_TARGET_DEBUFF_FIX` (default
on) returns early in `BattleContext::debuffEnemy` (before Artifact, Sadistic
Nature and Champion Belt) and in `ActData_BuffEnemy`. Not mirrored natively
yet (**Unverified** whether native already matches):

- powers on the player while the player is dying;
- the constructor's `areMonstersBasicallyDead` cancel.

A dead monster's powers stay in the native state; Java clears them in
`updateDeathAnimation`, after `die()` (javap on the PC, 2026-10-18).
**Inference:** no game rule reads them, so the parity probe ignores them
instead of the engine clearing them.

### Half-dead Darkling powers (mismatch, fixed)

`Darkling.damage` calls `powers.clear()` when a Darkling goes half-dead, and
REINCARNATE applies a fresh Regrow (javap on the PC, 2026-10-19). Native
`Monster::resetAllStatusEffects` cleared the status bits but kept the
amounts, so a debuff on the revived Darkling added to them.
`STS_HALF_DEAD_POWER_RESET_FIX` (default on, `=0` restores) clears them.

Test: `half_dead_power_reset`.

### Curl Up on a lethal hit (mismatch, fixed)

`CurlUpPower.onAttacked` curls only when `damageAmount < owner.currentHealth`
(second parity canary, 2026-10-18). Native curled on a killing hit too, which
queued block on the dead louse. `STS_CURL_UP_LETHAL_FIX` (default on, `=0`
restores) makes native check the same condition. The louse is dead either
way, but the dead monster's block and status bits are part of Silver's node
identity (hash and state equality), so search can change.

Test: `dead_target_debuff_fix`.

### Multi-hit from a dead attacker (mismatch, fixed)

Read with `javap -c -p` from the pinned JAR (2026-10-19):

- `DamageAction.update` checks on every tick, before anything else, whether
  `shouldCancelAction()` holds and the damage type is not `THORNS`; if so the
  action ends with no damage. On its first tick it also ends when the
  damage owner `isDying` or `halfDead` (again unless `THORNS`).
- `shouldCancelAction()` is `target == null || source.isDying ||
  target.isDeadOrEscaped()`; `source` is the `DamageInfo` owner.
- `AbstractMonster.die` sets `isDying` at its start, and `damage` calls it in
  the same tick that takes the monster to 0 HP. Darkling and stage-1
  Awakened One become `halfDead` only and do not touch the action queue.
- Byrd's Peck queues one `DamageAction` per hit.

So when player Thorns (or Flame Barrier, Bronze Scales) kills a monster
partway through a multi-hit, its remaining hits do nothing. Native landed them
(overnight live play, seed 111194455: 2 extra Byrd pecks).
`STS_DYING_ATTACKER_FIX` (default on, `=0` restores) returns early in
`ActData_AttackPlayer` when the attacker is dead or half-dead. Monster
`THORNS`-type damage (`DamagePlayer`: Spiker Thorns, Sharp Hide, Exploder) is
not cancelled, as in Java.

Test: `dying_attacker`.

### Block on a dead monster (mismatch, fixed)

`GainBlockAction.update` adds block only when the target is neither
`isDying` nor `isDead` (javap on the PC, 2026-10-19). A multi-hit card such
as Fiend Fire can curl a louse with an early hit and kill it with a later
one before the queued block resolves; the game leaves the dead louse at 0
block, native added the Curl Up amount (overnight live play, seed 111194454).
`STS_DEAD_MONSTER_BLOCK_FIX` (default on, `=0` restores) makes the native
monster block action skip a dead monster that is not half-dead. It covers
every queued monster block (Curl Up, Malleable, Guardian mode shift, block
moves). Only Silver's node identity changes.

Test: `dead_monster_block`.

### Mugger death roll (mismatch, fixed)

`Mugger.die` calls `playDeathSfx`, which draws `aiRng.random(2)`, before
`AbstractMonster.die`; `Mugger.playSfx` draws the same on Mug and Lunge. The
Looter's sound methods use `MathUtils` (javap, 2026-10-19). Native drew
nothing on a Mugger death, so every later monster roll in the fight
differed (parity canary 2: `aiRng` counter 9 in the game vs 8 natively after
the kill). `STS_MUGGER_DEATH_RNG_FIX` (default on, `=0` restores) draws it at
the start of `Monster::die`.

Test: `mugger_death_rng`.

### Large slime split (mismatch, fixed)

`AcidSlime_L.damage` and `SpikeSlime_L.damage` (and `SlimeBoss.damage`) call
`setMove(SPLIT)` and queue a `SetMoveAction(SPLIT)`, so the split byte enters
`moveHistory` twice. On the split turn both large slimes queue
`SpawnMonsterAction` twice; each runs `init`, one `aiRng.random(99)` roll
(a fresh medium slime has no move history, so its `getMove` draws nothing
more). `AcidSlime_L.takeTurn` then returns; `SpikeSlime_L.takeTurn` falls
through to a `RollMoveAction` for itself, one more roll on the dead slime.
`queueMonsters` snapshots the turn order first, so the new slimes do not act
that turn (javap, 2026-10-19). Native drew two extra rolls for either slime
(a `noOpRollMove` plus an `extraRollMoveOnTurn` roll) and kept the previous
move in `moveHistory[1]` (overnight live play, seed 111194454: `aiRng`
counter 6 in the game vs 8 natively). `STS_SLIME_SPLIT_RNG_FIX` (default on,
`=0` restores) draws 2 rolls for Acid Slime (L), 3 for Spike Slime (L), and
records the split twice for both large slimes and the Slime Boss.

Test: `slime_split_rng`.

### Ethereal exhaust order at end of turn (parity, not reproducible)

`DiscardAtEndOfTurnAction.update` copies the hand, shuffles the copy with the
one-argument `Collections.shuffle` (Java's unseeded static `Random`, not a
game RNG stream) and calls `triggerOnEndOfPlayerTurn` on each card, which
queues `ExhaustSpecificCardAction` with `addToTop` for an ethereal card (javap
on the PC, 2026-10-19). The order of end-of-turn ethereal exhausts is
therefore random and unseeded in the game. All of them still resolve before
the end-of-turn discards, and retained cards are already in limbo. Native
exhausts them in reverse hand order, which is one of the orders the game can
produce. Clumsy queues the same exhaust; Ghostly Armor and Entrench queue
`ExhaustAllEtherealAction`, which only repeats exhausts that the
`group.contains` guard then skips.

**Inference:** the order cannot change play. On-exhaust effects (Feel No Pain,
Dark Embrace, Dead Branch, Charon's Ashes) depend on how many cards are
exhausted, not which one goes first, no ethereal Ironclad, colorless or curse
card has its own on-exhaust effect, and no rule reads the exhaust pile order
(Exhume shows a grid). No engine change; the combat parity probe compares the
exhaust pile as a multiset (`UNORDERED_PILES` in `tools/combat_parity.py`).

## Ironclad relics

### Pools

`RelicLibrary.populateRelicPool` iterates the `sharedRelics` and then
`redRelics` `HashMap`s. Replaying the JAR's `RelicLibrary.initialize`
insertion order into a real JDK 8 `HashMap` gives the same membership and
order as `include/constants/RelicPools.h` for all five Ironclad pools
(33/30/28/22/17), assuming a fully unlocked profile. The native shuffle uses
`java::Collections::shuffle` seeded from `relicRng.randomLong()`, as the game
does.

### Effects

For every relic in the Ironclad pools and the red relics, each overridden hook
was compared with the native references.

| Relic | Status | Note |
|---|---|---|
| Ancient Tea Set | **Mismatch, fixed** | Java charges the relic on entering any rest site (`onEnterRestRoom` sets the counter to −2) and spends it on the first turn of the next combat, however many rooms later. Native used `gc.lastRoom == Room::REST`, which missed rest → event, shop or treasure → fight. Now relic `data` is 1 while charged: `GameContext::transitionToMapNode` sets it on entering a rest site, `BattleContext::initRelics` grants +2 energy when it is set, and `updateRelicsOnExit` clears it. Save files and the inspector map the vanilla −2 to 1 and everything else to 0. In the inspector this is `combatEntryRelicData`, which is used for combat entry and the CTM and is shared by `LiveOocCapture.nativeRelicData` for live out-of-combat roots. **Limitations:**
- The lazy combat-entry fallback, which captures at the first decision when the battle-start capture was missed, sees the already spent −1, so that entry records 0 although Java granted +2.
- Snapshots recorded before this change replay without the old `lastRoom` energy. The CTM relic legality and native contract model the post-combat data as 0. Covered by `ironclad_card_java_parity` and `CombatBoundaryTest`. |
| All other Ironclad-pool and red relics | Parity | Includes the counter relics (Pen Nib's −1 encodes "9 with the power active"; Sundial, Happy Flower, Incense Burner and Nunchaku are offset but equivalent); turn-indexed relics (Captain's Wheel, Horn Cleat, Stone Calendar); Art of War and Pocketwatch from turn 2 only; Orichalcum (its `trigger` flag is never set); Boot and Torii (after block, attack damage only); Preserved Insect; Magic Flower's rounding; Gremlin Horn on Darkling half-death; Mummified Hand's filters and `cardRandomRng`; Strange Spoon's `cardRandomRng`; Whetstone, War Paint and Tiny House with `java.util.Random(miscRng.randomLong())`; Slaver's Collar (elite or boss); Brimstone on turn 1; the Burning and Black Blood victory heals. |

### Necronomicon and Necronomicurse

Issue #406 inspected these classes in the pinned JAR (`javap -c -p`):

| Java hook | Native path | Status |
|---|---|---|
| `relics.Necronomicon.onEquip` obtains a new `Necronomicurse` through `ShowCardAndObtainEffect` | `GameContext::obtainRelic` `NECRONOMICON` case calls `Deck::obtain`, so Omamori, Darkstone Periapt and Ceramic Fish apply as for any curse | **Mismatch, fixed** (#406): native added no curse |
| `cards.curses.Necronomicurse.onRemoveFromMasterDeck` queues a `NecronomicurseEffect` with a new copy | `Deck::remove` puts the curse back | **Mismatch, fixed** (#406). Unreachable natively by code reading: every native removal screen and event filters out untransformable curses |
| `Necronomicurse.triggerOnExhaust` adds a copy to hand | `BattleContext` exhaust handler queues `MakeTempCardInHand(NECRONOMICURSE)` | Parity |

**Unverified:** whether `NecronomicurseEffect` re-obtains through the
obtain hooks (Omamori, Darkstone, Ceramic Fish); native re-adds the card
without them. The Necronomicon combat effect (the first 2+-cost attack each
turn plays twice) was not audited.

### Ritual Dagger

A new Ritual Dagger starts at 15 base damage, stored in the master-deck
card's `misc`, and gains 3 (5 upgraded) per fatal kill. Native kept `misc`
at 0 for every new card, so every dagger from The Nest or `Deck::obtain`
dealt 0 + kill bonuses (**Mismatch, fixed** in #426: the `Card(CardId)`
constructors set `misc` to 15 for `RITUAL_DAGGER`). Corpora generated
before the fix carry the 0-based dagger. Covered by `issue_fixes`.
**Unverified:** the starting value comes from the decompiled card source, not
from `javap` on the pinned JAR. Genetic Algorithm also starts with a nonzero
`misc` in Java (1); native leaves it at 0, but it is a Defect card whose
play is not implemented natively.

**Not inspected:** relics only reachable through events, Neow or other
classes, and relic hooks that act purely out of combat beyond the
upgrade/transform relics listed above.


## Encounter generation

Java `AbstractDungeon.populateFirstStrongEnemy` draws the act's first strong
hallway encounter from the strong weights and re-rolls `monsterRng` while the
draw is in the act's `generateExclusions()`, which depends only on the last
weak encounter. Native `GameContext::populateFirstStrongEnemy`
(`src/game/GameContext.cpp`) uses the same re-roll loop.

| Act (Java class) | Last weak encounter | Excluded as first strong |
|---|---|---|
| 1 (`Exordium`) | Small Slimes | Large Slime, Lots of Slimes |
| 1 | 2 Louse | 3 Louse |
| 2 (`TheCity`) | Spheric Guardian | Sentry and Sphere |
| 2 | 3 Byrds | Chosen and Byrds |
| 2 | Chosen | Chosen and Byrds, Cultist and Chosen |
| 3 (`TheBeyond`) | 3 Darklings | 3 Darklings |
| 3 | Orb Walker | Orb Walker (not in the strong pool, so never fires) |
| 3 | 3 Shapes | 4 Shapes |

`Exordium` also has Looter and Blue Slaver cases, which never fire because
those are strong encounters, so the last weak encounter is never one of them.

### Mismatch, fixed

Until #407, native applied only the act 1 rows. In acts 2 and 3 it could
produce a first strong fight the game never would. Java consumes an extra
`monsterRng` draw per re-roll and `monsterRng` is not reseeded between acts, so
from that point the rest of the run's `monsterRng` sequence (the act's strong
queue, elites and boss, then every later act) diverged from the game for the
same seed. **Inference** from the pool weights: an act 2 queue hits an
exclusion with probability 9/145 (about 6%), an act 3 queue with probability
1/12. Covered by `first_strong_exclusions`, which checks the result and the
`monsterRng` counter against a Java-rule reimplementation for every act and
last weak encounter.

Consequence for evidence: corpora and runs generated before this fix follow the
act-1-only rule, so paired seeds across the fix boundary (for example a new run
against the #417 pilot or older ledger runs) are not seed-for-seed comparable
past act 1 for roughly 6–14% of seeds. Comparisons within one SHA are
unaffected.

## Out-of-combat audit (2026-10-17)

Scope: Neow HP options, shop prices, Bonfire Spirits, Fountain of Cleansing
eligibility, Dead Adventurer, Black Star and Torii in events, Ectoplasm, the
burning-elite buff and Act-3 boss rewards, checked with `javap` against the
pinned JAR.

| Mechanic | Java reference | Native before the fix | Status |
|---|---|---|---|
| Neow 10%/20% max-HP bonus | `hp_bonus = (int)(maxHealth*0.1f)` from the constructor; `increaseMaxHp(hp_bonus)` / `increaseMaxHp(hp_bonus*2)`, which heals the same amount | added `(int)(max*0.1)` / `(int)(max*0.2)` without healing (A20: 68/82 instead of 75/82) | **Mismatch, fixed** (`STS_ENGINE_FIDELITY_FIX`) |
| Neow 10% max-HP loss | `decreaseMaxHealth(hp_bonus)` | `(int)(0.9f*max)` (75 → 67, Java 68) | **Mismatch, fixed** |
| Neow damage drawback | HP-loss damage of `currentHealth/10*3` | `cur = cur/10*7` (68 → 42, Java 50) | **Mismatch, fixed** |
| Bonfire Spirits, Uncommon offering | `heal(maxHealth)` | healed 10 | **Mismatch, fixed** |
| Dead Adventurer after three rewards | only Leave remains | Search stayed, with a forced elite fight | **Mismatch, fixed** (the event ends) |
| Black Star | read only in `MonsterRoomElite.dropReward` | added a relic to the Dead Adventurer fight | **Mismatch, fixed** |
| Torii | `onAttacked` needs an owner and `1 < damage <= 5`; Scrap Ooze, Golden Idol, Face Trader and The Nest pass no owner, Wing Statue, Shining Light and World of Goop pass the player | reduced all event damage of 5 or less to 1 | **Mismatch, fixed** |
| Ectoplasm | `canSpawn`: `actNum <= 1` | always eligible | **Mismatch, fixed** |
| Burning elite buff | Strength `actNum+1`; +25% max HP; Metallicize `actNum*2+2`; Regenerate `1+actNum*2`; `mapRng.random(0,3)` at combat start | Strength `act`; others equal; draw at map generation gives the same value | **Mismatch, fixed** (Strength) |
| Shop prices at A16+ | `applyDiscount(1.1f, false)` (purge unchanged) | ×0.8 | **Mismatch**, fixed by `STS_SHOP_RULES_FIX` (#594) |
| Fountain of Cleansing eligibility | `isCursed()` ignores Ascender's Bane, Curse of the Bell, Necronomicurse | `deck.hasCurse()`, whose curse count already skips untransformable curses | Parity |
| Act-3 boss rewards | gold is added and then skipped with the reward screen for TheBeyond bosses | no rewards | Parity |

## Ambiguous or not yet inspected

- Gremlin `escapeNext` (resolved: unreachable in vanilla). Java's gremlin
  turns check `escapeNext` before choosing their escape move (99). The native
  Gremlin Wizard and Shield Gremlin do not; the other native gremlins do, but
  their `GENERIC_ESCAPE_MOVE` does nothing.
  - In the pinned JAR, only `AbstractMonster` and the five gremlin classes
    reference `escapeNext`. The field becomes true only inside the gremlins'
    `escapeNext()` method, and no class calls it.
  - When the Gremlin Leader dies, its minions escape immediately
    (`GremlinLeader.die` queues an `EscapeAction` for each). Natively, the
    minion-leader branch of `Monster::die` ends the fight instead.
  - The escape-next path therefore never fires in vanilla play, and the native
    code is left unchanged. Revisit only if a mod or the live importer
    (`escapeNext` in `live_silver_importer.cpp`) is shown to set it.
- The Guardian's switch back to offensive mode queues a block loss in Java;
  the native Twin Slam does not. **Inference**: no block exists at that point
  in reachable Ironclad play, because monster block resets at the start of its
  turn.
- Code comments in `useCard` that mark open semantics: Rampage damage when the
  card is played twice, Twin Strike block interaction, and the Sword Boomerang
  Vigor approximation. These need behavioral or differential evidence, not
  bytecode reading alone.

## Recommendation

The monster audit of Acts 1–4 is complete. It found 34 simulator defects, 19 of
which reach A0, plus one live-import mapping defect (since fixed). Every simulator defect has
a focused test in `monster_ai_java_parity`.

The remaining static targets are the Inference rows above.

Beyond monster AI and constants, invest in dynamic differential captures
([differential correctness](../evaluation/differential-correctness.md)) for
ordering-sensitive interactions such as action-queue order, powers, and relic
triggers, which bytecode reading cannot settle cheaply. Consider a static
audit of event and relic behavior only if differential captures point there.
