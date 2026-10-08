# GEN2 fixed32-source primary result

**LOCAL_CONDITIONAL_INCONCLUSIVE.** The frozen rollout-selection rule changed19 of63 retained decisions. Its independent evaluation gain was **−1.171875 percentage points**, with a source-cluster95% bootstrap interval **[−5.46875,+3.125] points**. It meets neither the preregistered positive rule (mean at least2points and lower bound above0) nor the negative rule (upper bound below0).

| Frozen rule | Role | Changed decisions | Equal-source gain | Source-cluster95% interval |
|---|---|---:|---:|---:|
| Rollout k0–3 | Primary | 19/63 | −1.171875pp | [−5.46875,+3.125]pp |
| Historical P0-s0 | Exploratory secondary | 33/63 | +0.390625pp | [−4.296875,+5.46875]pp |
| Historical F2-s0 | Exploratory secondary | 34/63 | −0.78125pp | [−5.078125,+3.125]pp |

The secondary figures do not select a best rule or establish superiority. Exactly32 allocated sources610084100..131 remain in the equal-source endpoint; states are averaged within source before source-cluster resampling. The63 retained states comprise32 CARD_REWARD and31 BOSS_RELIC decisions. One source has one state and the other31 have two. All1968 retained option×future branches and MAP joins passed; no negative branch, failed source or missing sibling was omitted.

The frozen producer remains3ed91ab3 with public8 scoring, optional-Recall exclusion, learned-stop continuation and Act3 cutoff. No later FullHp, removal or card-ranking experiment changes this collection. Cost was392.094290 source CPU seconds plus14550.502842 branch CPU seconds: **4.15072 core-hours**. Sum of invocation wall times was14956.732568 seconds; this is aggregate process wall time, not dispatcher elapsed time. The456152 tree-profile rows passed seed-custody and budget/error gates. Profiles combine source and continuations; without a branch-ID tag they cannot prove profile coverage separately for every sibling.

The immutable sequence is contract validation, selection onk0–3, choice serialization and hashing, then a separate evaluation invocation onk4–7. Each command and before/after timestamp is saved in `gen2_tranche32_3ed9/{contract,selection,evaluation}_invocation.json`; `primary_execution_receipt.json` verifies ordering. Frozen tools, model bytes, source allocation, choices and decision rule remained unchanged.

- Contract: `gen2_tranche32_3ed9/contract_receipt.json`, SHA256 `dec269de73abb320cf926e8e3891bbbdb74205521658849e23f8783ac217aa70`.
- Frozen choices: `gen2_tranche32_3ed9_choices.json`, SHA256 `0f7f79637cc1bce3fccb306e39d32c91e97539d75ebb970de6efc27416e923f7`.
- Primary evaluation: `gen2_tranche32_3ed9_evaluation.json`, SHA256 `5ada874a05f6d947cf0a19435db681a01be89aa23b26ceb26b5c59414aff798f`.

This is conditional action-value evidence for the retained decisions under the existing future sampler and teacher, not a whole-run policy experiment. The sampler preserves latent counters and pool membership, so it is not an exact posterior of player-visible information. Historical P0/F2 contain latent-counter inputs and privileged-teacher label history despite omitting four hidden encounter-queue features; arithmetic/native parity is not deployment qualification. Neither these models nor the rollout selector was trained or installed. The four-source canary was not pooled; protected TEST and final confirmation remain outside this analysis.

The separately specified post-primary diagnostics are exploratory and cannot revise this result, frozen choices or advancement rules.
