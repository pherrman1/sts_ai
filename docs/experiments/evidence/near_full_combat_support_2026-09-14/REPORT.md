# Near-full Ironclad combat support: staged execution report

**NEAR_FULL_COMBAT_SUPPORT_NOT_READY**. Stage-1 shared gold development/composition gates pass; independent review and Stages 2–5 remain pending. The earlier stop on Transmutation+ was too conservative and is superseded: share the learned HoG mechanism and supply native upgrade-dependent payouts. No new data or gameplay. Stages 2–5 require Stage 1 to pass.

Baseline / unchanged model implementation SHA: `210f347334898e7c2a85b8af0f30dedc4888ea88`. Local main was fast-forwarded from `74d31681b8ebd3beb5e85d6db9c1a164f9aeaf13`; the existing fresh Codex-app-managed worktree was moved to that clean main on `codex/near-full-combat-support`. No additional worktree was created. #179 and #180 are merged. Reviewed SHA: **none**; this implementation and development evidence have not had independent review. Final implementation/evidence handoff SHA is recorded in the draft PR evidence packet.

## Initial frozen remaining-support census

Original source-grouped splits and all six frozen component artifact hashes, corpus hash, split hash, prepared representation hashes and manifest binding were revalidated. Every corpus index/source/fight and original split membership matches the prepared representation. All 24,999 completed sources are accounted for. The historical support totals reproduce #179 exactly. Counts by reason are overlapping; combinations below partition the fallback set. All encounter/act/room tables count unsupported rows.

| Population | Rows | Source seeds | Unsupported rows | Unsupported source seeds | Supported rows | Support |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| TEST | 51,441 | 2,517 | 9,987 | 2,196 | 41,454 | 80.585525% |
| all | 510,030 | 24,999 | 96,231 | 21,905 | 413,799 | 81.132286% |

### Support reasons

| Value | All fallback rows | TEST fallback rows |
| --- | ---: | ---: |
| entropic_brew | 3,208 | 349 |
| gold_mutating_card | 2,640 | 273 |
| gold_mutating_encounter | 27,664 | 2,797 |
| gold_mutating_potion | 21,698 | 2,246 |
| gold_mutating_relic | 6,824 | 716 |
| potion_not_certified | 3,208 | 349 |
| pre_smoke_bomb_used | 26 | 1 |
| pre_stolen_gold_nonzero | 19,048 | 1,950 |
| ritual_dagger | 13,926 | 1,550 |
| smoke_bomb | 3,765 | 372 |
| writhing_mass | 4,477 | 464 |

### Exact combinations of reasons

| Value | All fallback rows | TEST fallback rows |
| --- | ---: | ---: |
| entropic_brew+gold_mutating_card+gold_mutating_encounter+potion_not_certified | 1 | 0 |
| entropic_brew+gold_mutating_card+gold_mutating_potion+potion_not_certified | 1 | 0 |
| entropic_brew+gold_mutating_card+potion_not_certified | 8 | 0 |
| entropic_brew+gold_mutating_encounter+gold_mutating_potion+potion_not_certified | 5 | 0 |
| entropic_brew+gold_mutating_encounter+gold_mutating_potion+potion_not_certified+smoke_bomb | 1 | 0 |
| entropic_brew+gold_mutating_encounter+gold_mutating_relic+potion_not_certified | 1 | 0 |
| entropic_brew+gold_mutating_encounter+potion_not_certified | 157 | 22 |
| entropic_brew+gold_mutating_encounter+potion_not_certified+pre_stolen_gold_nonzero | 3 | 0 |
| entropic_brew+gold_mutating_encounter+potion_not_certified+smoke_bomb | 1 | 0 |
| entropic_brew+gold_mutating_potion+gold_mutating_relic+potion_not_certified | 2 | 0 |
| entropic_brew+gold_mutating_potion+potion_not_certified | 79 | 7 |
| entropic_brew+gold_mutating_potion+potion_not_certified+pre_stolen_gold_nonzero | 3 | 1 |
| entropic_brew+gold_mutating_potion+potion_not_certified+ritual_dagger | 1 | 0 |
| entropic_brew+gold_mutating_relic+potion_not_certified | 36 | 1 |
| entropic_brew+gold_mutating_relic+potion_not_certified+pre_stolen_gold_nonzero | 1 | 1 |
| entropic_brew+gold_mutating_relic+potion_not_certified+ritual_dagger | 1 | 0 |
| entropic_brew+gold_mutating_relic+potion_not_certified+writhing_mass | 2 | 0 |
| entropic_brew+potion_not_certified | 2,687 | 296 |
| entropic_brew+potion_not_certified+pre_stolen_gold_nonzero | 107 | 13 |
| entropic_brew+potion_not_certified+pre_stolen_gold_nonzero+ritual_dagger | 1 | 0 |
| entropic_brew+potion_not_certified+ritual_dagger | 81 | 6 |
| entropic_brew+potion_not_certified+ritual_dagger+writhing_mass | 3 | 0 |
| entropic_brew+potion_not_certified+smoke_bomb | 14 | 2 |
| entropic_brew+potion_not_certified+writhing_mass | 12 | 0 |
| gold_mutating_card | 2,098 | 200 |
| gold_mutating_card+gold_mutating_encounter | 66 | 9 |
| gold_mutating_card+gold_mutating_encounter+gold_mutating_potion | 4 | 0 |
| gold_mutating_card+gold_mutating_encounter+ritual_dagger | 1 | 0 |
| gold_mutating_card+gold_mutating_encounter+smoke_bomb | 1 | 0 |
| gold_mutating_card+gold_mutating_potion | 112 | 11 |
| gold_mutating_card+gold_mutating_potion+gold_mutating_relic | 1 | 0 |
| gold_mutating_card+gold_mutating_potion+pre_stolen_gold_nonzero | 3 | 1 |
| gold_mutating_card+gold_mutating_potion+ritual_dagger | 12 | 3 |
| gold_mutating_card+gold_mutating_potion+writhing_mass | 1 | 0 |
| gold_mutating_card+gold_mutating_relic | 63 | 4 |
| gold_mutating_card+gold_mutating_relic+ritual_dagger | 7 | 0 |
| gold_mutating_card+gold_mutating_relic+ritual_dagger+writhing_mass | 1 | 0 |
| gold_mutating_card+gold_mutating_relic+writhing_mass | 1 | 0 |
| gold_mutating_card+pre_stolen_gold_nonzero | 53 | 8 |
| gold_mutating_card+pre_stolen_gold_nonzero+ritual_dagger | 3 | 0 |
| gold_mutating_card+ritual_dagger | 140 | 30 |
| gold_mutating_card+ritual_dagger+smoke_bomb+writhing_mass | 1 | 0 |
| gold_mutating_card+ritual_dagger+writhing_mass | 6 | 2 |
| gold_mutating_card+smoke_bomb | 13 | 0 |
| gold_mutating_card+writhing_mass | 43 | 5 |
| gold_mutating_encounter | 25,192 | 2,544 |
| gold_mutating_encounter+gold_mutating_potion | 1,268 | 124 |
| gold_mutating_encounter+gold_mutating_potion+gold_mutating_relic | 4 | 0 |
| gold_mutating_encounter+gold_mutating_potion+gold_mutating_relic+ritual_dagger | 1 | 0 |
| gold_mutating_encounter+gold_mutating_potion+pre_stolen_gold_nonzero | 34 | 5 |
| gold_mutating_encounter+gold_mutating_potion+ritual_dagger | 3 | 0 |
| gold_mutating_encounter+gold_mutating_potion+smoke_bomb | 5 | 2 |
| gold_mutating_encounter+gold_mutating_relic | 139 | 15 |
| gold_mutating_encounter+gold_mutating_relic+pre_stolen_gold_nonzero | 1 | 0 |
| gold_mutating_encounter+pre_smoke_bomb_used | 2 | 0 |
| gold_mutating_encounter+pre_stolen_gold_nonzero | 420 | 39 |
| gold_mutating_encounter+pre_stolen_gold_nonzero+smoke_bomb | 6 | 0 |
| gold_mutating_encounter+ritual_dagger | 100 | 12 |
| gold_mutating_encounter+ritual_dagger+smoke_bomb | 1 | 1 |
| gold_mutating_encounter+smoke_bomb | 247 | 24 |
| gold_mutating_potion | 18,069 | 1,896 |
| gold_mutating_potion+gold_mutating_relic | 258 | 19 |
| gold_mutating_potion+gold_mutating_relic+pre_stolen_gold_nonzero | 8 | 1 |
| gold_mutating_potion+gold_mutating_relic+ritual_dagger | 12 | 0 |
| gold_mutating_potion+gold_mutating_relic+ritual_dagger+writhing_mass | 1 | 0 |
| gold_mutating_potion+gold_mutating_relic+smoke_bomb | 1 | 0 |
| gold_mutating_potion+gold_mutating_relic+writhing_mass | 9 | 2 |
| gold_mutating_potion+pre_stolen_gold_nonzero | 1,069 | 96 |
| gold_mutating_potion+pre_stolen_gold_nonzero+ritual_dagger | 10 | 1 |
| gold_mutating_potion+pre_stolen_gold_nonzero+smoke_bomb | 7 | 0 |
| gold_mutating_potion+ritual_dagger | 487 | 58 |
| gold_mutating_potion+ritual_dagger+smoke_bomb | 4 | 0 |
| gold_mutating_potion+ritual_dagger+writhing_mass | 10 | 0 |
| gold_mutating_potion+smoke_bomb | 90 | 3 |
| gold_mutating_potion+smoke_bomb+writhing_mass | 1 | 0 |
| gold_mutating_potion+writhing_mass | 122 | 16 |
| gold_mutating_relic | 5,605 | 592 |
| gold_mutating_relic+pre_stolen_gold_nonzero | 141 | 16 |
| gold_mutating_relic+pre_stolen_gold_nonzero+ritual_dagger | 3 | 1 |
| gold_mutating_relic+pre_stolen_gold_nonzero+smoke_bomb | 2 | 1 |
| gold_mutating_relic+ritual_dagger | 365 | 49 |
| gold_mutating_relic+ritual_dagger+smoke_bomb | 1 | 0 |
| gold_mutating_relic+ritual_dagger+writhing_mass | 9 | 1 |
| gold_mutating_relic+smoke_bomb | 32 | 1 |
| gold_mutating_relic+smoke_bomb+writhing_mass | 2 | 0 |
| gold_mutating_relic+writhing_mass | 114 | 12 |
| pre_smoke_bomb_used | 24 | 1 |
| pre_stolen_gold_nonzero | 16,759 | 1,721 |
| pre_stolen_gold_nonzero+ritual_dagger | 274 | 35 |
| pre_stolen_gold_nonzero+ritual_dagger+smoke_bomb | 1 | 0 |
| pre_stolen_gold_nonzero+smoke_bomb | 139 | 10 |
| ritual_dagger | 12,027 | 1,315 |
| ritual_dagger+smoke_bomb | 83 | 7 |
| ritual_dagger+smoke_bomb+writhing_mass | 2 | 0 |
| ritual_dagger+writhing_mass | 274 | 29 |
| smoke_bomb | 3,092 | 319 |
| smoke_bomb+writhing_mass | 18 | 2 |
| writhing_mass | 3,845 | 395 |

### Encounter

| Value | All fallback rows | TEST fallback rows |
| --- | ---: | ---: |
| CULTIST | 577 | 54 |
| EXORDIUM_THUGS | 8,294 | 832 |
| EXORDIUM_WILDLIFE | 983 | 112 |
| RED_SLAVER | 688 | 70 |
| THREE_LOUSE | 1,249 | 117 |
| TWO_FUNGI_BEASTS | 1,231 | 143 |
| GREMLIN_NOB | 2,946 | 296 |
| LAGAVULIN | 2,810 | 286 |
| THREE_SENTRIES | 2,830 | 282 |
| SLIME_BOSS | 1,452 | 131 |
| THE_GUARDIAN | 1,388 | 144 |
| JAW_WORM | 598 | 64 |
| HEXAGHOST | 1,421 | 135 |
| SPHERIC_GUARDIAN | 1,571 | 154 |
| CHOSEN | 1,506 | 160 |
| SHELL_PARASITE | 1,582 | 191 |
| THREE_BYRDS | 1,612 | 161 |
| TWO_THIEVES | 9,009 | 948 |
| CHOSEN_AND_BYRDS | 737 | 81 |
| SENTRY_AND_SPHERE | 724 | 78 |
| SNAKE_PLANT | 1,935 | 202 |
| SNECKO | 1,366 | 128 |
| TWO_LOUSE | 610 | 59 |
| CENTURION_AND_HEALER | 1,996 | 210 |
| CULTIST_AND_CHOSEN | 1,134 | 121 |
| THREE_CULTIST | 1,132 | 126 |
| SHELLED_PARASITE_AND_FUNGI | 1,095 | 121 |
| GREMLIN_LEADER | 2,073 | 229 |
| SLAVERS | 2,155 | 222 |
| BOOK_OF_STABBING | 2,124 | 230 |
| AUTOMATON | 1,005 | 109 |
| COLLECTOR | 990 | 102 |
| CHAMP | 925 | 95 |
| SMALL_SLIMES | 578 | 59 |
| THREE_DARKLINGS | 1,875 | 221 |
| ORB_WALKER | 1,204 | 132 |
| THREE_SHAPES | 1,247 | 135 |
| SPIRE_GROWTH | 682 | 81 |
| TRANSIENT | 712 | 75 |
| FOUR_SHAPES | 679 | 78 |
| MAW | 721 | 80 |
| SPHERE_AND_TWO_SHAPES | 684 | 75 |
| JAW_WORM_HORDE | 691 | 76 |
| WRITHING_MASS | 4,477 | 464 |
| BLUE_SLAVER | 1,276 | 152 |
| GIANT_HEAD | 1,348 | 146 |
| NEMESIS | 1,325 | 131 |
| REPTOMANCER | 1,252 | 135 |
| AWAKENED_ONE | 583 | 68 |
| TIME_EATER | 579 | 58 |
| DONU_AND_DECA | 605 | 62 |
| LAGAVULIN_EVENT | 16 | 3 |
| GREMLIN_GANG | 727 | 74 |
| MASKED_BANDITS_EVENT | 639 | 62 |
| MUSHROOMS_EVENT | 104 | 9 |
| MYSTERIOUS_SPHERE_EVENT | 275 | 29 |
| LOOTER | 10,361 | 1,017 |
| LARGE_SLIME | 1,186 | 109 |
| LOTS_OF_SLIMES | 657 | 63 |

### Act

| Value | All fallback rows | TEST fallback rows |
| --- | ---: | ---: |
| 1 | 41,790 | 4,192 |
| 2 | 35,310 | 3,730 |
| 3 | 19,131 | 2,065 |

### Room

| Value | All fallback rows | TEST fallback rows |
| --- | ---: | ---: |
| EVENT | 1,259 | 128 |
| ELITE | 18,830 | 1,951 |
| MONSTER | 67,386 | 7,023 |
| BOSS | 8,756 | 885 |

## #180 actual root-abort ranking

The 64 official seeds are exactly 980000–980063; canaries are excluded. First-failure reason counts reconcile per seed against unsupported-combat totals. They account for 1,551 unsupported imagined combats and 1,551 aborted roots.

| First failure | Aborted roots | Share |
| --- | ---: | ---: |
| entropic_brew | 30 | 1.934% |
| gold_mutating_card | 264 | 17.021% |
| gold_mutating_encounter | 366 | 23.598% |
| gold_mutating_potion | 250 | 16.119% |
| gold_mutating_relic | 227 | 14.636% |
| pre_stolen_gold_nonzero | 155 | 9.994% |
| ritual_dagger | 34 | 2.192% |
| smoke_bomb | 25 | 1.612% |
| writhing_mass | 200 | 12.895% |

Gold reasons sum to 1,262/1,551 (81.367%). This is actual first-failure frequency, not corpus frequency. It is not a before/after replay: other failures can be hidden behind a first gold rejection. The trace writer (`apps/one_combat/ooc_mcts_adapter.cpp::writeLiveOocMctsTrace`) emits per-seed aggregates, without imagined states, root identities, or joint reasons. No saved #180 imagined-state corpus has been identified. Exact new unsupported counts and predicted new aborted roots are **unavailable**; subtracting 1,262 would be unsupported. No replay or gameplay was run.

## Stage 1 — gold / stolenGold

### Source audit and required representation

- `Monster::stealGoldFromPlayer` takes `min(player.gold, amount)` and tracks each thief’s stolen amount. Native THIEVERY is 15 at A0 (20 from A17); Looter/Mugger can perform two mugs and an optional lunge. Two Thieves requires per-thief clipping and escape/recovery accounting. Exordium Thugs has initialization misc-RNG draws, already represented by the exact replay schedule.
- `BattleContext::exitBattle` resets `stolenGold` to zero, then sums qualifying Looter/Mugger stolen amounts unless they escaped. Pre-existing `stolenGold` is not generally copy-through.
- `Actions::HandOfGreedAction` gives 20/25 gold only on eligible non-minion kills, excluding half-dead and relevant regrowth states. `Player::gainGold` suppresses gains under Ectoplasm and heals through Bloody Idol. This can affect upstream HP; no upstream refit was performed.
- Jack of All Trades generates unupgraded colorless cards (the upgraded card generates two). Transmutation generates colorless cards with its own upgraded flag and temporary zero cost, with energy/Chemical X determining count. Toolbox and Colorless Potion also expose generated Hand of Greed routes. Native generation probabilities alone do not determine eligible-kill/proc probability under the combat policy.
- A vocabulary of observed raw `(Δgold, post stolenGold)` pairs is insufficient: four TEST pairs covering five rows are absent from TRAIN. They are clipped-transfer pairs, so this does not itself prove missing simulator support; a native structured reconstruction can represent such values without treating them as unseen regression labels.

Gold exclusions affect 74,069 rows overall and 7,615 TEST rows. The gold-only candidate set contains 71,367 rows / 7,301 TEST rows. Revealing all later support checks on the original visible inputs finds **zero later rejection reasons**. Gold-only victorious rows have **zero other copy-through mutations**. This is a source/target inventory, not ancestral hard-validity qualification.

| Candidate split | Rows | Source seeds | Victories | Deaths | Net gold gains |
| --- | ---: | ---: | ---: | ---: | ---: |
| test | 7,301 | 2,044 | 7,190 | 111 | 41 |
| train | 57,151 | 16,153 | 56,153 | 998 | 364 |
| validation | 6,915 | 2,017 | 6,788 | 127 | 34 |

**Transmutation+ diagnostic, not a veto.** Whole-corpus inspection finds exactly two rows, both source 4108572 / fights 27 and 28 / TEST: one non-gain victory and one death; TRAIN=0 and VALIDATION=0. This slice cannot independently establish calibration, but does not require a separate distribution. The accepted design shares statistical information across explicit HoG/HoG+, Transmutation and generated routes, with upgraded-HoG source status as a common condition and exact native +20/+25 payouts. Native generation also permits recursive colorless routes and in-combat upgrades; these affect legal payout availability. The damage shift (25 versus 20) remains a conditional modeling issue and diagnostic caveat.

The earlier request for new targeted Transmutation+ data is withdrawn. Corpus frequency remains 2/510,030 (0.000392%); specific #180 live frequency remains unknown because gold-card reasons are aggregated. No data is collected or reassigned across frozen splits.

Implementation: `tools/combat_transition_gold.py` enumerates native RAW gold/stolenGold outcomes with turn-ordered clipped theft, killed/escaped thief recovery, exact payouts, Ectoplasm and pre-stolen reset. A single small conditional categorical scorer shares frozen visible state, HP/potion conditions and common upgrade features. The native closure proves gold-accounting legality, not complete combat-policy reachability. `tools/combat_transition_gold_evaluate.py` audits/prepares all original gold-only rows, fits only the new scorer on original TRAIN victories with original VALIDATION epoch selection, and produces bounded development diagnostics. No encoder or upstream head is trained.

The fixed composition diagnostic uses 32 upstream draws, exact conditional potion-mask marginalization for gold exposure, the existing exact maxHP marginal for HP exposure, and 32 complete ancestral draws per gold-only TEST row. Main gold mechanisms and their union are reported separately; Transmutation+ is reported as an ultra-low-support diagnostic and excluded from the vetoing statistical aggregation, while its native validity remains checked. Independent review and union/native/runtime continuation remain required. Relic exposure is covered by the supplemental frozen diagnostic below.

### Stage-1 executed development evidence

**GOLD_DEVELOPMENT_GATES_PASS_PENDING_REVIEW** and **RELIC_DEVELOPMENT_EXPOSURE_PASS_PENDING_REVIEW**. Gold fit/diagnostics source SHA: `1a24e7ccdb26c3ef649371dfe07269ecbc3c2d4a`; supplemental relic evaluation SHA: `2f8fb3f45a6656c03d81f69f3f4b1d1c3116164a`. Neither SHA has independent implementation review. The PR records the final handoff head separately. Fixed 12-epoch fit: 56,153 original TRAIN victories, 6,788 original VALIDATION victories, selected epoch 12, validation NLL 0.617246, fit elapsed 2.90 s. No upstream weight/normalization/refit or new data.

Gold-only TEST contains 7,301 rows / 7,190 victories / 111 deaths. Vetoing statistical union contains 7,189 victories; the one Transmutation+ victory is reported separately, and both diagnostic rows participate in hard validity. Reason slices overlap and must not be summed.

| TEST slice | Victories | Joint gold NLL | Joint Brier | Mode exact | Gold exposure | HP exposure | Potion exposure | Relic exposure / observed group |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Gold union | 7,189 | 0.574911 | 0.259408 | 0.799972 | 0.012944 | 0.014668 | 0.000701 | 0.006219 |
| Transmutation+ diagnostic | 1 | 0.031261 | 0.001460 | 1.000000 | -0.000098 | 0.000130 | -0.000697 | 0.057193 |
| Gold card | 212 | 0.267029 | 0.111231 | 0.924528 | -0.001516 | 0.021672 | 0.000771 | -0.011224 |
| Gold encounter | 2,735 | 1.444972 | 0.655748 | 0.488117 | 0.030017 | 0.011005 | 0.001123 | -0.000276 |
| Gold potion | 2,115 | 0.134877 | 0.055152 | 0.961702 | 0.007248 | 0.019124 | -0.000495 | 0.013227 |
| Gold relic | 615 | 0.167372 | 0.060857 | 0.959350 | 0.001442 | 0.030266 | -0.000017 | 0.008069 |
| Pre-existing stolenGold | 1,863 | 0.028048 | 0.013461 | 0.992485 | 0.000637 | 0.008262 | 0.001551 | 0.008568 |

Union expected-value MAE: gold 4.22353 / stolenGold 4.17038. Deterministic rows do not hide the informative results: 4,091 union victories have more than one teacher-legal gold outcome; on these NLL 1.010275, Brier 0.455851, mode exact 0.648497, gold MAE 7.42189, stolenGold MAE 7.32849. Positive-gain support remains sparse (41 TEST rows); the exposure gate is a composition check, not independent proof of rare-proc calibration or full policy reachability. The single Transmutation+ victory is non-gain; its score cannot establish branch calibration.

Complete ancestral hard validity: **233,632 draws = 7,301 × 32**, 229,414 gold/upstream downstream calls, 4,218 sampled deaths; zero illegal gold, illegal stolenGold, native-gold-closure violations, upstream assembled persistent-state violations, or downstream-after-death accounting violations. Native raw-target audit covers all 71,367 candidates, width at most 72, with zero native target, other persistent, or inherited RNG violations. Existing immutable upstream assembly enforces HP/maxHP/potion/relic/shared-residue/RNG rules; gold is then checked against its mask-dependent native closure. Relic exposure has 1,834 informative union victories and zero zero-mixture-probability rows. All gold reason slices pass each evaluated exposure mean ≤0.1 nat.

A failed first preparation exposed an incorrect assumed Darkling qualifying-kill cap. Native `MonsterGroup::anyHalfDead` defers only Awakened One, and the final Darkling death returns before setting halfDead; one HoG payout is possible. The native cap and regression were corrected, committed, and the full target audit rerun successfully before any fitting.

Research checkpoint `gold.pt` SHA256: `19a1a387f56ea4c8eceb2ebf4b92f951f497b18876ccab31168f0c6a9a5d853c`. Its local bound directory is `/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914/shared-gold-v1`; preparation/cache/test-row/checkpoint hashes and frozen upstream hashes are in the JSON receipts. This is a Python development checkpoint, not a native runtime artifact.

Stage 1 is at the draft-PR implementation-review handoff. The bounded development results pass; no new Transmutation+ collection is needed. Independent review/frozen reviewed SHA remain required for final scientific qualification and an expensive full-stack refit. The repository research workflow explicitly says: “After implementation review passes, freeze the reviewed commit SHA before any expensive scientific run.” No support exclusions or deployable runtime artifact are changed; actual rows recovered: **0**. Candidate recovery after qualification would be 71,367 overall / 7,301 TEST: 485,166/510,030 (95.124993%) overall and 48,755/51,441 (94.778484%) TEST. These percentages are a prospective census calculation, not current support. The frozen census/source-inventory bytes remain unchanged.


## Stages 2–4

| Stage | Mechanism | Implementation/training/TEST metrics/exposure/ancestral validity | Rows recovered |
| --- | --- | --- | ---: |
| 2 | Writhing Mass | Not started; Stage-1 draft-PR review handoff | 0 |
| 2 | Ritual Dagger | Not started; Stage-1 draft-PR review handoff | 0 |
| 3 | Entropic Brew / creation | Not started; Stage-1 draft-PR review handoff | 0 |
| 4 | Smoke Bomb / ESCAPE | Not started; Stage-1 draft-PR review handoff | 0 |

## Stage 5 and final qualification

No refit or union qualification. Final support remains the historical #179 support; all 96,231 fallback rows and reasons in the initial census remain unsupported. Final new component/composition metrics, native parity, new runtime artifact hash, continuation equivalence, and new #180 counts: **not available**. The unchanged historical runtime is not a near-full-support artifact.

Final classification: **NEAR_FULL_COMBAT_SUPPORT_NOT_READY**. No gameplay improvement is claimed. Independent review and composition qualification are required before support/runtime changes; the approved shared-mechanism development continues without new data.

## Checks and reproduction

- `python3 tools/agent/worktree.py preflight .`: Codex-app-managed, external writable Git metadata, correct origin.
- `git fetch origin main`, then `git fetch origin main:main`: local main fast-forwarded; canonical checkout/task branch and unrelated untracked evidence preserved.
- `python3 tools/agent/worktree.py check .`: both pinned submodules pass.
- `bash tools/agent/doctor.sh`: all checks pass.
- Census and gold audit: complete verified corpus scans pass; branch presence: complete prepared-card inspection passes.
- `python3 tools/test_combat_transition_remaining_census.py -q`: 5 tests pass.
- `cmake --preset linux-gcc-debug`: configure/generate pass. No C++ code changes or build needed for this Python CTest.
- `ctest --test-dir build/linux-gcc-debug -R '^combat_transition_remaining_census_selftest$' --output-on-failure`: 1/1 pass, 0.14 s.
- `git diff --check`: pass.
- Initial census invocation failed on a misspelled copy-through constant; corrected and complete rerun passes. Initial `python` preflight failed because only `python3` is installed; corrected preflight passes. An accidental Python invocation of the shell doctor failed; the proper Bash invocation passes.
- Shared gold native/scorer tests: 8 PASS; original census tests: 5 PASS; focused CTests: 2/2 PASS (1.17 s). Supplemental relic diagnostic compiles and completes all 32 draws.
- Full native preparation, bounded 12-epoch fit, gold/HP/potion exposure, supplemental relic exposure and complete ancestral validity: PASS; raw receipts linked below.
- Linux GCC at implementation SHA `1a24e7c`: SUCCESS. Final handoff-head CI status is recorded in the PR; earlier CI does not attest later commits.
- Not run: independent implementation/scientific review, upstream/full-stack refit, native export/runtime/escape continuation/new parity tests, new data/game seeds/gameplay. No manual C++ build/full CTest; authoritative Linux GCC CI runs the repository verification.

Reproduction (seed-free; frozen inputs must exist at the bound paths):

```sh
python3 -m tools.combat_transition_remaining_census --output /tmp/near-full-initial-census.json
python3 -m tools.combat_transition_gold_audit --output /tmp/near-full-gold-inventory.json
python3 -m tools.combat_transition_gold_audit --presence-only --output /tmp/near-full-gold-branch.json
python3 tools/test_combat_transition_remaining_census.py -q
```

Executed shared-component receipts: [native preparation](shared-gold-preflight.json), [fixed recipe](shared-gold-recipe.json), [fit/history](shared-gold-fit.json), [gold/HP/potion and hard validity](shared-gold-diagnostics.json), [relic exposure](shared-gold-relic_diagnostics.json).

Reproduction of new receipts (use a fresh absent output directory; commands refuse overwrites):

```sh
# Preparation and fit/diagnose at source SHA 1a24e7ccdb26c3ef649371dfe07269ecbc3c2d4a
python3 -m tools.combat_transition_gold_evaluate prepare --output-dir "$GOLD_RUN_DIR"
python3 -m tools.combat_transition_gold_evaluate fit --output-dir "$GOLD_RUN_DIR" --source-sha 1a24e7ccdb26c3ef649371dfe07269ecbc3c2d4a
python3 -m tools.combat_transition_gold_evaluate diagnose --output-dir "$GOLD_RUN_DIR" --source-sha 1a24e7ccdb26c3ef649371dfe07269ecbc3c2d4a
# Supplemental evaluation at its separately frozen source SHA
python3 -m tools.combat_transition_gold_relic_diagnostic --output-dir "$GOLD_RUN_DIR" --evaluation-sha 2f8fb3f45a6656c03d81f69f3f4b1d1c3116164a
```

Frozen receipts: [census](initial-census.json), [gold inventory](gold-source-inventory.json), [whole-corpus branch presence](gold-branch-presence.json). `SHA256SUMS` freezes their bytes and this report. Knowledge impact: seed-free research census/qualification status recorded in the experiment ledger and maintained current-research page.
