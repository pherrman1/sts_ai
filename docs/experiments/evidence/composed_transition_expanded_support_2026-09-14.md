# Frozen expanded-support composed transition qualification

**EXPANDED_COMPOSED_TRANSITION_QUALIFIED.** This experiment tests whether #178's mechanically
valid 80.586% TEST support inherits composition qualification from #174's
original 62.526% subset. #174 evidence is preserved without modification.
Original source-grouped TEST is reused engineering validation, not untouched
holdout evidence. No model training, refitting, tuning, recalibration, new data,
support change, runtime optimization or gameplay was performed.

## Provenance and partition identity

User accepted current clean main instead of the older proposed baseline.
Baseline `74d31681b8ebd3beb5e85d6db9c1a164f9aeaf13`; independently reviewed scoring SHA `66d62987308e200f1abbfaa92d3fff67b3370ac7`.
The final evidence-only head is recorded in the draft PR and Git history.
The six frozen model, corpus, split and prepared-representation hashes were
verified before scoring and are recorded in the [JSON evidence](composed_transition_expanded_support_2026-09-14.json).

| Partition | Rows | Sources | Observed victories |
| --- | --- | --- | --- |
| OLD | 32164 | 2474 | 31150 |
| RECOVERED | 9290 | 893 | 8769 |
| EXPANDED | 41454 | 2512 | 39919 |

Rows are identified by original corpus index and original sourceSeed. OLD
membership equals the hashed historical #174 TEST receipt exactly. OLD and
RECOVERED have disjoint row IDs and their union equals EXPANDED; source sets may
overlap, so source counts are not additive. Current support equals the frozen
#178 predicate. Explicit Alchemize and Entropic Brew remain excluded. All
510,030 corpus rows were audited; current full support is 413,799 rows and
41,454/51,441 TEST rows. No independent support exclusion was relaxed.

## OLD reproduction stop gate

All reproduced component/exposure metrics and row teacher NLLs are within the
existing 1e-5 tolerance. The ordered evaluator completes OLD, checks the
historical result, and only then scores EXPANDED. Historical survival comparison
uses its original global-support cohort; the cohort survival metrics below use
each named support partition. Original #174 relic full-vector reproduction
retains its carrier convention; this packet's full-vector mode exact includes
all victory rows, including trivially exact empty relic vectors.
The OLD exposure entries in the cohort table use OLD rows sliced from the new
EXPANDED ancestral stream. The separate OLD-alone run preserves the historical
ordering and reproduces #174 exactly; changing the number of rows in the new
stream changes the sampled potion/relic draws for OLD, without changing models
or qualification definitions.

| Reproduction metric | Signed error |
| --- | --- |
| exposure.hp.mean | 0.000000000 |
| exposure.hp.mixtureNll | 0.000000000 |
| exposure.hp.teacherNll | 0.000000000 |
| exposure.potion.mean | 0.000000000 |
| exposure.potion.mixtureNll | 0.000000000 |
| exposure.potion.teacherNll | 0.000000000 |
| exposure.relic.mean | 0.000000000 |
| exposure.relic.mixtureNll | 0.000000000 |
| exposure.relic.teacherNll | 0.000000000 |
| historicalSurvival.auc | 0.000000000 |
| historicalSurvival.brier | 0.000000000 |
| historicalSurvival.logloss | 0.000000000 |
| hp.teacherMaxAbs | 0.000000000 |
| maxHp.modeAccuracy | 0.000000000 |
| maxHp.nll | 0.000000000 |
| potion.jointMaskNll | 0.000000000 |
| potion.modeExact | 0.000000000 |
| potion.teacherMaxAbs | 0.000000000 |
| relic.constraintNll | 0.000000000 |
| relic.fullVectorExact | 0.000000000 |
| relic.teacherMaxAbs | 0.000000000 |
| signedHp.crps | 0.000000000 |
| signedHp.expectedMae | 0.000000000 |
| signedHp.nll | 0.000000000 |

## Component diagnostics

Survival uses every row in each support partition. Downstream metrics use
observed victories and teacher-forced true upstream state. Relic constraint NLL
is the partial full-vector constraint mass; informative-row counts identify
where learned trajectory groups were observed. These metrics are diagnostic.

| Metric | OLD | RECOVERED | EXPANDED |
| --- | --- | --- | --- |
| Survival Brier | 0.016413115 | 0.028133844 | 0.019039775 |
| Survival log loss | 0.054881630 | 0.093882124 | 0.063621790 |
| Survival AUC | 0.980805861 | 0.968125150 | 0.978065501 |
| maxHP NLL | 0.049227638 | 0.090764082 | 0.058351942 |
| maxHP mode accuracy | 0.978587480 | 0.960314745 | 0.974573511 |
| Signed HP NLL | 2.371751655 | 2.981535576 | 2.505702786 |
| Signed HP CRPS | 3.432251386 | 4.544047775 | 3.676479511 |
| Expected HP MAE | 5.036824002 | 6.629118169 | 5.386602993 |
| Potion joint-mask NLL | 0.504139860 | 0.652127524 | 0.536648285 |
| Potion mode exact | 0.805264848 | 0.746835443 | 0.792429670 |
| Relic constraint NLL | 0.490337976 | 0.881870220 | 0.576345798 |
| Relic full-vector mode exact | 0.814060995 | 0.677386247 | 0.784037676 |
| Informative relic rows | 7414.000000000 | 3601.000000000 | 11015.000000000 |

## Composition exposure and decision gates

Same ancestral factorization as #174: survival → sampled ΔmaxHP → stochastic
signed ΔHP → joint potion mask → shared relic trajectory → persistent state.
Historical FP32/FP16 attention arithmetic and legality masks are unchanged.
HP uses exact probability marginalization over all eleven maxHP classes.
Potion/relic use the same 32-draw probability-before-log mixture. Relic row gaps
are divided by the number of observed learned groups and averaged only over
informative rows. Source bootstrap uses seed 20260917 and 1,000 resamples;
ancestral seed is 20260916. CIs are descriptive; each mean gap must be <=0.1 nat
independently on RECOVERED and EXPANDED. OLD cannot hide a RECOVERED failure.

| Partition | Component | Rows | Sources | Gap nats | 95% source CI | Gate |
| --- | --- | --- | --- | --- | --- | --- |
| OLD | hp | 31150 | 2474 | 0.012241622 | [0.009743450, 0.014807776] | EXPOSURE_OK |
| OLD | potion | 31150 | 2474 | 0.000767588 | [0.000545799, 0.001000076] | EXPOSURE_OK |
| OLD | relic | 7414 | 909 | -0.000878655 | [-0.003634083, 0.002163038] | EXPOSURE_OK |
| RECOVERED | hp | 8769 | 871 | 0.019484613 | [0.014790354, 0.024908487] | EXPOSURE_OK |
| RECOVERED | potion | 8769 | 871 | 0.000565261 | [-0.000038728, 0.001160546] | EXPOSURE_OK |
| RECOVERED | relic | 3601 | 465 | -0.002278852 | [-0.006496149, 0.002097758] | EXPOSURE_OK |
| EXPANDED | hp | 39919 | 2512 | 0.013832688 | [0.011592087, 0.016428043] | EXPOSURE_OK |
| EXPANDED | potion | 39919 | 2512 | 0.000723143 | [0.000521837, 0.000954464] | EXPOSURE_OK |
| EXPANDED | relic | 11015 | 1202 | -0.001336405 | [-0.003720422, 0.001011381] | EXPOSURE_OK |

## Complete ancestral hard validity

Full EXPANDED sampling contains **1,326,528 transitions** (32 per row). RECOVERED contains **297,280 transitions**. Complete draw membership, dimensions and per-row call receipts were verified independently. Sampled deaths terminate before all downstream encoders/heads.

| Counter | OLD | RECOVERED | EXPANDED |
| --- | --- | --- | --- |
| crossRelicResidueInconsistency | 0 | 0 | 0 |
| deterministicNativeMismatch | 0 | 0 | 0 |
| downstreamModelInvokedAfterDeath | 0 | 0 | 0 |
| hpAboveSampledMaxHp | 0 | 0 | 0 |
| hpBelow1 | 0 | 0 | 0 |
| illegalRelicCounter | 0 | 0 | 0 |
| invalidInheritedRngReconstruction | 0 | 0 | 0 |
| invalidMaxHpClassOrState | 0 | 0 | 0 |
| invalidPotionTransition | 0 | 0 | 0 |
| potionCreationSwapSubstitution | 0 | 0 | 0 |
| unsupportedMutableRelicMutation | 0 | 0 | 0 |

Zero means no observed violation in this frozen 32-draw-per-row engineering
validation; it is not a proof of gameplay performance. Native assembly validates
copy-through, potion closure, relic legality/shared residues and exact inherited
OOC RNG continuation. The independent raw checker separately reconstructed the
same constraints and reconciled model-call receipts. The existing raw format
omits some sampled persistent fields and the original sampled relic residue;
the independent checker proves a common residue exists from saved full vectors
and audits inherited RNG/copy-through from original states. Assembly of omitted
fields remains covered by implementation review, rather than independent
inspection of every serialized sampled field.

## RECOVERED slice diagnostics

All slices are diagnostic, with no per-card significance tests or tuned gates.
Card slices overlap. The recovered census contains only COMBUST (ID 73) and
BRUTALITY (ID 47), both labeled GREEN by this simulator's cardColors metadata.
The result therefore validates these recovered decks and does not establish
accuracy for unobserved off-color card IDs. Off-color count counts visible card entries outside the
historical RED/COLORLESS/CURSE certification set; every recovered row necessarily
has at least one such card. Empty slices are omitted, not assigned fabricated
metrics. Survival AUC is explicitly undefined in single-outcome slices; learned
relic exposure is undefined if a slice has no informative relic rows. All slice
component metrics, source CIs and row counts are retained in JSON.

| Slice | Rows | Sources | Brier | HP NLL | Potion NLL | Relic NLL | HP gap | Potion gap | Relic gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| act:1 | 1902 | 471 | 0.009439598 | 2.873970224 | 0.578559937 | 0.308367682 | 0.002752306 | 0.001859242 | 0.004374329 |
| act:2 | 4115 | 729 | 0.034513063 | 3.112352876 | 0.687467270 | 0.793519899 | 0.015886946 | 0.000584388 | -0.002829557 |
| act:3 | 3273 | 502 | 0.030977099 | 2.882155811 | 0.652455490 | 1.343492940 | 0.034239684 | -0.000248907 | -0.003012840 |
| card:BRUTALITY | 4511 | 527 | 0.032596999 | 2.972287065 | 0.663689141 | 0.959139302 | 0.019843553 | -0.000196336 | -0.002867341 |
| card:COMBUST | 5563 | 462 | 0.025521684 | 2.989560148 | 0.644945232 | 0.810233367 | 0.019625357 | 0.001090084 | -0.000781843 |
| combat:boss | 1321 | 776 | 0.100952135 | 3.871234345 | 1.212065531 | 1.064773227 | 0.007225909 | -0.000111653 | -0.010528219 |
| combat:elite | 2390 | 783 | 0.031652448 | 3.550844999 | 0.960790189 | 0.879988707 | 0.014172774 | 0.000765345 | -0.008092230 |
| combat:event | 205 | 183 | 0.028617309 | 3.089127029 | 0.828789661 | 1.137820067 | 0.018219310 | 0.000967498 | 0.012452858 |
| combat:normal | 5374 | 848 | 0.008650863 | 2.567928126 | 0.409113537 | 0.839291575 | 0.024084590 | 0.000589039 | 0.001358990 |
| offColorCount:1 | 7879 | 874 | 0.026682907 | 2.975551382 | 0.650721123 | 0.869846011 | 0.018434899 | 0.000675866 | -0.002700123 |
| offColorCount:2 | 1265 | 166 | 0.035061455 | 2.996508383 | 0.657976654 | 1.015808191 | 0.025742131 | -0.000048376 | -0.001514019 |
| offColorCount:3 | 144 | 22 | 0.047040831 | 3.197060167 | 0.689150250 | 0.377002096 | 0.023125481 | -0.000187286 | 0.025110876 |
| offColorCount:4 | 2 | 1 | 0.001081936 | 2.229042057 | 0.000000000 | -0.000000064 | 0.000060854 | 0.000000000 | undefined |
| offColorPresent | 9290 | 893 | 0.028133844 | 2.981535576 | 0.652127524 | 0.881870220 | 0.019484613 | 0.000565261 | -0.002278852 |

Common recovered off-color cards by row presence:

| Card ID name | Recovered rows |
| --- | --- |
| BRUTALITY | 4511 |
| COMBUST | 5563 |

## Verification, raw evidence and handoff

Independent implementation review passed before scoring SHA freeze. 22 focused
unittests and 2/2 composed/expanded-support CTests passed. CMake debug-ccache
configuration, environment doctor (with a writable temporary uv cache), repo
health and git diff --check passed. Optional torch absence yields four clean
skips, matching the existing composed evaluator's CI convention. Full local C++
build/CTest was not repeated because no C++ implementation changed; GitHub
Actions Linux GCC remains authoritative and is reported in the draft PR.

Independent raw-output reproduction passed; its report and all artifact hashes
are included in JSON. Raw output is preserved at:

`/home/philippherrmann/sts_sweep/runs/composed-transition-expanded-support-20260914`.

```sh
python3 -m tools.combat_transition_expanded_support prepare --output-dir /tmp/composed-expanded-support-20260914
python3 -m tools.combat_transition_expanded_support evaluate --output-dir /tmp/composed-expanded-support-20260914 --reviewed-sha 66d62987308e200f1abbfaa92d3fff67b3370ac7
python3 /tmp/composed-expanded-independent-review.py /tmp/composed-expanded-support-20260914
python3 -m unittest tools.test_combat_transition_composed tools.test_combat_transition_expanded_support -v
ctest --test-dir build/linux-gcc-debug-ccache -R 'combat_transition_(composed|expanded_support)_selftest' --output-on-failure
git diff --check
```

Expanded support passes the requested offline composition prerequisite for a
next fresh MCTS gameplay gate. This does not establish improved win rate or
justify enabling MCTS by default; fresh-gate runtime/readiness and provenance
requirements still apply.

Knowledge impact: experiment evidence plus maintained current research status;
the stable evaluator navigation is updated in CODE_MAP.
