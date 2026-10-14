# Situational Silver leaf evaluation

**Status:** open (four candidates implemented, tested alone (§466), as a bundle (§468) and the end-of-run pair (§474)). **Last verified:** 2026-10-14
against `f41ec4d3`.

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
- **A20 first act-3 boss heal mis-credit (fixed, default on).** At A20 the engine enters the second
  boss directly after the first (`GameContext.cpp`, act-3 `ascension >= 20` branch), but
  `postBattleHealedHp` credited the 75% heal after the first boss too. `SilverSearchContext::actHealFollows`
  now removes that credit (native `STS_SILVER_A20_BOSS_HEAL_FIX=0` restores it; the wire path always fixes it).
- **Loss-branch potion credit in every fight (`STS_SILVER_NO_LOSS_POTION_CREDIT=1`, opt-in).** 30/55
  exact-10k deaths in the §460 replays held potions.
- **Burning Blood / Black Blood / Meat on the Bone (`STS_SILVER_RELIC_HEAL_LEAF=1`, opt-in).** Victory
  HP is scored after the post-combat relic heals, capped at max HP.
- **Bundle of all four (§468, whole runs, 500 paired seeds each).** A0 Δwin −2.6 pp [−6.4, +1.2]
  NOT_SHOWN; A20 Δfloor −1.29 [−2.42, −0.19] WORSE, but A20 wins 52 → 71 (+3.8 pp [+0.6, +7.0]).
  The A20 bundle dies more in act 1 (paired 50 vs 26) and less at the final bosses. **Inference:**
  the every-fight terms (loss potion credit, relic heal) cost early fights, the end-of-run terms
  (heal fix, final-fight leaf) help at the A20 final bosses. **Open question:** the terms were not
  tested separately.
- **End-of-run parts alone (§474, 500 paired seeds each).** Heal fix + final-fight leaf vs legacy:
  A0 Δwin +0.8 pp [−1.2, +3.0], A20 Δfloor 0.00 (wins 42 → 47), both NOT_SHOWN; play is identical
  before floor 50. So the §468 act-1 losses came from the every-fight terms. The heal fix stays
  default on; the three opt-ins stay off.
- **Eliminated / not proposed:** dynamic potion keep-value before hard fights (ledger-02, §35,
  `STS_POTION_SAVE`: −3..−9 pp); v_win terminal pricing (§385, −8.6 pp); HP before a rest site
  (needs route knowledge the leaf lacks).

## Reproduction

§466 evidence packet `docs/experiments/evidence/silver_final_fight_leaf_466_20261014/`; §468 and §474 evidence
packets `docs/experiments/evidence/silver_leaf_combo_468_20261014/`, `silver_leaf_split_471_20261014/` (bestbench whole runs);
(`ctmsilvergen`, `STS_CTMSILVER_ARMSET=finalleaf`). Descriptive §460 statistics came from
`/mnt/project-files/silver-az-mlp/gen3-eval/w*.tar`.

## Relevant code

- `src/sim/search/SilverSearcher.cpp` — `evaluateEndState`, `postBattleHealedHp`.
- `src/sim/search/NativeSilverBackend.cpp` — `SilverSearchContext` construction, run-ending test.
- `src/sim/search/SilverWireState.cpp` — `searchContextFromWire` (live path).
- `apps/one_combat/combat_datasets.cpp` — `ctmSilverCompareGen`, arm set `finalleaf`.
