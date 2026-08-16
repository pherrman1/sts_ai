# E2b masked feature availability

- **Date:** 2026-08-17
- **Context:** E2b offline ablation of `build/vrich.csv`.
- **Decision:** Use all represented card-reward rows and compare `B1`, `T-full`,
  `T-fair`, and `T-masked`. Exclude verified future encounter/forward-map
  families. Exclude direct reward-mutated fields (gold, potion state, card
  rarity, keys, relic ownership/counters) and reward-induced side effects
  (HP/max HP, deck composition/upgrades, bottles, potion capacity). Do not run
  a counter arm.
- **Rationale:** **Verified:** `apps/one_combat.cpp::richHeader/richRow` emits
  future encounter fields, forward-map fields, relic ownership plus counters,
  potions, and gold. **Verified:** `runFullRun` processes `GOLD`, `RELIC`, and
  `POTION` after `BattleContext::exitBattle`. **Verified:** the existing schema
  has no room/encounter identifier. Therefore ordinary-combat filtering and
  exact raw-terminal confirmation are not defensible from E2 rows.
- **Interpretation:** The verdict is `MASKED SUPPORT`, `MASKED INCONCLUSIVE`, or
  `MASKED NEGATIVE`, never the original exact-leaf `STRONG SUPPORT`. The
  corrected result is `MASKED NEGATIVE`: the strict all-row mask leaves only
  eight varying features and performs worse than B1. This does not prove a raw
  terminal critic impossible because masking may remove legitimate pre-existing
  resource state.
- **Counter status:** `NOT TESTABLE FROM E2 DATASET`; `r*` encodes presence plus
  counter and post-reward pickup can add relics, so no clean cross-combat counter
  set is identifiable.
- **Corrected result:** the manifest has 9 hidden/future, 236 direct reward-
  mutated, 751 reward-induced side-effect, and 9 fair/stable schema features;
  8 of the latter vary in the dataset. T-masked has AUC `0.611091`, log loss
  `0.613848`, Brier `0.211795`, ECE `0.002156`, and masked retention
  `-0.310800`. The verdict is **MASKED NEGATIVE**. Its T-masked−B1 log-loss
  bootstrap mean is `+0.018650`, 95% CI `[+0.016415,+0.020872]`.
- **Follow-up:** E2c raw-boundary collection remains scientifically worthwhile
  because the negative result is confounded by conservative removal of fields
  that cannot be disentangled from post-reward mutations in E2 rows.