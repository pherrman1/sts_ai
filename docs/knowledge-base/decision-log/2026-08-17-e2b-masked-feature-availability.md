# E2b masked feature availability

- **Date:** 2026-08-17
- **Context:** E2b offline ablation of `build/vrich.csv`.
- **Decision:** Use all represented card-reward rows and compare `B1`, `T-full`,
  `T-fair`, and `T-masked`. Exclude verified future encounter/forward-map
  families, then exclude gold, potion, relic ownership/counter families, and
  unclassified features. Do not run a counter arm.
- **Rationale:** **Verified:** `apps/one_combat.cpp::richHeader/richRow` emits
  future encounter fields, forward-map fields, relic ownership plus counters,
  potions, and gold. **Verified:** `runFullRun` processes `GOLD`, `RELIC`, and
  `POTION` after `BattleContext::exitBattle`. **Verified:** the existing schema
  has no room/encounter identifier. Therefore ordinary-combat filtering and
  exact raw-terminal confirmation are not defensible from E2 rows.
- **Interpretation:** The verdict is `MASKED SUPPORT`, `MASKED INCONCLUSIVE`, or
  `MASKED NEGATIVE`, never the original exact-leaf `STRONG SUPPORT`. A positive
  result means signal survives conservative masking of known hidden/future and
  reward-mutated fields, not that exact raw-terminal calibration is established.
- **Counter status:** `NOT TESTABLE FROM E2 DATASET`; `r*` encodes presence plus
  counter and post-reward pickup can add relics, so no clean cross-combat counter
  set is identifiable.
- **Follow-up:** E2c raw-boundary collection is justified according to the
  masked verdict and the preregistered interpretation rule.