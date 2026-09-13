# Frozen survival composition and potion-decoder qualification

Date: 2026-09-13. Knowledge impact: frozen composition/support findings recorded in ledger §234 and maintained research status; stable adapter behavior recorded in the training/inference KB.

**Decisions:** `REPRODUCED_AND_CORE_PRESERVED`; `INSUFFICIENT_AFTER_CORRECTION`; deployment `NOT_QUALIFIED`.

This is prespecified inference on existing final PR #163 checkpoints. No fitting, new corpus, simulator seeds, gameplay integration, precision selection, calibration tuning, or global support change occurred. The final checkpoints saw TRAIN+VALIDATION; VALIDATION is not unseen, and the fixed TEST is reused for this engineering diagnostic. Bootstrap intervals describe source variability on that TEST, not variability across training runs.

## Baseline, frozen arms, and provenance

- Merged code baseline: `08799ad6bd9061459339d36a4e22cce23d0236ec` (PR #165, including #164 and #163). Executed diagnostic source hashes are in the [machine-readable evidence](frozen_survival_potion_2026-09-13.json); candidate SHA is supplied by the draft PR. Implementation has not been independently reviewed.
- A: original attention Phase-2 survival and conditional-on-victory outputs.
- B: exact frozen attention point-control survival, all conditional outputs from A.
- C: B, with certified consumption-only potion logits masked and renormalized. HP, max-HP, and relic distributions stay unchanged. Uncertified inputs keep B exactly.
- Supported TRAIN/VALIDATION/TEST counts remain 331,225 / 41,120 / 41,454. TEST has 39,919 victories and 1,535 deaths; 2,512 source groups.
- Every corpus row was reconciled with prepared source/fight order, actual frozen split membership, support flags, and pre/post potion inventories. Every source was also checked against the canonical source-hash split rule.

| Artifact | SHA256 |
| --- | --- |
| corpus | `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde` |
| phase2_attention.pt | `66ac8f70da69e29bf9b1364243f6f903e4f74dda1ec8a909ef54a7ea97dc6479` |
| point_control_attention.pt | `2447b2daf1a48a619a5f071488908afd6f0fb83bfd855ee9f379c04120efeaef` |
| prepared.npz | `2badbb85ccd8329bcb886d50ef8a0b9b1bd2c043fda9445de9f9c2e7a4b6f9a5` |
| prepared_manifest.json | `13b2c91fd0ced713f8c429bbf8995ceb58b6e3e57d1555de42f5e67d7f9a389f` |
| sourceSplit | `e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32` |
| target_spec.json | `e2315620d512578542d6b3bfbd362eb07b086f0e9fa7770cc23f4fa4c226e229` |

Original small checkpoints, manifests, support audit, and evidence are preserved at `/home/philippherrmann/sts_sweep/runs/frozen-survival-potion-20260913/`. Large prepared arrays remain referenced at `/tmp/sts-phase2-attention-audit-20260913/prepared.npz`; the frozen corpus and split remain in their existing durable `sts_sweep/runs` directories. No corpus duplication or checkpoint replacement occurred.

## A reproduction and B composition

All checked A aggregate numeric metrics reproduced exactly at historical batch 2,048 (maximum recorded difference 0). Historical potion mode accuracy also reproduced exactly. The initial batch-256 run changed one potion-vector mode: exact accuracy `0.491119517` versus published `0.491094466`; maximum logit difference `1.14440918e-5`, source-array row 403158. The isolated batch-sensitivity rerun confirmed this numerical mode sensitivity. Final comparisons use historical batching; no threshold or checkpoint was selected against TEST.

B defines `P(death|x)=1-p_point(x)` and `P(victory,T|x)=p_point(x)*q_phase2(T|x,victory)`. It neither averages survival probabilities nor refits weights. Both models stayed in eval/inference mode; parameters and buffers were verified unchanged, and normalization buffers are distinct. Conditional distributions were checked finite and normalized. Death draws terminate with no post-state.

| Metric | A | B/C | B minus A, paired source 95% |
| --- | ---: | ---: | --- |
| Survival Brier | 0.019920463 | 0.019039774 | -0.000880687 [-0.001289956, -0.000501706] |
| Survival log loss | 0.066628456 | 0.063621797 | -0.003006653 [-0.004202626, -0.001811162] |
| Winning HP fraction MAE | 0.067770742 | 0.067770742 | 0 [0, 0], preserved |
| Winning raw HP MAE | 5.403836250 | 5.403836250 | 0 [0, 0], preserved |
| Winning HP CRPS | 0.045763172 | 0.045763172 | 0 [0, 0], preserved |
| Joint alive-HP fraction MAE | 0.074977458 | 0.074275836 | -0.000701618 [-0.000874158, -0.000507510] |
| Joint alive raw HP MAE | 5.903266430 | 5.855357647 | -0.047908530 [-0.060634232, -0.034700484] |
| Joint outcome/max-HP-delta/HP-bin NLL | 2.690480035 | 2.687473382 | -0.003006653 [-0.004202626, -0.001811162] |

Deaths contribute only outcome NLL; victories add max-HP-delta and conditional HP-bin NLL. The rowwise identity `(NLL_B-NLL_A)=(outcome_NLL_B-outcome_NLL_A)` held to maximum error `1.47e-15`. Survival preservation is an implementation invariant. Improved joint HP error is measured, not assumed. These observations do not causally establish gradient interference.

## Certified potion rule and native-code basis

The predicate uses pre-input alone: Ironclad, visible deck card IDs with canonical RED/COLORLESS/CURSE metadata, and no Entropic Brew in inventory. Any off-class card makes the rule inapplicable, including Alchemize and Foreign Influence. IDs absent from canonical metadata are also uncertified. This deliberately conservative certification does not alter global surrogate eligibility.

Bounded audit at the recorded baseline:

- [BattleContext potion methods](../../../src/combat/BattleContext.cpp): `drinkPotion` consumes the same slot; `discardPotion` only empties it. `obtainPotion` fills an empty active slot, and the sole implemented combat caller is Entropic Brew. No other combat inventory assignment creates, moves, or duplicates an identity. `Player::wouldDie` consumes Fairy Potion through `discardPotion`.
- [Generated actions](../../../src/combat/Actions.cpp), [pool routing](../../../src/game/Game.cpp), and [native pools](../../../include/constants/CardPools.h): current combat/type pools contain Ironclad cards, including skill/power potion routes; colorless pools contain no Alchemize. Dead Branch and Discovery use combat pools, Nilry uses explicit Ironclad Discovery, Enchiridion uses the power pool, and Magnetism/Jack of All Trades use colorless pools. Metamorphosis/Chrysalis use combat type pools. Fixed generated cards such as Shiv/Miracle cannot obtain potions. This is current simulator behavior, not a general claim about off-class generation in the original game.
- Alchemize appears in card metadata/reward pools but has no combat case or obtain-potion action in this simulator; the default unimplemented-card path asserts in assert-enabled builds or performs no effect. Certification excludes off-class initial cards rather than relying on that omission. Prismatic Shard changes game reward pools, outside the RAW combat interval.
- `BattleContext::exitBattle` transfers slots/count and invokes the RAW observer before victory callbacks and `regainControl`; reward acquisition and `afterBattle` behavior are outside this boundary. The inherited Entropic Brew exclusion helps, but the complete inventory-write and pool audit supplies the certification basis.

Initially empty slots remain empty; unavailable slots copy through; occupied active slots can retain their exact identity or become EMPTY. Stable float64 masked log-softmax rejects nonfinite logits or mass failures. It never uses uniform/empty fallbacks. The draw samples only positive-mass indices, so roundoff is not assigned to a forbidden final class. Potion count is derived from resulting slots.

The all-row RAW audit certified 322,644/413,799 supported rows (77.97%). It found zero contradicting certified supported transitions, including deaths. On TEST victories, C applies to 31,150/39,919 (78.03%); 8,769 remain identical to B. Post-state/outcome labels are used only after fixing the predicate, for contradiction checks and scoring. Seed/RNG, target frequencies, and outcome never enter certification or the masks.

The historical potion head is one linear layer on concatenated global and slot embeddings. Its logits are `a(x)+b(slot)`, so differences in class log-odds between slots are independent of x. Its domain admits identities absent from the inventory. The frozen head and its weights are preserved.

## Potion results

All vector metrics are conditional on observed victory; unavailable slots have deterministic copy-through probabilities. NLL uses stable log probabilities without an arbitrary clipping floor. B and C are compared on identical rows.

| Slice / arm | Vector NLL | Vector mode exact | Changed exact | Unchanged exact | No-change Brier | Mean no-change probability | Count exact | Copy-through exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| overall / B | 1.891231 | 0.491094 | 0.394674 | 0.527093 | 0.352821 | 0.338714 | 0.741902 | 0.728150 |
| overall / C | 1.178422 | 0.597059 | 0.464338 | 0.646610 | 0.235101 | 0.450664 | 0.687642 | 0.728150 |
| certified / B | 1.757862 | 0.524815 | 0.413692 | 0.564198 | 0.335101 | 0.364935 | 0.758234 | 0.738331 |
| certified / C | 0.844391 | 0.660610 | 0.506441 | 0.715248 | 0.184242 | 0.508401 | 0.688700 | 0.738331 |
| uncertified / B | 2.364996 | 0.371308 | 0.337282 | 0.386454 | 0.415766 | 0.245567 | 0.683886 | 0.691983 |
| uncertified / C | 2.364996 | 0.371308 | 0.337282 | 0.386454 | 0.415766 | 0.245567 | 0.683886 | 0.691983 |

Overall changed/unchanged counts are 10,852/29,067; certified 8,151/22,999; uncertified 2,701/6,068. Copy-through predicts no change with probability 1; its event Brier is 0.271850 overall and 0.261669 certified. Thus C beats that event-probability comparator as well as B, but it still loses vector-mode accuracy to copy-through. Copy-through is not used as the sole probabilistic comparator or assigned a finite full-vector NLL on changed targets.

| C minus B | Overall paired source 95% | Certified paired source 95% |
| --- | --- | --- |
| vectorNll | -0.712809 [-0.737550, -0.686317] | -0.913471 [-0.939676, -0.888000] |
| exact | +0.105965 [+0.100580, +0.111278] | +0.135795 [+0.129582, +0.142575] |
| noChangeBrier | -0.117720 [-0.121934, -0.113683] | -0.150859 [-0.155540, -0.146357] |

Uncertified differences and intervals are exactly zero. All bootstrap comparisons use 1,000 source resamples: overall 2,512 sources, certified 2,474, uncertified 871. Source sets may overlap across applicability slices.

| Active slot NLL | Overall B | Overall C | Certified B | Certified C |
| --- | ---: | ---: | ---: | ---: |
| 0 | 0.734541 | 0.434173 | 0.690246 | 0.305323 |
| 1 | 0.635845 | 0.392460 | 0.598449 | 0.286549 |
| 2 | 0.482141 | 0.321548 | 0.441785 | 0.235983 |
| 3 | 0.375119 | 0.293499 | 0.327526 | 0.193304 |
| 4 | 0.203749 | 0.158799 | 0.197992 | 0.124072 |

B assigns mean invalid-vector mass `0.427566` on certified TEST victories, computed directly as `1-product_s(sum_allowed q_s)`. Its 5/50/95% quantiles are 0.001173 / 0.373137 / 0.956868. The illegal-vector mode rate is `0.340931`. C has zero forbidden support on certified inputs. All observed certified targets survive the mask and C never worsens per-row target NLL.

Masking recovers substantial likelihood/accuracy/calibration signal, but leaves 33.94% vector-mode error on certified rows. Overall count accuracy drops from 0.741902 to 0.687642; changed-row no-change-event Brier rises from 0.017611 to 0.042027. Improved aggregate event Brier does not imply all slices or count predictions improve. Classification is `INSUFFICIENT_AFTER_CORRECTION` because corrected vector-mode accuracy remains below copy-through, despite measured support correction benefits.

## Native validity limits and CPU cost

HP/max-HP and relic heads remain historical distributions. Positive max-HP mode checks find zero nonpositive outputs. HAPPY_FLOWER, NUNCHAKU, and INK_BOTTLE mode counters stay within audited native cyclic ranges, but SUNDIAL has eight invalid counters among 1,751 present TEST-victory tokens; its native counter range is 0..2 (`onShuffle` cycles at 2, exit copies that counter). Examples are in the JSON. No relic correction was applied. Allowed historical delta classes alone do not prove starting-state legality, and neither these range checks nor the earlier 16 shallow samples qualify a full native model.

| TEST input applicability | A mean ms | B mean ms | C mean ms |
| --- | ---: | ---: | ---: |
| certified | 1.9720 | 3.3788 | 3.4164 |
| uncertified | 2.0871 | 3.5530 | 3.5238 |

Same CPU (AMD Ryzen 5 7500F 6-Core Processor), PyTorch 2.5.1+cu121 FP32, one thread, batch 1, fixed widths, 10 warm-ups and 100 draws per arm per input. Boundary includes visible predictor-input validation/encoding, all required forwards (one for A, two for B/C), probability/support adapters, and one transition draw including copied state. Two representative existing TEST inputs are an illustrative microbenchmark, not a latency population estimate. All measured draws were victories; the early death path was not timed separately. Medians/p95 and draw outcomes are in JSON. CPU/GPU historical figures are not used as architecture speed ratios; training AMP gains do not imply inference speedups.

## Checks, raw outcomes, and execution

Raw logs and exact diagnostic sources are preserved in the external artifact directory above.

| Check | Raw outcome / log |
| --- | --- |
| Worktree preflight/check and doctor | Codex-app-managed task branch; pinned submodules OK; doctor all checks passed |
| `python3 -m unittest tools.test_combat_transition_frozen_composition tools.test_combat_transition_attention_ablation tools.test_combat_transition_surrogate -v` | Ran 33 tests; OK (`focused-final.log`) |
| Same modules under `.venv/bin/python` without Torch | Ran 33 tests; OK (skipped=7); all eight new checks run (`no-torch.log`) |
| Agent unittest discovery | Ran 145 tests; OK (`agent.log`) |
| Repository-health unittest | Ran 2 tests; OK |
| CMake `linux-gcc-debug-ccache` configure | Exit 0 (`configure.log`) |
| Affected CTest selftests | 3/3 passed (`ctest-focused.log`) |
| Full diagnostic command below | Exit 0; three decisions as reported (`run-final.log`) |

Fixtures cover two-potion swaps, substitution/duplication, initial empty slots, unavailable slots, retain/consume and multiple simultaneous consumptions, strict/nonfinite numerics, derived count, death termination, exact composition, and the joint NLL identity. Existing HP regression tests remain passing. The new CTest check requires no Torch; no PyTorch dependency was added to default CI.

```bash
python3 tools/combat_transition_frozen_composition.py \
  --prepared-dir /tmp/sts-phase2-attention-audit-20260913 \
  --artifact-dir /home/philippherrmann/sts_sweep/runs/frozen-survival-potion-20260913 \
  --split-manifest /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/split_manifest.json \
  --output-dir /home/philippherrmann/sts_sweep/runs/frozen-survival-potion-20260913 \
  --device cuda --nn-batch 2048 --threads 8 \
  --baseline-sha 08799ad6bd9061459339d36a4e22cce23d0236ec
```

No full local C++ build/CTest was needed for this Python diagnostic and CTest registration; GitHub Linux GCC is the authoritative clean-repository gate. Independent implementation/scientific review has not run. No fitting, unseen holdout, broad profiling, new simulator seeds, Silver gate, C++ export, native replay qualification, gameplay, multi-fight, or RNG-continuation checks ran.

## Next decision

Keep survival protected. The next proposed training experiment replaces only the potion decoder: at most 32 joint consumption masks for five occupied active slots, including exact copy-through. Condition a small joint head on visible inventory, the state representation, sampled max-HP delta and sampled HP. This can model dependence without inventing five potion identities. It is a proposal, not an authorized fit or guaranteed improvement; uncertified paths need an explicit future contract.

Obtain a TRAIN-only encoder for honest validation; do not present VALIDATION as unseen for the current TRAIN+VALIDATION checkpoints. Teacher-forced training must be followed by qualification with ancestral sampled conditioning. Put normalized numeric conditioning in the small decoder rather than rerunning the encoder. Retain merged training padding trimming; consider explicit CUDA AMP for newly trained attention components with matching candidate/control precision and recorded metadata. Frozen historical survival stays FP32. Padding/AMP speedups are bounded optimizer-step evidence, not proof of decoder-only speed, model quality, full-epoch speed, or runtime readiness. Do not add an autoregressive relic decoder or train anything in this task.
