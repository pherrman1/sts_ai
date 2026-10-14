# Situational Silver leaf evaluation

**Status:** open (one candidate tested, others unverified). **Last verified:** 2026-10-14 against `8d8eeb3c`.

## Symptom and scope

Silver's terminal score (`SilverSearcher::evaluateEndState`) uses fixed weights: victory
`53 + healedHp + 11·potions − 0.4·turn + deathSave + 0.25·Δgold + 2·ΔmaxHp`, loss
`37·damage ratio − 3.4·alive − 1.75·energy wasted + 0.03·draws + 5.5·potions + 1.5·turns + deathSave`.
The question is which run circumstances make parts of that score meaningless.

## Findings

- **Post-boss heal is already modeled.** `GameContext::transitionToAct` heals to full at A0–A4 and
  `round(0.75·(maxHp − curHp))` at A5+; `postBattleHealedHp` applies it in the act-boss room. At A0
  HP after any act boss (including the final act-3 boss) already has no value; at A5+ one HP there
  is worth 0.25.
- **Final-fight potion credit (tested, §466 NOT_SHOWN).** `STS_SILVER_FINAL_FIGHT_LEAF=1` removes
  post-fight value in the run-ending fight. Potions held at act-3 boss deaths fell 105/258 → 0/257,
  but the win rate did not move (+0.05 pp [−1.27, +1.38], 236 fights, exact 10k, A0).
- **A20 first act-3 boss heal mis-credit (Unverified effect).** At A20 the engine enters the second
  boss directly after the first (`GameContext.cpp`, act-3 `ascension >= 20` branch), but
  `postBattleHealedHp` credits the 75% heal after the first boss too, so HP there counts at a
  quarter. The live wire path sets `actBossRoom` from `isBossEncounter` and has the same issue.
  Next check: a fix crediting the heal only when the act transition follows, with an A20 test.
- **Loss-branch potion credit in every fight (Inference).** 30/55 exact-10k deaths in the §460
  replays held potions. §466 suggests held potions rarely decide a loss; low priority.
- **Burning Blood / Black Blood / Meat on the Bone (Inference).** Victory HP is scored before
  post-combat relic heals; 60–75% of won hallway fights end within 6 HP of max (3–4 HP per win
  credited that the relic would restore). Small expected effect.
- **Eliminated / not proposed:** dynamic potion keep-value before hard fights (ledger-02, §35,
  `STS_POTION_SAVE`: −3..−9 pp); v_win terminal pricing (§385, −8.6 pp); HP before a rest site
  (needs route knowledge the leaf lacks).

## Reproduction

§466 evidence packet `docs/experiments/evidence/silver_final_fight_leaf_466_20261014/`
(`ctmsilvergen`, `STS_CTMSILVER_ARMSET=finalleaf`). Descriptive §460 statistics came from
`/mnt/project-files/silver-az-mlp/gen3-eval/w*.tar`.

## Relevant code

- `src/sim/search/SilverSearcher.cpp` — `evaluateEndState`, `postBattleHealedHp`.
- `src/sim/search/NativeSilverBackend.cpp` — `SilverSearchContext` construction, run-ending test.
- `src/sim/search/SilverWireState.cpp` — `searchContextFromWire` (live path).
- `apps/one_combat/combat_datasets.cpp` — `ctmSilverCompareGen`, arm set `finalleaf`.
