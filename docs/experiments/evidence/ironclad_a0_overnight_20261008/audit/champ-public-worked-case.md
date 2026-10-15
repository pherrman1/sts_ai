# Champ public decision audit: discovery source610081002

This is a concrete local combat audit, not a policy-strength verdict. Source3ed9 reproduces the old736 gameplay exactly when optional-Recall repair is off, and capture does not change it. The public capture (`build/overnight_20261008/corrected_canary/Capture_0.public.jsonl`, SHA256 `0a679ddf01a75eae8186a7c68eda9d6b808decb42c6c2c0457b4c2fc980a4f83`) contains72 valid roots from the Act2 floor33 Champ fight. `champ_public_decisions.json` decodes every hand, intent, legal alternative, chosen fingerprint and search count for reproducible inspection. Turns in the capture are zero-based.

All72 wires have isolatedSearchSeed0, nonconcrete draw piles with canonically sorted unknown multiset, no full draw-order observation, visible intents and zero hidden-intent pending-roll fields. Known top/bottom facts remain available when legitimately observed. Run identity stays outer metadata. The captured Q is the retained child mean, including inherited visits and shared transpositions; it is neither calibrated win probability nor an independent paired counterfactual estimate. Edge and child visit counts can differ. D72 is an unsearched singleton with null Q, which must not be invented as zero-valued search evidence.

## Findings and competing explanations

- **Potion nonuse is disconfirmed for this case.** Skill Potion is drunk atD3, producing Shockwave chosen atD4 and played atD5; Attack Potion is drunk atD7, producing Wild Strike chosen atD8; Gambler's Brew is drunk atD16 and discards Transmutation atD17. All potion slots are empty before turn2 finishes. Timing and offered-card selection remain separate questions.
- **Primary suspicious decision, D13/T1:** HP75, block3, energy1, ChampHP374, strength0, weak2, visible Face Slap. END has Q106.281939 and2052 edge visits; the legal Shrug It Off#14 alternative has Q49.188571 and one visit; Gambler's Brew has Q92.317792 and69visits. The root carries1873 inherited visits and receives only250 new simulations. The hand contains two equivalent unupgraded Shrugs; search merges their action class. Baseline loses6HP byD14. Playing Shrug would add8block against a9damage attack, preventing this immediate loss. However, drawing now changes next-turn card availability; avoiding damage changes Blood for Blood's cost and Self-Forming Clay. Therefore this is **not a proof of whole-combat dominance**. Competing explanations: sparse root exploration, retained-tree/learned-stop interaction, rollout ranking noise, or a real card-timing/resource tradeoff. A frozen END-vs-Shrug public conditional probe is justified.
- **Secondary suspicious resource choices:** D10 ends turn0 with1energy, free Fire Breathing and free Wild Strike legal. The selected END has4123edgevisits; Wild Strike has only one. Wild Strike adds a Wound, so its free damage is not costless. D14 opens the nonattacking Defensive Stance turn with Defend, then Uppercut, Gambler's Brew and Headbutt. Its immediate block has no use against that intent, but the alternative changes the later sequence and Transmutation's energy. These are named candidates, not proven errors.
- **Supported caution around phase change:** D41/T6 ends with free Blood for Blood+ and Anger available while Champ has211/420HP. Executed code switches to Anger after HP becomes strictly below210 (`MonsterSpecific.cpp`). Ending preserves the pre-enrage phase; calling this automatic missed damage would ignore a concrete combat mechanic. Baseline crosses below half during turn7, sees Anger on turn8 and Execute on turn9. Whether earlier burst is better still requires a conditional comparison.
- **Late damage-on-loss concern:** D69–D71 spend all4energy on Uppercut+, Strike and Wild Strike during Execute, with playerHP10 and Champ53HP+25block initially. The resulting known line ends with Champ32HP and no player block, then dies. Shrug is a legal earlier alternative. AtD71, after prior spending, immediate8block alone cannot save10HP from weak Execute24. Legacy terminal value rewards monster damage, survival turns and draws even on loss, so its positive Q45.75 for the fatal Wild Strike is not a45.75% win estimate. This identifies an objective-versus-win-probability hypothesis, but does not establish that an available line wins. The campaign's final-boss binary challenger does not alter this Act2 fight.

## Smallest next probe (design, not launched)

Use the existing Silver wire loader and semantic resolver, not a reconstructed feature row or private snapshot. Freeze D13's raw/public identity and END/Shrug#14 fingerprints before outcomes. Start both interventions from the same legitimately sampled public future, preserving known top/bottom and sampling the unknown multiset on demand through CardPile. Use an independent fixed public search seed and equal exact continuation budgets; never copy the actual continuation RNG streams into search. Fresh-root Silver continuation is explicitly a diagnostic policy because the original retained tree is unavailable. Record actual combat victory, HP, potion use, unresolved/health failures, CPU and all allocated cases. A measured two-pair contract/cost canary followed by at most62 new paired futures stays below64total; no adaptive sample extension and no Act3-strength claim. Any source/helper implementation and game execution requires coordinator protocol review.

## Chronology

| Decision | Turn | HP / block / energy | Champ HP / block | Visible intent | Chosen | New sims / inherited |
|---:|---:|---|---|---|---|---|
| 1 | 0 | 69 / 0 / 5 | 420 / 0 | HEAVY_SLASH | Play Shrug It Off+#18 | 2000 / 0 |
| 2 | 0 | 69 / 11 / 4 | 420 / 0 | HEAVY_SLASH | Play Infernal Blade#23 | 4000 / 116 |
| 3 | 0 | 69 / 11 / 3 | 420 / 0 | HEAVY_SLASH | Drink Skill Potion | 2000 / 137 |
| 4 | 0 | 69 / 11 / 3 | 420 / 0 | HEAVY_SLASH | Select Shockwave (task3) | 4000 / 0 |
| 5 | 0 | 69 / 11 / 3 | 420 / 0 | HEAVY_SLASH | Play Shockwave#26 | 250 / 2764 |
| 6 | 0 | 69 / 11 / 3 | 420 / 0 | HEAVY_SLASH | Play Reaper+#17 | 1000 / 1067 |
| 7 | 0 | 76 / 11 / 1 | 413 / 0 | HEAVY_SLASH | Drink Attack Potion | 2000 / 1503 |
| 8 | 0 | 76 / 11 / 1 | 413 / 0 | HEAVY_SLASH | Select Wild Strike (task3) | 2000 / 0 |
| 9 | 0 | 76 / 11 / 1 | 413 / 0 | HEAVY_SLASH | Play Searing Blow#25 | 1000 / 1556 |
| 10 | 0 | 76 / 11 / 1 | 395 / 0 | HEAVY_SLASH | END | 2000 / 2274 |
| 11 | 1 | 75 / 3 / 4 | 395 / 0 | FACE_SLAP | Play Strike#3 | 2000 / 0 |
| 12 | 1 | 75 / 3 / 3 | 386 / 0 | FACE_SLAP | Play Bash#8 | 250 / 1904 |
| 13 | 1 | 75 / 3 / 1 | 374 / 0 | FACE_SLAP | END | 250 / 1873 |
| 14 | 2 | 69 / 3 / 4 | 374 / 0 | DEFENSIVE_STANCE | Play Defend#7 | 2000 / 0 |
| 15 | 2 | 69 / 6 / 3 | 374 / 0 | DEFENSIVE_STANCE | Play Uppercut+#19 | 500 / 1853 |
| 16 | 2 | 69 / 6 / 1 | 355 / 0 | DEFENSIVE_STANCE | Drink Gamblers Brew | 250 / 2205 |
| 17 | 2 | 69 / 6 / 1 | 355 / 0 | DEFENSIVE_STANCE | Select [Transmutation#22] (task9) | 2000 / 2410 |
| 18 | 2 | 69 / 6 / 1 | 355 / 0 | DEFENSIVE_STANCE | Play Headbutt#15 | 250 / 718 |
| 19 | 2 | 69 / 6 / 0 | 342 / 0 | DEFENSIVE_STANCE | Select Shrug It Off+#18 (task10) | 1000 / 960 |
| 20 | 2 | 69 / 6 / 0 | 342 / 0 | DEFENSIVE_STANCE | END | 0 / 873 |
| 21 | 3 | 69 / 0 / 4 | 342 / 20 | TAUNT | Play Anger#20 | 2000 / 184 |
| 22 | 3 | 69 / 0 / 4 | 342 / 11 | TAUNT | Play Shrug It Off+#18 | 250 / 2085 |
| 23 | 3 | 69 / 8 / 3 | 342 / 11 | TAUNT | Play Headbutt+#10 | 250 / 2343 |
| 24 | 3 | 69 / 8 / 2 | 335 / 0 | TAUNT | Select Anger#28 (task10) | 10000 / 2563 |
| 25 | 3 | 69 / 8 / 2 | 335 / 0 | TAUNT | Play Strike#0 | 250 / 5669 |
| 26 | 3 | 69 / 8 / 1 | 326 / 0 | TAUNT | Play Blood for Blood+#9 | 250 / 5317 |
| 27 | 3 | 69 / 8 / 0 | 293 / 0 | TAUNT | END | 0 / 5810 |
| 28 | 4 | 69 / 0 / 4 | 293 / 5 | FACE_SLAP | Play Strike#2 | 4000 / 0 |
| 29 | 4 | 69 / 0 / 3 | 289 / 0 | FACE_SLAP | Play Shrug It Off#12 | 250 / 2277 |
| 30 | 4 | 69 / 8 / 2 | 289 / 0 | FACE_SLAP | Play Bash#8 | 2000 / 152 |
| 31 | 4 | 69 / 8 / 0 | 277 / 0 | FACE_SLAP | Play Anger#28 | 250 / 1523 |
| 32 | 4 | 69 / 8 / 0 | 268 / 0 | FACE_SLAP | Play Clash#13 | 250 / 1696 |
| 33 | 4 | 69 / 8 / 0 | 247 / 0 | FACE_SLAP | END | 0 / 1950 |
| 34 | 5 | 64 / 3 / 4 | 247 / 5 | HEAVY_SLASH | Play Defend#5 | 1000 / 0 |
| 35 | 5 | 64 / 6 / 3 | 247 / 5 | HEAVY_SLASH | Play Uppercut+#19 | 1000 / 964 |
| 36 | 5 | 64 / 6 / 1 | 233 / 0 | HEAVY_SLASH | Play Strike#0 | 2000 / 1933 |
| 37 | 5 | 64 / 6 / 0 | 224 / 0 | HEAVY_SLASH | END | 0 / 3950 |
| 38 | 6 | 52 / 3 / 4 | 224 / 5 | FACE_SLAP | Play Shrug It Off#14 | 4000 / 0 |
| 39 | 6 | 52 / 9 / 3 | 224 / 5 | FACE_SLAP | Play Wild Strike#27 | 2000 / 382 |
| 40 | 6 | 52 / 9 / 2 | 211 / 0 | FACE_SLAP | Play Defend#7 | 2000 / 3 |
| 41 | 6 | 52 / 12 / 1 | 211 / 0 | FACE_SLAP | END | 250 / 1916 |
| 42 | 7 | 51 / 3 / 4 | 211 / 5 | TAUNT | Play Shrug It Off+#18 | 2000 / 1 |
| 43 | 7 | 51 / 11 / 3 | 211 / 5 | TAUNT | Play Searing Blow#25 | 1000 / 362 |
| 44 | 7 | 51 / 11 / 1 | 198 / 0 | TAUNT | Play Strike#3 | 500 / 1320 |
| 45 | 7 | 51 / 11 / 0 | 189 / 0 | TAUNT | END | 0 / 1692 |
| 46 | 8 | 51 / 0 / 4 | 189 / 5 | ANGER | Play Transmutation#22 | 500 / 57 |
| 47 | 8 | 51 / 0 / 0 | 189 / 5 | ANGER | Play Anger#20 | 8000 / 0 |
| 48 | 8 | 51 / 0 / 0 | 185 / 0 | ANGER | Play Forethought#33 | 250 / 4919 |
| 49 | 8 | 51 / 0 / 0 | 185 / 0 | ANGER | Select Wound#30 (task8) | 1000 / 4277 |
| 50 | 8 | 51 / 0 / 0 | 185 / 0 | ANGER | Play Hand of Greed#32 | 250 / 4386 |
| 51 | 8 | 51 / 0 / 0 | 155 / 0 | ANGER | END | 250 / 4478 |
| 52 | 9 | 51 / 0 / 4 | 155 / 5 | EXECUTE | Play Flame Barrier+#11 | 1000 / 0 |
| 53 | 9 | 51 / 16 / 2 | 155 / 5 | EXECUTE | Play Headbutt#15 | 1000 / 777 |
| 54 | 9 | 51 / 16 / 1 | 151 / 0 | EXECUTE | Select Anger#35 (task10) | 8000 / 1429 |
| 55 | 9 | 51 / 16 / 1 | 151 / 0 | EXECUTE | Play Defend#6 | 250 / 5493 |
| 56 | 9 | 51 / 21 / 0 | 151 / 0 | EXECUTE | Play Clash#13 | 250 / 5630 |
| 57 | 9 | 51 / 21 / 0 | 137 / 0 | EXECUTE | END | 0 / 5531 |
| 58 | 10 | 24 / 6 / 4 | 125 / 5 | HEAVY_SLASH | Play Shrug It Off#12 | 10000 / 0 |
| 59 | 10 | 24 / 14 / 3 | 125 / 5 | HEAVY_SLASH | Play Perfected Strike+#16 | 8000 / 203 |
| 60 | 10 | 24 / 14 / 1 | 106 / 0 | HEAVY_SLASH | Play Defend#7 | 250 / 5972 |
| 61 | 10 | 24 / 19 / 0 | 106 / 0 | HEAVY_SLASH | Play Anger#35 | 250 / 5262 |
| 62 | 10 | 24 / 19 / 0 | 100 / 0 | HEAVY_SLASH | Play Blood for Blood+#9 | 250 / 4738 |
| 63 | 10 | 24 / 19 / 0 | 78 / 0 | HEAVY_SLASH | END | 0 / 6416 |
| 64 | 11 | 10 / 3 / 4 | 78 / 5 | DEFENSIVE_STANCE | Play Shockwave+#21 | 10000 / 0 |
| 65 | 11 | 10 / 3 / 2 | 78 / 5 | DEFENSIVE_STANCE | Play Bash#8 | 8000 / 3332 |
| 66 | 11 | 10 / 3 / 0 | 71 / 0 | DEFENSIVE_STANCE | Play Anger#29 | 250 / 5629 |
| 67 | 11 | 10 / 3 / 0 | 62 / 0 | DEFENSIVE_STANCE | Play Anger#28 | 1000 / 6320 |
| 68 | 11 | 10 / 3 / 0 | 53 / 0 | DEFENSIVE_STANCE | END | 0 / 5796 |
| 69 | 12 | 10 / 0 / 4 | 53 / 25 | EXECUTE | Play Uppercut+#19 | 8000 / 109 |
| 70 | 12 | 10 / 0 / 2 | 53 / 6 | EXECUTE | Play Strike#1 | 8000 / 3360 |
| 71 | 12 | 10 / 0 / 1 | 50 / 0 | EXECUTE | Play Wild Strike#27 | 250 / 5400 |
| 72 | 12 | 10 / 0 / 0 | 32 / 0 | EXECUTE | END | 0 / 0 |

Knowledge impact: local combat evidence and competing hypotheses. No general policy repair, causal win improvement, or production-default change is established.


## Frozen D13 continuation result

The bounded probe completed all 62 newly allocated evaluation futures (124 branches), excluding both cost-canary pairs. The independent reviewer reran frozen custody and strict analysis, rehashed every input, and reproduced report SHA256 `269b1e792395de0c1d97cd5af2ae1d5ced2a2a65c436b651fd627bcd74da86c3` exactly. END won 51/62 and Shrug It Off uniqueId14 won 50/62. Nine futures favored Shrug and ten favored END; 41 won under both and two lost under both. Shrug minus END was -1.61 percentage points, with paired 95% bootstrap interval [-14.52, +11.29] points. The preregistered verdict is **LOCAL_CONDITIONAL_INCONCLUSIVE**; no sample extension follows.

The one-step fixture verifies the immediate six-HP saving, but that local benefit did not establish a fight-win improvement. Draw timing, exhaust/resource interactions and continuation choices can change downstream consequences. This result neither proves the historical action was a policy error or a search limitation nor proves END was intentionally optimal. The historical tree's highly unequal root visits remain an observed fact rather than an established cause of loss.

All 62.13 million completed continuation-search endpoints were normal victories or deaths, with zero turn-limit, engine-stop or nonterminal health errors. Actual branches completed normally. Measured branch CPU was 264.49 seconds for END and 308.44 for Shrug; invocation wall time totaled575.80 seconds. Those checks establish the supported execution contract, not policy quality.

This is one outcome-informed historical public root, not62 independent decision states. Each continuation used a fresh exact10,000-step public-information search with seed0; the original retained-tree learned-stop controller was unavailable. Both actions shared independently sampled legitimate public futures, without the historical hidden RNG. The contrast therefore diagnoses this fixed conditional continuation policy only and makes no Act-3 population-strength or production-promotion claim. Raw terminal HP/potion diagnostics remain in the branch records; no survivor-only resource average is substituted for the primary combat-win endpoint.
