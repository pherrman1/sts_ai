# Near-full Ironclad combat support: staged execution report

**NEAR_FULL_EXCEPT_SMOKE_QUALIFIED**. The final supported cohort passes offline composition and native probability/state parity. Smoke/pre-Smoke and the failing Writhing/Ritual intersection remain fail-closed. See the final bounded qualification below; earlier whole-union failures are preserved as historical development evidence.

Task baseline SHA: `210f347334898e7c2a85b8af0f30dedc4888ea88`. Local main was fast-forwarded from `74d31681b8ebd3beb5e85d6db9c1a164f9aeaf13`; the existing fresh Codex-app-managed worktree was moved to that clean main on `codex/near-full-combat-support`. No additional worktree was created. #179 and #180 are merged. External engineering review supplied by the user covered `8420103ed7cdeb220472a70c4961f203cfca471c`, including gold, sparse events and the native escape oracle. The final frozen implementation is independently reviewed before merge; review and CI outcomes are bound to the SHA in PR #182. This does not assert pristine scientific holdout qualification. Final implementation/evidence handoff SHA is recorded in the draft PR evidence packet.

## Final bounded support qualification (2026-09-15)

**NEAR_FULL_EXCEPT_SMOKE_QUALIFIED** for offline composition and the native combat boundary. The final pre-state predicate retains qualified near-full states except an initially held Smoke Bomb, pre-existing `smokeBombUsed`, or Writhing Mass with any Ritual Dagger. It does not inspect post-state labels. Brew remains supported, including generated Smoke/ESCAPE; the exclusion concerns initial/pre-Smoke states. No fourth Smoke repair, retraining, new data or gameplay was run in this pass. MCTS remains OFF by default.

| Population | Total | Supported | Unsupported | Exact support |
| --- | ---: | ---: | ---: | ---: |
| TRAIN | 408,183 | 404,877 | 3,306 | 99.190069% |
| VALIDATION | 50,406 | 50,022 | 384 | 99.238186% |
| TEST | 51,441 | 51,036 | 405 | 99.212690% |
| Entire corpus | 510,030 | 505,935 | 4,095 | 99.197106% |

Overlapping entire-corpus exclusion marginals are Smoke 3,765, pre-Smoke flag 26 and Writhing/Ritual 307; three rows overlap. TEST marginals are 372, 1 and 32, without overlap. All 41,454 previously qualified #179 TEST rows are retained and their composition was rerun with the selected refitted maxHP weights. New support adds 92,136 corpus states and 9,582 TEST states to V1.

Composition on the exact final set uses 49,236 surviving TEST rows. Every nonempty reported slice gate is ≤0.1 nat, including tiny Transmutation+ and recursive Brew slices, with zero remaining target-mass failures. Maximum slice gap is Writhing +0.094655723 nat (418 rows). Entire-final-set component gaps are HP +0.012623412, potion +0.004074735, relic −0.001031325, Ritual −0.000254998 and gold +0.019147781 nat. The seven retained observed ESCAPE rows pass their applicable HP/potion/gold gates; none has an informative relic/Writhing/Ritual target.

The original 32-draw composition report has one gold Monte Carlo zero at corpus index 71838. Preserve that report as `final-support-exposure-v1.json`. A restricted analytic fallback integrates all 11 maxHP classes, legal HP outcomes and 32 ordinary potion-clearing masks, then the native conditional gold probability. The corrected exact target mass is 0.0010596961022394005, normalization 0.9999999941683583. This correction changes qualification accounting only, not weights, support or sampling; it applies to ordinary inventory without Ritual Dagger. `final-support-exposure-exact-v3.json` binds the original row evidence and retained cohort hash. This is a hybrid qualification estimate, not an exact ancestral marginal for every row. All original TEST evidence remains reused development evidence, including the earlier repair decisions; it is not a pristine holdout or gameplay confirmation.

All 51,036 final-supported TEST states receive 32 draws: **1,633,152** sampled transitions, with zero recorded HP, potion, gold/kill-budget, Writhing, Ritual, relic, RNG, escape or death-short-circuit violations. Counts: 61,661 DEATH, 1,571,140 VICTORY, 351 ESCAPE, 10,142 Brew uses, 329 sampled recursive Brew cases; zero downstream work after sampled death.

The selected original full-union v1 component stack is exported as the tracked `selfplay/models/combat_transition_near_full_except_smoke_v2.native` (2,235,832 bytes; SHA256 `22c855e0667a58a73835505672b0ae6d03f12e9fb8d64f08893810199246e94e`). Failed Smoke repair checkpoints are not promoted. The exporter requires passing slice/validity gates, row-evidence hashes and matching checkpoint identities. The strict V2 loader binds the passing classification, exact all/TEST cohort hashes, source identities, tensor schema and exclusions; the V1 loader and support remain compatible. A byte-identical verification export records source SHA separately without changing the artifact.

CPU FP32 Python/native probability parity passes at fixed 1e-4 tolerance: largest probability error 5.9604645e−7, largest value error including encoder outputs 2.3841858e−6. Across 3,904 draws from 28 supported fixtures, complete RAW sampled state, advanced planner stream and scalar/prepared sampling match exactly: 415 DEATH, 3,368 VICTORY, 121 ESCAPE, 117 recursive Brew cases, 2,852 advanced hypothetical potion RNG states. Three excluded fixtures prove unsupported/no RNG draw in Python and native. Additional conditional fixtures exercise generated Colorless/Skill/Forge effects and ESCAPE. Parity exposed a native Ritual candidate ordering bug; preserving Python insertion order repaired sampled-state parity without changing probabilities or weights.

The executed native predicate scans all 510,030 states. Both counts and ordered index digests exactly match the qualification cohort: all `969a239845e7638a5797bcf1f2d03dc7c599c83b22e8dd76337cb31c3c20e0ef`, TEST `71f2ca52769aa36a39f5684bf408090deb10edf8c13e55803cc0fd46ce1bfc31`. `final-runtime-support-v3.json` binds artifact, census, native output and probe/source hashes. No approximate subtraction is used.

Use the V2 artifact only through the existing explicit `STS_OOC_MCTS_COMBAT_MODEL` path with the usual loaded V4/win models and opt-in `STS_OOC_MCTS=1`. This combat-boundary qualification neither enables MCTS by default nor establishes whole-planner fairness or win rate. Exact #180 imagined-state replay remains unavailable; aggregate counts cannot supply a new root-abort count. Final frozen SHA, independent implementation review and authoritative Linux GCC CI outcomes are recorded in PR #182 before merge.

Local verification: Debug configure/build PASS, all **101/101 CTest** PASS (52.30 seconds), focused **11/11** PASS, direct tracked-artifact **2/2** PASS, worktree/doctor/diff checks PASS. Raw logs and exact commands are bound in `final-checks.json`. No new gameplay, training or corpus. Final review/CI are bound to the PR SHA.

Receipts: `final-support-census-v1.json`, original `final-support-exposure-v1.json`, authoritative `final-support-exposure-exact-v3.json`, `final-support-raw-v1.json`, `final-native-export-v3.json`, `final-native-parity-v4.json`, `final-runtime-support-v3.json`. External row NPZ paths/hashes are bound in the exposure receipts. Historical full-union failures below remain unchanged and explain the final exclusions.

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

Stage 1 at PR head `9a7220512939deb46e359339d28016e019cebad3` was approved by the user, who authorized all remaining stages. This continuation uses the same app-managed worktree and frozen corpus/splits. User approval is recorded as user approval, not an assertion of independent scientific review.

## Stage 2 — native sparse events and affected maxHP repair

Writhing Mass has exact native no-change / Parasite / Omamori-consumed reconstruction. Omamori is active only with positive charges; zero charges permit Parasite. Ceramic Fish's world-deck gold is overwritten by battle-player gold on RAW exit, while Darkstone's battle +6 maxHP survives. Ritual Dagger preserves RAW card index and duplicate ownership, with exact +3/+5 increments and a common eligible-kill budget. Its Awakened One cap includes the first phase, as the native Dagger action does. Joint gold/Dagger reconstruction prevents spending the same fatal hit twice, including per-thief escape/recovery.

The full existing corpus audit finds zero native target problems. Consumption-only development explicitly defers Brew/Smoke overlaps to Stages 3–4: 41 Writhing and 180 Dagger rows. They remain part of the final support goal.

| Component | TRAIN victories | VALIDATION victories | TEST victories | TEST teacher NLL | Exact component exposure gap |
| --- | ---: | ---: | ---: | ---: | ---: |
| Writhing Mass | 3,462 | 411 | 449 | 0.587495 | +0.047608 |
| Ritual Dagger | 9,898 | 1,222 | 1,402 | 0.059781 | -0.000122 |

Both tiny shared scorers use frozen visible HP encodings and sampled HP/potion conditions. Original source splits, fixed 12 epochs, original VALIDATION selection; selected epoch 12 for each. Finite 32-draw Writhing misses were retained as diagnostics. Exact marginalization over all maxHP, legal HP and legal potion-mask classes found zero true zero-mass targets but a **real +0.530710 nat exposure failure**. An affected maxHP linear-head-only refit reduced this to +0.287375, still failing. Refitting only the existing maxHP encoder and head repaired it to **+0.047608**, source-bootstrap 95% CI [0.033039, 0.063111]. Dagger's gap is **-0.000122**, CI [-0.000431, 0.000097]. No other historical encoder/head weights changed. This material degradation justifies the affected-component refit allowed by the plan.

MaxHP refit: 388,204 TRAIN / 47,962 VALIDATION / 48,929 TEST victories in the explicitly eligible union; unchanged normalization and architecture; fixed 12 epochs, selected 11. VALIDATION NLL improves 0.053481 → 0.043296; TEST NLL 0.053666. Research checkpoint SHA256 `c6c6564e8e3f689ad3ad152f98ad7d42a819a48e9a603df1ebf70ba93868bec1`.

Affected upstream exposure checks pass. Writhing: HP +0.038175 / potion -0.003109 / relic +0.003011 per observed group. Dagger: HP +0.016799 / potion -0.001816 / relic -0.004980. Rechecking original gold-only rows after maxHP repair gives gold +0.012722 / HP +0.012401 / potion +0.000597 / relic +0.005723. HP uses its exact maxHP marginal; downstream checks use 32 maxHP/HP draws and exact conditional potion-mask marginalization. Writhing's Omamori is evaluated by the native event component.

Combined native sparse validity: **62,912 draws = 1,966 deduplicated TEST rows × 32**, 58,205 surviving sparse calls and 4,707 sampled deaths. Zero shared-residue, joint gold/Dagger, HP, potion-count, RNG, Writhing structure, other persistent, non-native Dagger or downstream-after-death violations. These are bounded development gates. Actual live-support rows recovered remain **0** until native export and final composition qualification.

Bound receipts: [native audit](sparse-native-v2.json), [Writhing fit](writhing-v1-fit.json), [Dagger fit](ritual-v1-fit.json), [Writhing exact exposure](writhing-v1-exact_exposure_encoder_refit.json), [Dagger exact exposure](ritual-v1-exact_exposure_encoder_refit.json), [maxHP refit](maxhp-encoder-v1-fit.json), [combined hard validity](sparse-combined-validity-v1.json). Separate upstream receipts are included alongside these files. Each carries its executed source SHA and artifact/input bindings.

## Stage 3 — native Brew generation and shared learned trajectory

The native combat-limited Ironclad return pool has 32 potion types: 65% common, 25% uncommon, 10% rare, uniform within rarity after excluding Fruit Juice. Brew and Smoke remain possible results. Limited generation discards the initial pool candidate and uses bounded rejection draws. Every Brew use generates **potionCapacity** potions, even when full capacity or Sozu prevents insertion; insertion uses the first empty legal slot.

The explicit-origin native generator reproduces all **3,208** pre-Brew rows and **3,106** generation rounds with zero potion RNG end-state mismatches. There are 112 recursive Brew-consumption cases and 88 escape rows. Generated-body labels are teacher targets reconstructed from RAW transitions; historical RNG is not a fair-model input. [Audit](brew-native-label-audit-v1.json), [native generator replay and origin comparison](brew-native-generation-v2.json).

The user resolved the origin contract: use a planner-owned fresh native hypothetical potion RNG on first Brew use, reuse it for recursive generations and write its advanced state into sampled RAW. Historical potion RNG reconstructs teacher labels only. An unused Brew branch copies its inherited potion RNG; a used branch never restores that RNG after hypothetical generation.

The shared 64-action potion decoder distinguishes special USE from DISCARD, including legal Smoke discard at bosses. It exactly marginalizes compatible teacher trajectories and records generated Colorless/Skill/Forge effects. The 112 proven recursive cases comprise 108 surviving rows (86 TRAIN / 11 VALIDATION / 11 TEST) and four deaths; multiple rounds from multiple initially held Brews are not automatically recursive. No separate Transmutation+ distribution or new data was collected.

A native joint target audit covers all 491,897 surviving corpus transitions, including 3,001 escapes, 4,363 Writhing and 12,690 Ritual Dagger rows, with zero native representation failures. This is target representability, not model composition qualification.

## Stage 4 — explicit ESCAPE and native continuation oracle

The sampler interface represents `ESCAPE` separately from `VICTORY`. Adapter continuation requires RAW `smokeBombUsed` to agree with the outcome, applies RAW state and invokes native continuation. An actual Smoke Bomb exit versus explicit ESCAPE injection from the **identical prebattle origin** passes exact OOC/persistent/all-RNG/PathHistory equivalence, no-reward map return and parent preservation. Fixtures cover both with and without Face of Cleric and native reset of a pre-existing used flag. Escape mislabeled as victory is rejected. Boss escape is rejected and its native potion remains unconsumed; Surrounded blocks consumption until the status is removed. Historical samplers still emit only their previously supported outcomes. Smoke exclusions remain until learned outcome probabilities and composition qualify; Brew-generated Smoke probabilities depend on Stage 3.

## Stage 5 and final qualification

The entire candidate union has been refitted with the existing architectures and original source-grouped TRAIN/VALIDATION selection: survival, maxHP, HP and shared potion encoders/heads, then shared relic/gold/Writhing/Ritual heads. Selected TEST NLLs: survival 0.060412, maxHP 0.053423, HP 2.507614, conditional potion trajectory 0.504572; downstream normalized joint target NLL 1.344312. These component losses do not establish composition qualification.

Whole-union RAW validity and exposure evaluation completed on all 51,441 TEST rows, including the previously qualified 41,454 rows. All later diagnostics are development evidence on the original reused TEST. In particular the Stage-2 Writhing TEST failure motivated the maxHP repair, so its repaired gap is not untouched confirmation.

The user confirms that no separate #180 saved imagined-state corpus is known. Available tracked CSV/support JSONL contain aggregate per-seed and first-failure counts only. Exact before/after state replay is **unavailable**, is not inferred by subtracting aggregates, and does not block Stages 3–5.

### Executed full-union composition and stop

The complete original TEST has 51,441 rows: old #179 support 41,454 (39,919 surviving targets), newly recovered candidate rows 9,987 (9,711 surviving targets). The original all-row candidate census covers 510,030 rows with zero remaining source/target representability failures. Candidate eligibility is **not** qualified runtime support.

Full-union exposure source `b26643393c0e6356f18bd22ba31d4d1f677ab1d1`, original full-union candidate weights:

| Component | Full informative union gap | Old #179 gap | Newly recovered gap |
| --- | ---: | ---: | ---: |
| HP (exact maxHP marginal) | +0.012821 | +0.011774 | +0.017126 |
| Potion trajectory | +0.004097 | +0.003758 | +0.005492 |
| Relic (per observed group) | +0.000416 | -0.002470 | +0.011565 |
| Gold | +0.019119 | deterministic old population | +0.019119 |
| Ritual Dagger | -0.000279 | no applicable old rows | -0.000279 |
| Writhing Mass | +0.088853 | no applicable old rows | +0.088853 |

These aggregate passes do **not** qualify the final union. On 102 informative Smoke Bomb TEST rows, relic exposure is **+0.242637 nat**, source-bootstrap 95% CI **[+0.088666, +0.409294]**, versus the required mean gap <=0.1. There are zero exact target-mass failures. [Full exposure receipt](full-union-exposure-v1.json).

All 51,441 TEST rows receive 32 full ancestral RAW draws: **1,646,112** draws, 62,347 sampled deaths, 1,574,266 victories, 9,499 escapes, 10,217 Brew uses and 354 sampled recursive trajectories. Zero recorded HP/maxHP, potion, joint gold/Dagger-budget, Writhing/deck, relic-residue, RNG, escape-flag/boss, or downstream-after-death violations. Death exits before querying downstream models; the focused sampler test also verifies this. Native escape continuation has the separate exact real-Smoke oracle; this corpus check is RAW legality, not gameplay or complete combat-policy reachability. [RAW receipt](full-union-raw-v1.json).

The original full-union weights' survival NLL/Brier are 0.060412/0.0179865. Exact maxHP-marginal HP NLL/Brier/CRPS/mean MAE are 2.520435/0.752391/3.622578/5.322113. MaxHP NLL/Brier/CRPS/mean MAE are 0.053423/0.032505/0.055558/0.104384. Old/recovered/union quality is separated in the [quality receipt](full-union-quality-v2.json). Generated potion-body identity NLL is supplied by the exact native law: 11.128156 over 306 TEST generation rows /317 rounds; use and retention likelihood is learned separately. Full-union conditional Brew-use/escape Monte Carlo Briers are 0.00051134/0.00080878, diagnostics at 1/32 probability resolution rather than exact-mass gates.

Three bounded relic-decoder repairs keep the original corpus/splits and frozen other heads:

| Repair | Selected epoch | Smoke relic TEST gap | Outcome |
| --- | ---: | ---: | --- |
| Added explicit escape coefficient fixed to zero | 1 | +0.199237 | FAIL |
| Exact teacher anchor plus two fixed ancestral contexts | 10 | +0.201889 | FAIL |
| Same contexts, balanced shared native Brew/Smoke route loss | 2 | +0.209178 | FAIL |

Original VALIDATION chooses each epoch, using the documented repair loss. No separate branch model or data collection. Non-relic gold/Writhing/Dagger weights remain bit-identical. The final attempted repair's source is `6ab63f40783b9955a978a2692e7af5460fb7c78a`; the exact checkpoint/context hashes and weighted loss are in [fit](full-union-downstream-v4-fit.json) and [focused exposure](smoke-relic-exposure-v4.json). Its Smoke gap CI is [+0.076693, +0.364132]. None of these candidates is promoted to a qualified runtime artifact.

The failure concentrates in ordinary-victory Smoke rows where the ancestral potion model predicts escape, changing the relic head's conditional residue distribution. **Inference:** the outcome/HP/potion/relic correlation needs a stronger model repair; the bounded head repairs have not qualified it. No missing native mechanic or new-data requirement is proven. The failing visible population has 1,005 informative surviving corpus rows: 808 TRAIN, 95 VALIDATION, 102 TEST (0.197047% of the entire corpus). Pre-Smoke presence itself has 3,765 corpus rows. Frequency does not excuse the failed mechanism gate.

Exact finite Writhing integration additionally reports +0.091256 over 449 ordinary-potion TEST rows. The 31 Writhing/Ritual overlap rows have +0.121732, and a shared maxHP head repair with an audited native coarse target gives +0.119052. The evaluator retains numerical threshold flags for every intersection. The report treats these overlap results as visible diagnostics; the handoff requests independent Writhing and Dagger mechanism gates, not an independent learned distribution for every feature intersection. The coarse target excludes available Fruit Juice because its native +5/+10 gain can confound the implantation/maxHP partition; the earlier unbounded exploratory receipt is retained, not promoted. [Exact receipt](full-union-writhing-exact-v1.json), [bounded maxHP fit](full-union-maxHP-v3-fit.json), [overlap diagnostic](writhing-ritual-exact-v3.json).

The user handoff's stop rule is now reached: bounded repair has not made Smoke/relic composition reliable under the required gate. Missing qualification is the outcome/HP/potion/relic correlation, with **no smallest additional corpus collection proven necessary**. Further correlation/factorization work needs an independently reviewed design rather than silently widening support or weakening the gate.

Historical full-union classification (superseded by the final bounded cohort above): **NEAR_FULL_COMBAT_SUPPORT_NOT_READY**. At that stop, live support remained 413,799/510,030 overall (81.132286%) and 41,454/51,441 TEST (80.585525%); actual rows recovered at runtime at that stop: **zero**. The entire original residual 96,231 rows was still rejected by the then-unchanged native predicate. For that historical full-union scope, a new runtime artifact, Python/native parity and MCTS supported-sampling integration were **not run**, because full-union qualification failed. Historical runtime artifact hash: **none**. No new data or gameplay ran. Final end-to-end gameplay evidence requires independent review of a final qualified frozen artifact. #180 state replay is explicitly unavailable and is not the blocker.

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
- Earlier continuation: 17 focused gold/sparse/Brew tests PASS; Debug `one_combat` build PASS; focused native adapter CTest PASS, including exact escape oracle. Affected maxHP refit and bound exposure/native validity complete as reported above.
- Final continuation: worktree/submodule check PASS; seven focused CTests PASS (33 constituent tests, 6.15 s), including death short-circuit and compatible-posterior gradient checks. Original deployed runtime/export/support files have zero diff from reviewed `8420103`.
- Not run: independent final scientific/implementation review, new native model export/probability parity/support expansion, new data/game campaigns/gameplay. Full-stack refit and final-union development qualification were run and failed as reported above. Final-head authoritative Linux GCC CI is recorded in the PR.

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

Integration refresh: merged main `876e9305a258df3d5a5eafd50e30375b933f8884` into the published task branch without rewriting history. The experiment baseline and source-bound model receipts remain unchanged; ledger entries are now §§254–257 after main’s §§250–253. Final integration SHA and CI are recorded in draft PR #182.
