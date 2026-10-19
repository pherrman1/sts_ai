# #401 Stage 1: grouped permutation importance, A20 CTM fast DeepSets child (`ctm_a20`)

Analysis only: no seeds, no `one_combat` runs, nothing tracked changed. Style follows §438.

## Provenance
- **Artifact:** `selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native`, sha256 `ae785ec2…` (FAST4L, `pathb-a20`, data branch c507cebb / 6faa5695). Survival component checkpoint `c3162761…`. Loaded with the repo's `tools/ctm_artifact_torch.py` (main b5dd5557), FP32 CPU, 1 torch thread.
- **Standard child** `e338506d…`: used only for parity (Brew rows), not audited. Its Attention encoders take about 6.5 min per pass.
- **Data:** Stage 1 tars (`/mnt/project-files/ctm-a20/stage1/`, the same files as `claude/ctm-a20-data` `ctm-a20-stage1/`).
- **Split:** VALIDATION under `split_for_seed("combat-transition-model-v1:{seed}")`, the #418 source-seed split the artifact was trained on. TEST rows were dropped at extraction and never written. Stalled-unit reruns were handled as in §470 `extract.py`.
- **Main corpus:** 59,282 rows from 3,124 seeds, the same set §470 scored. Forced-slice rows were not used.
- **Importance set:** 57,790 rows served directly by the fast child. Excluded: 392 Entropic Brew rows (sent to the standard child) and 1,110 active-Lizard rows (composed q·r). Acts 1/2/3: 27,513 / 18,493 / 11,784.
- **No Act-4 rows exist in the Stage 1 corpus.** Act-4 survival (Heart, Shield and Spear) is priced in play by the §527 GBT, so this audit says nothing about Act 4.
- **Scripts:** `extract_val.py` → `encode.py` (the repo's `_encode_row`) → `parity.py` → `perm.py` → `tables.py`; sha256s in `results.json`. A container restart killed the first run; the rerun reproduced every completed item exactly.

## Step 1 parity: PASS (exact)
No Stage 2 training log for this child exists in the repo or on the share. The target is therefore the deployed stack's own native VALIDATION scoring in §470 `fit-validation.json` (`ctmscorerows`, LIZARD=1, the same 59,282 rows), reproduced in Torch with the same Brew routing and Lizard composition:
- Boss NLL 0.3046648 (Torch) vs 0.3046648 (native).
- Death bias by room, normal / elite / boss: −0.0011019 / +0.0041747 / +0.0193059 in both, equal to ≤ 1e-9.
- Calibrated version: boss bias −1.95e-5 and NLL 0.3028974, matching `fit-validation-recheck.json`.

## Baseline
Importance set, with the deployed §470 boss shift applied:
- Survival BCE 0.0779 (primary), Brier 0.0230, AUC 0.974. Death rate 0.047, mean predicted death 0.048.
- Survival BCE by act 1/2/3: 0.040 / 0.096 / 0.137.
- HP-class CE 2.930; win-HP MAE 7.14 HP (55,047 wins).
- MaxHP-delta CE 0.101. Potion-mask CE 0.383 (54,642 rows).

## Method
- **Groups:** the field mapping is in `results.json` under `groups_mapping`. Each repeat uses one row permutation shared by every column of a group, so whole token blocks move together: the card set with its mask, the relic set with its mask, the 5 potion slots.
- **Repeats:** 5 for groups, 3 for single fields.
- **Token-field shuffles:** one field (for example card `upgraded`) is pooled over all valid tokens of all rows and permuted. Deck and relic sizes and ids stay fixed.
- **Fixed inputs:** HP legality, the potion head's inventory, escape eligibility and the boss shift keep their true values.
- **CI:** source-seed cluster bootstrap, 1,000 resamples.

## Ranked groups
| group | Δ surv BCE [95% CI] | repeat range | Δ surv act 1/2/3 | Δ HP CE | Δ HP MAE | Δ maxHP CE | Δ potion CE |
|---|---|---|---|---|---|---|---|
| progress (act, floor) | +0.241 [0.236, 0.246] | 0.239–0.243 | .354/.098/.203 | +0.64 | +4.1 | +0.012 | +0.34 |
| room type (roomClass, isBurningElite) | +0.193 [0.186, 0.199] | 0.190–0.196 | .161/.238/.195 | +1.76 | +8.7 | +0.010 | +0.70 |
| deck (card token set) | +0.099 [0.096, 0.103] | 0.097–0.101 | .053/.113/.186 | +0.47 | +2.3 | +0.523 | +0.27 |
| hp (curHp, maxHp) | +0.081 [0.077, 0.086] | 0.080–0.084 | .057/.117/.082 | +0.92 | +2.0 | +0.000 | +0.17 |
| relics (relic token set) | +0.074 [0.071, 0.078] | 0.073–0.076 | .030/.071/.181 | +0.60 | +2.3 | +0.005 | +0.23 |
| encounter (monster group id) | +0.053 [0.050, 0.055] | 0.051–0.054 | .049/.045/.072 | +0.62 | +2.8 | +0.019 | +0.21 |
| potions all (tokens + count + capacity + keep value) | +0.015 [0.014, 0.016] | | .012/.019/.015 | +0.24 | +1.0 | +0.139 | +0.03 |
| potion tokens | +0.0095 [0.0087, 0.0104] | | | +0.22 | +0.9 | +0.140 | +0.02 |
| potion scalars (count, capacity) | +0.0023 [0.0019, 0.0027] | | | +0.003 | +0.03 | 0 | +0.004 |
| path (lastRoom) | +0.0009 [0.0006, 0.0012] | | | +0.006 | +0.03 | 0 | +0.001 |
| gold | +0.00003 [−0.00005, 0.0001] | | | 0 | 0 | 0 | 0 |
| potionKeepValue / ascension / characterClass | exactly 0 (constant inputs) | | | 0 | 0 | 0 | 0 |

**Top single fields** (Δ survival BCE):
- roomClass +0.192, act +0.187, curHp +0.081 (HP CE +2.06), floor +0.0055.
- potionCount +0.0021, isBurningElite +0.0010, potionCapacity +0.0002.
- maxHp +0.0003, but HP CE +0.95.

**Token fields:**
- card id +0.027 (maxHP CE +0.51), relic id +0.023.
- card upgraded +0.003 (maxHP CE +0.07).
- relic counter +0.0001, card bottleBinding +0.00005, relic orderIndex +0.00001, card misc 0.

## Dead or near-zero inputs
- **Constant here, so they cannot matter:** ascension (always 20; the encoder's inverse std is 1e6), characterClass (always 0), potionKeepValue (always 4.0; inverse std 1e6).
- **Effectively unused:** gold, card misc, relic orderIndex, card bottleBinding.
- **Very small:** lastRoom, relic counters.

## Surprising findings and hints (**Inference** unless stated)
- **Coarse context dominates survival.** Act and roomClass alone are worth more than the encounter id: permuting `act` costs +0.187, `floor` only +0.0055 and the encounter id +0.053. The model seems to price difficulty mostly through the act scalar and the room type, with the 61-way encounter embedding refining it. **Hint:** cheap ablations would drop floor, or use `ctm_input_v2` with act as a category. The act slope is also what Act-4 extrapolation relies on.
- **Deck and relics weigh more as the run goes on.** Deck survival Δ is 0.05 / 0.11 / 0.19 across acts 1–3; relics 0.03 / 0.07 / 0.18. Both are keepers. Card id drives the maxHP head (cards like Feed that raise max HP), as expected.
- **HP for survival is essentially curHp; maxHp feeds the HP and potion heads.** Permuting curHp alone is worse for the HP head than permuting curHp and maxHp together (+2.06 vs +0.92), because a lone curHp no longer matches maxHp.
- **The potion head leans on room type** (Δ potion CE +0.70, from potions spent in elite and boss fights) more than on the potion tokens (+0.02, with the labelled inventory held fixed).
- **Hazard (Open question): potionKeepValue.** It is constant 4.0 in training, so its inverse std is 1e6. `STS_POTION_SAVE=1` makes the runtime feed a varying keep value (`one_combat.cpp::potionKeepValue`), about 1e6 standardized units off-distribution. Is `STS_POTION_SAVE` ever on together with the A20 CTM? If yes, guard or drop this input (the v2 encoding has no keep value). Ascension has the same 1e6 scale, but the runtime only sends A20 rows to this stack.
- **Candidates for a removal ablation** (descriptive, not "unnecessary"): gold, card misc, relic orderIndex, bottleBinding, lastRoom.
- **Possibly missing:** no monster HP or intent beyond the encounter id, and no map lookahead. This audit cannot test either.

## Caveats
- Permutation importance is descriptive. Correlated inputs share or hide credit: act/floor/encounter, curHp/maxHp, potion tokens/count.
- The 1,502 Brew and Lizard rows are excluded. Forced slices and Act 4 are not covered.
- Some held-out rows may have been outside the original training union, because its support filter dropped rows. None are in TRAIN, since the split is by seed.
