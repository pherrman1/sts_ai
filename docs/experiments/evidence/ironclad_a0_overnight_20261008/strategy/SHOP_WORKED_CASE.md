# Actual shop ranking changed by the deck-size repair

**Worked case: discovery seed610081023, act1 floor10.** This is an outcome-informed forensic comparison of frozen wave1 Fprod and ShopFix, selected because the paired outcomes differed. The mechanical finding is that correcting the removal candidate's deck-size feature changed a real native fallback decision. It does not establish that the first purchase alone caused the eventual win.

## Matched root and decision owner

Both runs used source `736d1ff7e61725d9c6a50326064b2e3060ce6ae4`, binary `3f69f5fd251ac699580bca8eb8da707282c77bc5263732f10e83f8e2670aba2d`, public futures8 and identical model custody. Their complete effective environments differ only in `STS_OOC_SHOP_DECK_SIZE_FIX=0` versus1 after excluding diagnostic output paths. Completed invocation receipts bind every input hash. A separate read-only custody check confirmed that all four inspected receipts bind the exact wave1 manifest and that its immutable executable and all model/stop-source artifact hashes still match.

The first36 serialized trace events are exactly equal. All37 preceding combat-profile records are equal after excluding the process-global diagnostic `combat_id`. There was **no earlier shop root** in either trajectory. The first difference is the `post` object at line646 in both `Fprod_5.trace.jsonl` and `ShopFix_5.trace.jsonl`, traceidx31. Every serialized public `pre` field and the entire published shop offer are exactly equal: HP72/72, gold136, deck13, potion Fire Potion, relics Burning Blood/Thread and Needle/Bag of Marbles.

This equality is exact for the recorded public schema. That schema omits relic counters, card misc/bottles and full map details, so it is not a complete GameContext fingerprint. The identical preceding behavior and absence of prior shop use support the deterministic same-root interpretation; no state was reconstructed or treated as an exact replay snapshot.

The V4 SHOP record at Fprod strategic CSV line190 and ShopFix line192 is identical before outcome columns: margin `0.781441 < 1.0`, `owned=0`, `takeIdx=-1`, and the same ten action scores. The V4 gate declined both times. The active native floor fallback therefore made the divergent purchase. Relevant routing is `oocOnePlyShopPolicy` → `shopVPolicy` → `nativeFloorShopStep` → `nativeShopPlan`.

## What changed in the actual shop

| Stage | Fprod / legacy features | ShopFix / corrected features |
|---|---|---|
| First decision | Buy Wild Strike for51; gold85, deck14 | Pay75 for removal; gold61, selector opens |
| Removal | Remove one Defend after buying Wild Strike | Remove one Defend immediately |
| Shop exit | Deck13, gold10; added Wild Strike, removed Defend | Deck12, gold61; removed Defend, no purchase |

Fprod's sequence is trace lines646–649. ShopFix's sequence is lines646–648. Both then choose the same next map node; later states and combat behavior can diverge.

All three offered relics are **unaffordable at the shared root**: Pocketwatch304, Bottled Flame242, Chemical X149, versus136 gold. Consequently, no legal native bundle can contain a relic. This rules out the separate relic-as-card counting term as the explanation here. The only repair term that can alter a feasible candidate is the missing removal decrement:

| Hypothetical bundle at the shared root | Legacy `deckSize` | Corrected / actual `deckSize` | Gold after |
|---|---:|---:|---:|
| Remove only | 13 | 12 | 61 |
| Wild Strike only | 14 | 14 | 85 |
| Wild Strike + remove | 14 | 13 | 10 |

The card-count feature for the planner's selected removal target already decremented in both variants; the legacy aggregate deck size failed to follow it. The removal-target prepass already used a decremented deck size too, so its feature contract disagreed with the final bundle comparison. S01 fixes that disagreement.

`nativeFloorShopStep` executes the first token of the recomputed best bundle. Native plans emit purchases before removal. Therefore ShopFix's first removal proves its winning root bundle had no purchase tokens: removal-only became the selected bundle. Legacy's first Wild Strike proves its selected bundle included that card; its other initially planned tokens are **unlogged**, and the subsequent removal follows a fresh evaluation. Native floor prediction values are also unlogged, so no numerical native score margin or complete initial legacy plan is claimed.

## Outcome and limits

The recorded legacy trajectory loses at floor50, while ShopFix wins the Act-3 objective and ends with35 HP. This is a realized paired outcome, not a probability estimate or proof that buying Wild Strike was independently fatal. Remaining shops, combat decisions, RNG consumption and later choices can all differ after the first decision. The fact that RestOff also rescues this source further cautions against treating one early action as the unique cause.

A secondary matched case, seed610081002, first differs at both shard0 trace line487, act2 floor28: legacy buys Anger49 while ShopFix buys Shockwave41. Its first104 trace events and all preceding combat profiles match; the root offers affordable relics, so it does not isolate the two S01 subterms as cleanly. Its detailed locators are retained for completeness, not used as stronger causal evidence.

Machine evidence is `SHOP_WORKED_CASE.json` (SHA256 `f74cee8767b471bc34a3a38281440d01f4baa6d8478eb099a380a64bd34dafe9`). It includes input file/receipt hashes, exact equality checks, common-state hashes, source/binary identities and the policy environment difference, strategic records, local action chains and outcomes. `analyze_shop_worked_case.py` reproduces these checks using existing files only and refuses to overwrite its report. It executes no game seeds and fits no model.

Knowledge impact: worked experimental evidence supporting the already tested feature repair; no additional implementation or production-default change. The larger corrected-policy development and reserved confirmation cohorts decide any strength claim.
