# Ironclad CTM support: which states are modeled, refused, or overridden (2026-10-17)

Source: `apps/one_combat/combat_transition_native_contract.cpp` (`nativeComposedSupportReasons`, `legal`),
`apps/one_combat/combat_transition_runtime.cpp` (active-Lizard wrapper, Brew routing), artifact headers in
`selfplay/models/`, and `apps/one_combat/ooc_mcts_adapter.cpp`. The same native runtime serves sts_lightspeed OOC
MCTS and the live mod advisor.

## What happens on a refusal

The CTM refuses an imagined combat → `OocSearchUnsupported` → the **whole OOC MCTS search for that decision is
aborted** (partial visits discarded, `OocMctsPlanner.cpp:285`) and the V4 policy makes the decision instead.
Silver playing the refused combats (`STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS=N`, #583) is **opt-in and off by
default**; neither the live mod (`tools/live_game_runtime.py`) nor the A/B arms set it. Real combats are always
played by Silver; only imagined (planning) combats use the CTM.

## Stacks

| Stack | Used for | Artifacts (fast / Brew fallback) |
|---|---|---|
| A0 deployed `pathb-r2` | ascension < 20, automatic + live | `c6d56bbc…` / `b9188de0…` |
| A0 candidate `pathb-r2-ritual-refit` | opt-in research candidate only | `3bbff6b6…` / `2f0f5d97…` |
| A20 `pathb-a20` | ascension 20, automatic + live | `ae785ec2…` / `e338506d…` |

All three are "near-full" escape-capable stacks with active-Lizard correction and the `lizardFairy`/`lizardBrew`
capabilities on the fast artifact. Brew-holding states route to the standard (fallback) artifact.

## Refused states (Ironclad)

| Refusal reason | State | A0 deployed | A0 candidate | A20 |
|---|---|---|---|---|
| `writhing_ritual_intersection` | Writhing Mass fight with a Ritual Dagger in the deck | **refused** (≈0.27% of corpus fights) | supported | supported |
| `pre_smoke_bomb_used` | a Smoke Bomb already used before this combat's state (escape flag set) | refused | refused | refused |
| `potion_not_certified` | Alchemize in the deck | refused | refused | refused |
| `hp_envelope` | curHp > 220 or maxHp outside 24–220 | refused | refused | refused |
| `mark_of_bloom_exact_path` | active Lizard Tail together with Mark of the Bloom | refused | refused | refused |
| `boss_leaf_unsupported_<id>` | a boss leaf estimate that hits any refusal above | refused | refused | refused |
| `non_ironclad`, `invalid_pre_state`, `visible_*_mismatch`, `potion_count`, `inherited_rng`, `invalid_relic_counter`, `untrained_trajectory`, `max_hp_*`, `active_lizard_*` state/parameter checks | malformed, non-Ironclad or internally inconsistent inputs (guards, not game situations) | refused | refused | refused |

Everything else is supported, including:
- gold-changing encounters (Looters, Thieves, Thugs);
- Hand of Greed, Jack of All Trades and Transmutation;
- Toolbox;
- Colorless Potion;
- Entropic Brew (via the fallback);
- Smoke Bomb held (escape head);
- Ritual Dagger outside Writhing, and Writhing without a Dagger;
- active Lizard Tail with Fairy or Brew.

On the frozen 537k-fight corpus census, the deployed A0 stack supports everything except
`writhing_ritual_intersection` (1,431 rows). The census also lists `smoke_bomb` (4,192 rows), which the escape
capability has since lifted. The census does not measure the guard rows or `pre_smoke_bomb_used`.

## Qualification overrides in what is used

| Where | What was overridden | Record |
|---|---|---|
| A0 candidate `pathb-r2-ritual-refit` (opt-in only) | §507 criterion 4: the non-Writhing no-regression CI upper bound was +0.0107 against a +0.005 limit, though the point estimate improved | `decision.json` (Philipp, 2026-10-17) |
| A0 deployed fast `c6d56bbc…` (the default) | its DeepSets downstream heads (Ritual/Writhing/gold/relic) were `DEEPSET_DOWNSTREAM_REJECTED` on conditional VALIDATION; waived failure: cards singleton exact-label accuracy drop > 0.5 pp | `s19-override.json` `a2d28af3…`, see `ctm_ritual_validation_20261017/custody.json` |
| A20 `pathb-a20` (the default at A20) | exposure gate passed only `BY_OVERRIDE`, waived slices `hp.recursiveBrew` and `writhing.transmutationPlus` | `exposureOverrideSha256` `b89b7f18…` in both headers |
| A20 `pathb-a20` | `writhingRitual` granted with no cohort gate ("too few rows") | ledger-06 §458 |
| A20 `pathb-a20` Lizard r refit | criterion 2 failed as written; Philipp chose "Rerun anyway" for a research arm | ledger-06 §458 |

The deployed A0 standard artifact `b9188de0…` passed its exposure gate without override
(`FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS`).
