# Completed campaign results

Presentation of frozen reports only. Every recorded decision is reproduced verbatim. Controls remain within their original phase/source; no pooled control, combined efficacy estimate or campaign cost total is produced.

Full-run comparison effects and intervals are in percentage points, candidate minus control. C-only/B-only are the two paired discordances. The reported paired bootstrap intervals are copied, not recalculated.

| Report / phase | Source SHA | Candidate / control | Pairs | Wins C / B | C-only / B-only | Gain [95% CI], pp | Raw decision |
|---|---|---|---:|---:|---:|---|---|
| W1 / discovery | `736d1ff7e617` | Fflat / Fprod | 32 | 26 / 25 | 4 / 3 | +3.125 [-12.500, +18.750] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W1 / discovery | `736d1ff7e617` | ShopFix / Fprod | 32 | 27 / 25 | 2 / 0 | +6.250 [+0.000, +15.625] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W1 / discovery | `736d1ff7e617` | RestOff / Fprod | 32 | 28 / 25 | 4 / 1 | +9.375 [-3.125, +21.875] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W1 / discovery | `736d1ff7e617` | BossOff / Fprod | 32 | 24 / 25 | 1 / 2 | -3.125 [-15.625, +6.250] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W1 / discovery | `736d1ff7e617` | SkipZero / Fprod | 32 | 25 / 25 | 5 / 5 | +0.000 [-18.750, +18.750] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W1 / discovery | `736d1ff7e617` | ShopOff / Fprod | 32 | 27 / 25 | 3 / 1 | +6.250 [-6.250, +18.750] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W1 / discovery | `736d1ff7e617` | FinalBinary / Fprod | 32 | 26 / 25 | 4 / 3 | +3.125 [-12.500, +18.750] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W1 / discovery | `736d1ff7e617` | FinalBinary / Fflat | 32 | 26 / 26 | 0 / 0 | +0.000 [+0.000, +0.000] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W2 / development | `3ed91ab3491a` | RestOff / Fprod | 128 | 97 / 101 | 10 / 14 | -3.125 [-10.156, +4.688] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W2 / development | `3ed91ab3491a` | ShopFix / Fprod | 128 | 99 / 101 | 1 / 3 | -1.562 [-4.688, +1.562] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W2 / development | `3ed91ab3491a` | RestShop / Fprod | 128 | 91 / 101 | 10 / 20 | -7.812 [-16.406, +0.781] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W2 / development | `3ed91ab3491a` | RestShop / RestOff | 128 | 91 / 97 | 2 / 8 | -4.688 [-9.375, +0.000] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W2 / development | `3ed91ab3491a` | RestShop / ShopFix | 128 | 91 / 99 | 9 / 17 | -6.250 [-14.062, +1.562] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W3 screen / discovery | `b229f3ff2443` | FullHp / Fprod | 32 | 27 / 26 | 1 / 0 | +3.125 [+0.000, +9.375] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W3 screen / discovery | `b229f3ff2443` | ShopOff / Fprod | 32 | 27 / 26 | 3 / 2 | +3.125 [-9.375, +15.625] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W3 development / development | `b229f3ff2443` | FullHp / Fprod | 128 | 102 / 101 | 4 / 3 | +0.781 [-3.125, +4.688] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| W3 development / development | `b229f3ff2443` | ShopOff / Fprod | 128 | 102 / 101 | 10 / 9 | +0.781 [-5.469, +7.812] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| Removal screen / discovery | `d35b42b1d5dc` | RemoveLow / Fprod | 32 | 27 / 26 | 1 / 0 | +3.125 [+0.000, +9.375] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| Removal development / development | `d35b42b1d5dc` | RemoveLow / Fprod | 128 | 106 / 104 | 7 / 5 | +1.562 [-3.906, +7.031] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |
| Card rank screen / discovery | `5add2413281c` | CardWinRank / Fprod | 32 | 22 / 26 | 4 / 8 | -12.500 [-34.375, +9.375] | `DISCOVERY_OR_DEVELOPMENT_ONLY` |

W1 is the early fair-public diagnostic before the optional-Recall correction. Later corrected-reference results are separate. Discovery cohorts were reused adaptively for screening; they are not fresh qualification samples. Full-run win counts concern the fixed Act-3 endpoint.

Observed cost, listed once per report/arm. CPU is the reported sum of profile thread-CPU seconds, not total machine utilization. Wall is the sum of invocation process durations, not parallel campaign elapsed time. A control repeated in comparison rows has only this one cost row; controls from overlapping seed cohorts are not pooled or presented as independent efficacy evidence.

| Report | Arm | Runs | Observed profile CPU, s | Summed process wall, s |
|---|---|---:|---:|---:|
| W1 | Fprod | 32 | 434.716 | 436.356 |
| W1 | Fflat | 32 | 991.259 | 993.016 |
| W1 | ShopFix | 32 | 449.010 | 450.681 |
| W1 | RestOff | 32 | 444.512 | 446.255 |
| W1 | BossOff | 32 | 423.844 | 425.457 |
| W1 | SkipZero | 32 | 386.699 | 388.371 |
| W1 | ShopOff | 32 | 458.512 | 460.121 |
| W1 | FinalBinary | 32 | 1016.658 | 1018.521 |
| W2 | Fprod | 128 | 1614.192 | 1620.213 |
| W2 | RestOff | 128 | 1533.099 | 1539.205 |
| W2 | ShopFix | 128 | 1575.820 | 1581.814 |
| W2 | RestShop | 128 | 1506.954 | 1512.839 |
| W3 screen | Fprod | 32 | 437.032 | 438.701 |
| W3 screen | FullHp | 32 | 435.442 | 437.176 |
| W3 screen | ShopOff | 32 | 468.633 | 470.274 |
| W3 development | Fprod | 128 | 1727.171 | 1733.574 |
| W3 development | FullHp | 128 | 1729.206 | 1736.242 |
| W3 development | ShopOff | 128 | 1676.540 | 1683.049 |
| Removal screen | Fprod | 32 | 459.744 | 461.945 |
| Removal screen | RemoveLow | 32 | 478.638 | 480.487 |
| Removal development | Fprod | 128 | 1671.180 | 1677.937 |
| Removal development | RemoveLow | 128 | 1721.724 | 1728.290 |
| Card rank screen | Fprod | 32 | 421.952 | 423.603 |
| Card rank screen | CardWinRank | 32 | 429.561 | 431.231 |

Conditional probes remain separate from whole-run policy evidence. GEN2 wins/discordances below are descriptive totals over correlated state/future pairs; its gain and CI use the frozen equal-source estimand. Those totals must not be used to replace the source-cluster analysis. REST and Champ each have one selected source state; their intervals resample conditional future pairs.

| Probe / rule | Sources / states | Conditional pairs | Wins C / B | C-only / B-only | Gain [95% CI], pp | Exact recorded classification |
|---|---:|---:|---:|---:|---|---|
| GEN2 canary / rollout | 4 / 8 | 16 | 16 / 16 | 0 / 0 | +0.000 [no CI recorded] | No per-rule classification recorded |
| GEN2 canary / P0-s0 | 4 / 8 | 16 | 15 / 16 | 0 / 1 | -6.250 [no CI recorded] | No per-rule classification recorded |
| GEN2 canary / F2-s0 | 4 / 8 | 16 | 15 / 16 | 0 / 1 | -6.250 [no CI recorded] | No per-rule classification recorded |
| GEN2 tranche / rollout | 32 / 63 | 252 | 204 / 208 | 11 / 15 | -1.172 [-5.469, +3.125] | `LOCAL_CONDITIONAL_INCONCLUSIVE` |
| GEN2 tranche / P0-s0 | 32 / 63 | 252 | 208 / 208 | 15 / 15 | +0.391 [-4.297, +5.469] | No per-rule classification recorded |
| GEN2 tranche / F2-s0 | 32 / 63 | 252 | 206 / 208 | 19 / 21 | -0.781 [-5.078, +3.125] | No per-rule classification recorded |
| Targeted REST / Upgrade Offering vs REST | 1 / 1 | 32 | 23 / 17 | 8 / 2 | +18.750 [+0.000, +37.500] | `LOCAL_CONDITIONAL_INCONCLUSIVE` |
| Champ D13 / SHRUG vs END (fight wins) | 1 / 1 | 62 | 50 / 51 | 9 / 10 | -1.613 [-14.516, +11.290] | `LOCAL_CONDITIONAL_INCONCLUSIVE` |

| Conditional report | Exact status | Recorded cost (seconds) |
|---|---|---|
| GEN2 canary | `DIAGNOSTIC_EVALUATION_COMPLETE` | `{"branch_cpu_seconds": 1291.933931, "invocation_wall_seconds_sum": 1355.5126197969948, "label_rows": 128, "source_cpu_seconds": 62.46158}` |
| GEN2 tranche | `DIAGNOSTIC_EVALUATION_COMPLETE` | `{"branch_cpu_seconds": 14550.502842, "invocation_wall_seconds_sum": 14956.732568327978, "label_rows": 1968, "source_cpu_seconds": 392.09429}` |
| Targeted REST | `EVALUATION_INTEGRITY_PASS` | `{"branch_cpu_seconds": 360.56808, "process_wall_seconds": 379.24484855899937, "source_cpu_seconds": 18.317}` |
| Champ D13 | `EVALUATION_INTEGRITY_PASS` | `{"cpu_seconds_by_arm": {"END": 264.492758, "SHRUG": 308.43536}, "process_wall_seconds": 575.8027501009929}` |

GEN2 collection cost covers source runs and all retained branches across both selection and evaluation futures, shared by all three frozen rules. It is not three independent per-rule costs. REST/Champ cost here is their evaluation-stage report only, excluding preparatory selection/canaries.

Conditional scope and limitations copied from the reports:

- **GEN2 canary**: Four allocated source runs and at most eight selected states: contract/representation diagnostic only, no population-strength claim. Retained action set only; early eligible CARD_REWARD/BOSS_RELIC states need not represent important later decisions. One future k is paired between sibling actions; different decisions within a source are not independent runs. Historical P0/F2 models omit four hidden encounter-queue features but retain E1 latent potion/rarity counters and privileged-teacher labels. Model predictions are averaged over legitimate selection-future post-action MAP states; no realized evaluation MAP is used for action selection. Historical export/native parity establishes arithmetic compatibility, not current-policy calibration or fair deployment qualification. No training, test-split access, policy installation, adaptive extension, or final confirmation qualification.
- **GEN2 tranche**: Thirty-two allocated source runs and at most64 selected states: conditional action-value diagnosis under the existing sampler, no population-strength claim. Retained action set only; early eligible CARD_REWARD/BOSS_RELIC states need not represent important later decisions. One future k is paired between sibling actions; different decisions within a source are not independent runs. Historical P0/F2 models omit four hidden encounter-queue features but retain E1 latent potion/rarity counters and privileged-teacher labels. Model predictions are averaged over legitimate selection-future post-action MAP states; no realized evaluation MAP is used for action selection. Historical export/native parity establishes arithmetic compatibility, not current-policy calibration or fair deployment qualification. The sampler preserves latent counters and pool membership; it is not an exact posterior of player-observable information. No training, test access, policy installation, adaptive extension, or final qualification.
- **Targeted REST**: One selected source decision under fixed public-conditioning sampler and old631f teacher; not32 independent full runs. Confidence interval resamples32 paired future draws conditional on this source; it does not include source-selection or teacher-distribution uncertainty. Optional Ruby Recall defect remains in this diagnostic teacher. No corrected-reference qualification, policy promotion, or training claim. Frozen selection used k0..15. Only k16..47 contribute to this evaluation; no reselection or sample extension.
- **Champ D13**: One outcome-informed historical public root, not62 independent source decisions. Fresh exact10k per decision with fixed public search seed0; original retained learned-stop policy is unavailable. Conditional public-future sampling, not reconstruction of the historical hidden RNG. No Act3 population-strength or production-promotion claim; canaries excluded; no extension.

The GEN2 tranche rollout rule is the preregistered primary; P0/F2 are secondary exploratory rules. The four-source canary is descriptive only. Champ measures a single fight outcome, whereas REST/GEN2 continuations use the recorded run endpoint.

Frozen report identities (no referenced raw inputs were opened):

| Report | SHA256 |
|---|---|
| [W1](/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/docs/experiments/evidence/ironclad_a0_overnight_20261008/wave1_report.json) | `ca81039a2c73299f971d28a9d7819cf635d159e320f2bdbb0bd3736e1f52396d` |
| [W2](/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/docs/experiments/evidence/ironclad_a0_overnight_20261008/wave2_report.json) | `bb795afe5a5057b760eec592ca2a86ddbe6c1c68f7fde490fb3dcd3e1247c405` |
| [W3 screen](/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/docs/experiments/evidence/ironclad_a0_overnight_20261008/wave3_report.json) | `d2dc463939de18517222f66c790b2a6dedfb8362a0212ffa59579440a1badc67` |
| [W3 development](/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/docs/experiments/evidence/ironclad_a0_overnight_20261008/wave3_development_report.json) | `3d2d236871cbcb8890e82c65e4e61e4d145698c9e34ce80a8ecd661f61519723` |
| [Removal screen](/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/docs/experiments/evidence/ironclad_a0_overnight_20261008/wave4_removal_report.json) | `f405de50965522e4cee17cb103a22688ad663f2d2cf8f3c5372439cd44fbf0fd` |
| [Removal development](/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/docs/experiments/evidence/ironclad_a0_overnight_20261008/removal_development_report.json) | `91afa7dc02117114b75206fc07f7a77532146a0bff6948e44a996637bd6d10df` |
| [Card rank screen](/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/docs/experiments/evidence/ironclad_a0_overnight_20261008/wave5_card_rank_report.json) | `51902c796b13ebdb80376eaeb98ba920bd29bd4813dedfecf4b786bc2d29b530` |
| [GEN2 canary](/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/docs/experiments/evidence/ironclad_a0_overnight_20261008/learning/gen2_probe_3ed9_evaluation.json) | `efa197f3b737825fae52595005cdaa8bd3fc3a980e77dfbe09785bfbe1e08bbc` |
| [GEN2 tranche](/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/docs/experiments/evidence/ironclad_a0_overnight_20261008/learning/gen2_tranche32_3ed9_evaluation.json) | `5ada874a05f6d947cf0a19435db681a01be89aa23b26ceb26b5c59414aff798f` |
| [Targeted REST](/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/docs/experiments/evidence/ironclad_a0_overnight_20261008/learning/targeted_rest_631f_evaluation_result.json) | `f075d65327dd180f1d99be639448a54c3a35873c194bdace93195ff85ad41fd7` |
| [Champ D13](/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/docs/experiments/evidence/ironclad_a0_overnight_20261008/audit/champ_d13_evaluation_report.json) | `269b1e792395de0c1d97cd5af2ae1d5ced2a2a65c436b651fd627bcd74da86c3` |

Knowledge impact: presentation of existing experiment evidence; no new analysis, verdict, policy or qualification claim.
