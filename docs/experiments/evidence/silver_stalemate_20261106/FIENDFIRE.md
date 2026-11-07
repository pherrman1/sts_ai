# Fiend Fire at seed 111680130, floor 44 (Shapes), turn 4 — diagnosis (2026-11-06)

Copied from Philipp's PC (`~/longc-diag-out/stalemate/FIENDFIRE.md`, md5 f304db38434bb4364a481c8845aef9ab) for ledger
§759; paths below are on that PC. Diag patch and raw logs stay local.

Setup: new worktree `~/sts-ff-diag` (detached at 79baf6708, the same code as `~/sts-longc-diag`; created with
`tools/agent/worktree.py create --detach`) + the REPORT.md diag patch, extended locally (uncommitted;
`fiendfire/diag_patch_ff.diff`, `fiendfire/diag_live.h`): per-root-child playout endpoint classes, loss-branch
decomposition, the greedy check now excludes Fiend Fire and runs at every logged decision, and `STS_DIAG_EXIT_FLOOR/TURN`
stops the run after floor 44 turn 5. Replay: `fiendfire/replay_ff.sh` (LONG_C it269, salt 269, net-0268, actors_frozen.env,
through `tools/seed_guard.sh`, nice 10, 9.5 s wall). Raw log: `fiendfire/run/stderr.log`.
**Faithfulness:** the floor-44 DIAG decision lines (turns 0–5, all fields except dt_ms) are identical to the original
`shapes/111680130` replay; Silver again plays Fiend Fire → Spiker at turn 4, decision 19.

Engine turns count from 0. "Turn 4" = engine turn 4 (decisions 17–23); Fiend Fire is decision 19.

## 1. State at the turn-4 Fiend Fire root (decision 19)

- **Player:** 17/75 HP, **156 block**, energy 2/3. Powers: Barricade, Dexterity 1, Strength 7, Dark Embrace 2, Demon Form 2,
  Feel No Pain 3. Cards played this turn: 2 (both skills; Second Wind ×2 at decisions 17/18).
- **Relics:** Ceramic Fish, Gambling Chip, Happy Flower, Ornamental Fan, Pen Nib (counter 3), Sacred Bark, Sundial (2),
  Toy Ornithopter. **Potions: none** (2 empty slots; Duplication drunk on turn 0).
- **Hand (10):** Pommel Strike (1), Bash (2), Dramatic Entrance (0), Bludgeon (3, unplayable at 2 E), **Fiend Fire (2)**,
  Anger (0) ×3, Burning Pact (1), Blood for Blood+ (0). None upgraded except Blood for Blood+.
- **Draw pile (2):** Havoc+, Metallicize. **Discard (1):** Second Wind. **Exhaust (26):** 14 Dazed, Ascender's Bane,
  Intimidate, Havoc+ ×2, Dark Embrace, Disarm, Shockwave ×2, Discovery, Shrug It Off ×2, Inflame, Barricade, Spot Weakness.
- **Monsters:** Exploder dead. Repulsor#1 **20/37**, Vulnerable 2, Weak 2, 0 block, intent Repulse.
  **Spiker 53/53, Thorns 11**, Vulnerable 2, Weak 2, 0 block, intent Spike (attack). Repulsor#3 **32/32**, Vulnerable 2,
  Weak 2, 0 block, intent Repulse. No Artifact on any Shape. Total monster HP 105.

## 2. Root children (1000 sims) and 3. playout endpoints

Win score here is ≈74.3 (all wins end at HP 17 around turn 4). "nonwin" columns are the loss-branch terms of
`evaluateEndState` (draw = cardsDrawn·0.03, survival = 1.5·turn only for turn ≤ 100, energy = 0 because Shapes,
potion = 0 because no potions, death-save 0).

| child | visits | mean | win | death | turn-cap (t>500) | undecided @1000 actions | mean end turn | nonwin mean score | dmg | alive | draw | surv |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Fiend Fire → Spiker (chosen)** | **282** | **81.24** | **0** | 0 | 166 | 116 | 452.7 | 81.24 | 24.5 | −6.8 | **63.5** | 0 |
| End Turn | 95 | 77.94 | 84 | 11 | 0 | 0 | 12.6 | **110.8** | 28.3 | −5.3 | 6.9 | **80.9** |
| Burning Pact | 78 | 77.56 | 36 | 36 | 2 | 4 | 57.8 | 80.3 | 25.5 | −4.0 | 10.3 | 48.5 |
| Pommel Strike → Rep#3 | 51 | 75.56 | 41 | 10 | 0 | 0 | 12.6 | 80.5 | 27.2 | −4.8 | 4.8 | 53.3 |
| Pommel → Spiker | 46 | 74.90 | 34 | 5 | 4 | 3 | 85.1 | 76.4 | 29.7 | −4.3 | 31.0 | 20.0 |
| Dramatic Entrance | 44 | 74.90 | 37 | 4 | 0 | 3 | 31.0 | 77.6 | 31.7 | −3.4 | 18.7 | 30.6 |
| Anger → Rep#3 / Spiker / Rep#1 | 41/42/39 | 74.42/74.54/74.20 | 37/36/33 | 4/5/5 | 0 | 0/1/1 | 7–21 | 73.7–75.9 | | | | |
| Blood for Blood+ → Rep#1 / Rep#3 / Spiker | 40/40/39 | 74.31/74.26/74.14 | 38/39/38 | 0 | 0/1/1 | 2/0/0 | 16–29 | 68–74 | | | | |
| Bash → Rep#3 / Spiker / Rep#1 | 39/39/39 | 74.31/74.31/74.30 | **39/39/39** | 0 | 0 | 0 | 4.2 | — | | | | |
| Pommel → Rep#1 | 39 | 74.26 | 34 | 5 | 0 | 0 | 7.6 | 73.6 | | | | |
| Fiend Fire → Rep#3 | 4 | 49.87 | 0 | 0 | 0 | 4 | 251.5 | 49.9 | 19.5 | −6.8 | 37.2 | 0 |
| Fiend Fire → Rep#1 | 3 | 46.03 | 0 | 0 | 0 | 3 | 218.7 | 46.0 | 16.6 | −6.8 | 36.3 | 0 |

Whole search: 1000 playouts, 604 wins, 259 losses (174 turn-cap), 137 undecided. Fiend Fire → Spiker has 0 wins in 282
playouts and the highest mean. Its value is 0 survival + **63.5 draw credit** (≈2100 cards drawn by cycling Havoc+/Dazed over
~450 turns) + 24.5 damage (Spiker kill) − 6.8 alive. That beats every winning line (≈74.3).
End Turn's mean is lifted the same way. Its 11 deaths score 110.8 on average (survival 1.5·turn ≈ 81), above its 84 wins (73.6).

**Mechanism:** at 17 HP the win branch is worth only `53 + 17 − 0.4·turn + …` ≈ 74. The loss branch adds draw credit with
no cap and survival credit up to 150. As a result a turn-cap or action-cap stall (+81) and a slow death (+80–111) both
outrank a clean same-turn win. Silver picks the line with no wins at all. This is the eval inversion noted in REPORT.md,
now visible at the decisive root.

## 4. Turns 0–3: could playouts win?

Yes, every root had many wins (win/1000 playouts): turn 0: 294, 582, 575, 577; turn 1: 530, 706, 680, 556, 817, 869, 880;
turn 2: 903, 925; turn 3: 949, 946, 991; turn 4 before Fiend Fire: 989, 989. After Fiend Fire (decision 20 on): 0 wins.

## 5. Greedy from the turn-4 state, never Fiend Fire, attacks on non-Spikers first (lowest HP)

- At decision 19 (the Fiend Fire root), both variants (attacks only; attacks then any non-Fiend-Fire card) **win on
  turn 4 itself at 17 HP** with 4 attacks (Bash etc. on 20- and 32-HP Repulsors with Str 7, Vulnerable). The same holds
  at decisions 17 and 18 (win on turn 4–5 at 17 HP).
- The search also had these wins: all three Bash children won 39/39 playouts at turn ≈4.2.
- After Fiend Fire, greedy cannot win (0 attacks left; turn-cap loss at 501), which matches the 500-turn stall.

**Conclusion:** the Fiend Fire was not forced, and the rollout policy was not blind to the win: the win was found
(Bash 39/39) and the search rejected it. The cause is the leaf eval. Stalled ends after turn 100 keep draw credit (+63)
and lose no turn penalty, and at low HP that is worth more than a win. STS_SILVER_STALL_LEAF targets exactly this case: the
Fiend Fire child's 282 nonwin playouts all end after turn 100 with HP > 0. Deaths with survival credit (End Turn's 110.8)
are a separate low-HP inversion that the stall leaf does not touch.
