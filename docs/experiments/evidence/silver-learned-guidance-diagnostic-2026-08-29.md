# Silver learned-guidance diagnostic (2026-08-29)

## Scope and decision question

This is a bounded offline diagnostic of the learned Silver policy prior and
direct leaf evaluator. It does not train a model, start a simulator, run a
gameplay seed, or alter the frozen 25k-B judgment labels. The question is
whether sufficiently accurate guidance is likely to help Silver, or whether
the tested search integration is low-value or harmful.

The reviewed checkout was not the `main` branch name: it was
`docs/linked-worktree-command-recipe`, at baseline SHA
`60e00eb58f636c7fad11403dc9b01f44733f4280`. The pre-existing untracked
`.worktrees/` directory was preserved. The policy artifacts came from the
`exp/silver-policy-prior-25k` worktree; the leaf summaries came from the
corresponding frozen leaf-evaluator and teacher-comparison worktrees. The
current checkout contains no complete parent `BattleStateWire` snapshots or
complete leaf sibling corpus, so the replay limitations below are substantive.

## Inputs and provenance

The reproducible policy calculation used these existing files:

| Input | Path | SHA-256 |
| --- | --- | --- |
| Canonical policy features | `.worktrees/silver-policy-prior-25k/build/silver_parent_policy_features.jsonl` | `0377aaef862362cdf1fa3925579a73b66381cbd646762a0453b6a939149923bd` |
| A/B relabels and root labels | `.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl` | `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c` |
| Frozen held-out model predictions | `.worktrees/silver-policy-prior-25k/build/silver_policy_native_predictions_attempt3.csv` | `9d3ad9377276ee7c15421e902f70c3623bcd6b78a767cd9e3e8c8361b7c1aecb` |
| Recomputed diagnostic JSON | `build/silver_guidance_alias_20260829.json` | `f502db027c0f92ae653f4cb62fa2e23042df1fbfb8b29141e6a94eba832fbb32` |

Existing evidence manifests used for the non-reconstructed replay results:

| Evidence | Path | SHA-256 |
| --- | --- | --- |
| Policy offline | `.worktrees/silver-policy-prior-25k/docs/experiments/evidence/silver_parent_policy_25k_2026-08-28.json` | `c9d04e538d3372caad56ba8258754116e069e69a7736e7df63e87e9e21358cfe` |
| Policy online methods | `.worktrees/silver-policy-prior-25k/docs/experiments/evidence/silver_policy_online_methods_2026-08-28.json` | `e577e89566bde6d09c2fb7476301a35a194a00e52b26fc5d201bb3defebdec09` |
| M10 leaf evaluator | `.worktrees/silver-leaf-evaluator-10k/docs/experiments/evidence/silver_leaf_evaluator_10k_2026-08-27.json` | `205be1f906aa355fd8e4e15155dd84ab2224a5c588b5db031a687f011bab21ac` |
| M10/M25 comparison | `.worktrees/silver-teacher-model-comparison/docs/experiments/evidence/silver_teacher_model_comparison_2026-08-27.json` | `78beae07a9612088cc79a2a5738b0319fe483dadd268643f39523ca470719e2c` |

The policy evidence package reports 93 independent 25k-B anchor parents, 495
complete feature parents, 370 held-out legal-action rows, and 63 parents with
more than one legal action. The feature schema has 1,788 values: the 1,766
state values followed by the 22-value action block. The independent judgment
reference is always 25k-B; 25k-A is used only as teacher/oracle-side evidence.

## 1. Feature/action alias ceiling

The analyzer hashes the exact serialized canonical feature vector for every
legal action in all 93 valid B anchors, then compares values inside each
collision bucket using the independent 25k-B root Q. Results:

| Quantity | Result |
| --- | ---: |
| Valid B parents / action rows | 93 / 370 |
| All legal-action pairs | 992 |
| Exact feature-collision pairs | 19 (1.915% of all pairs) |
| Collision pairs with different B Q | 17 |
| Actions participating in a collision | 35 / 370 (9.459%) |
| Mean / median / max absolute B-Q spread in collision pairs | 1.378 / 0.552 / 6.145 |
| Parents whose best B action is in a collision bucket | 3 / 93 (3.226%) |
| Uniform-tie top-action error if the collision bucket is used | 50.000% on affected parents; 1.613% over all parents |
| Uniform-tie mean regret from those affected buckets | 2.471 Q units on affected parents; 0.080 over all parents |
| Non-tied B reference pairs on the multi-action slice | 981 |
| Unavoidable pairwise error floor from those aliases | 17/(2x981) = **0.866 pp** |
| Corresponding feature-only pairwise ceiling | **99.134%** |

The 3 best-action collision parents are a useful manual sanity check rather
than an abstract count. For example, in parent `d0b6bef005e2cb36`, two actions
with the same canonical vector have B Q values 92.829 and 98.693; the latter
is the best action. Parent `487b75069c104cd0` has same-vector action values
42.520 and 36.375, and parent `228eb64487cab54d` has 75.847 and 73.029.
These are genuine decision aliases, but they affect only three of 93 parents.

Breakdown by action semantics:

| Kind | Rows | Collision rows | Collision pairs | Non-tied pairs | Mean / max Q spread |
| --- | ---: | ---: | ---: | ---: | ---: |
| Untargeted card | 29 | 4 | 2 | 2 | 3.268 / 6.145 |
| Targeted card | 210 | 24 | 12 | 11 | 1.482 / 5.864 |
| Potion | 25 | 7 | 5 | 4 | 0.373 / 0.854 |
| Card selection | 15 | 0 | 0 | 0 | - |
| End turn | 91 | 0 | 0 | 0 | - |

Thus the representation is information-limited in a semantic sense, but exact
action aliasing is not large enough to explain the policy regression by itself.
The 0.87 pp ceiling is much smaller than the observed online differences.

### Omitted state information

This is a schema comparison, not a causal attribution. The policy/leaf
canonical features summarize piles as card-ID counts and visible aggregates,
whereas the richer Silver wire in `include/sim/search/SilverBridge.h` and the
conversion in `src/sim/search/SilverConversion.cpp` carry more decision state.
Important omissions or compressions include:

- known draw-pile top/bottom order, full-order-observed status, and positional
  knowledge; the feature vector has `dr*` counts rather than the
  `knownBottom`, `unknown`, and `knownTop` wire regions;
- card-instance fields (`uniqueId`, `specialData`, `costForTurn`, retain,
  free-to-play-once, and other instance state), which can distinguish otherwise
  identical card IDs;
- input/card-selection context such as the selection task, option identities,
  pick-zero/any-number flags, `data0`, and selected bits. The action block
  includes selected-card aggregate statistics, but not the full context or
  selected identities;
- exact action identity beyond compact features: the action block has target
  HP and a target-present bit, but not a stable target identity/index; action
  and selection semantics are consequently compressed;
- queued-card metadata, pending direct choices and hidden-intent roll inputs;
  and several status maps, counters, powers, move histories, and other wire
  fields that affect successor behavior.

The omissions justify representation work as a future hypothesis, but the
measured collision ceiling says it should not be the first explanation for the
current online regression.

## 2. Decision-relevant prior metrics

These metrics use only the 63 multi-action B parents and 981 non-tied B action
pairs. Ties in the prediction receive half credit for pairwise agreement;
top-action agreement uses the stable first maximum, and regret is the B-Q loss
from the selected action to the best B action.

| Selector | Pairwise agreement | Top-action agreement | Mean regret | Median regret |
| --- | ---: | ---: | ---: | ---: |
| Current Silver ordering | 66.361% | 34.921% | 4.225 | 0.619 |
| Learned policy model | 68.858% | 47.619% | 3.958 | 0.055 |
| 25k-A teacher Q | 78.084% | 73.016% | 3.437 | 0.000 |

The first two pairwise values exactly reproduce the stored policy evidence
(`.66360856` and `.68858308`) on the same B reference. The teacher value is an
upper-bound-style diagnostic, not an independent evaluation arm. The stored
whole-parent bootstrap for learned model minus current ordering was a +2.468 pp
median pairwise delta, 90% interval [-1.789, +7.421] pp, probability positive
0.822; probability of lower mean regret was only 0.656. This is useful offline
signal, not a strong promotion result.

Max-Q versus max-visit agreement on the same 63 multi-action parents was:

| Replicate | Agreement |
| --- | ---: |
| 25k-A | 63/63 = 100.000% |
| 25k-B | 62/63 = 98.413% |

### Learned-score ties and rank-PUCT conversion

The held-out prediction CSV contains 89 exact tied action-score pairs across
20 of the 63 multi-action parents; 81 of those pairs have different 25k-B Q
values, matching the stored 81-pair prediction-tie count used by the standard
metric. The exploratory implementation at
`241112c40614356b90550f179d8f24c06f720b27` uses a stable descending score sort
and assigns

```text
prior(position) = (n - position) / (n * (n + 1) / 2)
```

so all 89 tied pairs receive unequal priors. The mean absolute prior gap among
tied pairs is 0.06098 and the maximum is 0.21429. Stable sorting means the
remaining ordering is inherited from the current legal-action enumeration.
This is a concrete integration distortion: an exact model tie is not treated
as an equal prior.

## 3. Root-only oracle-prior replay

A faithful root-only replay could not be reconstructed from the stored policy
package. The feature/relabel artifacts contain feature vectors, action
fingerprints, A/B root Q, visits, and child summaries, but not complete parent
`BattleStateWire` snapshots or the isolated search state needed to rerun
ordinary UCT and the exact root expansion at budgets 16/32/64/128/1000. The
existing online experiment is a whole-combat 2×2, not a root-only replay, and
does not contain an oracle-ordering or calibrated-visit-prior arm. No substitute
was invented.

The existing exploratory whole-combat result at base budget 1,000 is still
useful as a mechanism warning, with 32 seeds per arm:

| Arm | Meaning | Wins | Mean floor | Mean end HP | Relative CPU |
| --- | --- | ---: | ---: | ---: | ---: |
| A | Current ordering + ordinary UCT | 20/32 | 47.750 | 30.313 | 1.000 |
| B | Learned ordering + ordinary UCT | 20/32 | 46.594 | 29.656 | 1.491 |
| C | Current ordering + learned rank-PUCT | 17/32 | 45.500 | 22.688 | 1.388 |
| D | Learned ordering + learned rank-PUCT | 15/32 | 44.750 | 19.750 | 1.372 |

Against A, the stored bootstrap contrasts were B: 0 wins, -1.156 floor;
C: -3 wins, -2.250 floor; D: -5 wins, -3.000 floor. The intervals are broad,
but the direction is consistent with rank-PUCT being harmful in this tested
integration. B is neutral in wins and slightly negative in floor while costing
about 49% more CPU. This does not answer whether an oracle prior would help;
it does show that the current rank-prior mechanism is not evidence of such a
benefit.

Calibrated visit-count prior versus rank prior: **not measured**. A/B visit
counts are available in the relabels, but no root state replay is available to
measure the search outcome without changing the evaluation protocol.

## 4. Oracle leaf replay

The complete stored sibling groups and production-path replay inputs requested
for this comparison are not available locally. In particular, there is no
faithful way from the current artifacts to compare current learned leaf,
one/two/four/eight matched SimpleAgent rollouts, and cached 25k-A value through
the production backup/action-selection path. The local smoke corpus is not a
decision-bearing substitute.

The existing independent-B offline and gameplay evidence is:

| Existing evidence | Pairwise | Top leaf/action | Mean regret | Interpretation |
| --- | ---: | ---: | ---: | --- |
| M10 direct leaf model vs independent B sibling values (641 rows) | 57.885% | 30.864% | 3.902 | Modest offline signal |
| M25 direct model vs independent B sibling values (641 rows) | 58.724% | 32.099% | 3.569 | Small offline improvement over M10 |
| M10 direct replacement gameplay arm (8 seeds) | - | 1/8 wins | floor 31.0 | Harmful online result |
| Existing rollout control gameplay arm (8 seeds) | - | 4/8 wins | floor 50.25 | Control, not a sibling replay metric |

The M10-vs-M25 comparison bootstrap gave only 0.747 probability that M25
improved pairwise agreement, although 0.959 probability of lower mean regret.
Neither is an oracle result. The direct leaf arm’s negative gameplay result
therefore rejects the current direct replacement, not the proposition that an
accurate oracle leaf value could help.

## 5. Quiet versus transient slices

The complete requested context slices (stable normal decision, card select,
start-of-turn/post-chance, and transient contexts) cannot be reproduced from
the available leaf summaries. The existing teacher-comparison artifact does
provide a partial rollout-length slice against independent B values:

| Rollout-length slice | Rows | M10 pairwise | M10 mean regret | M25 pairwise | M25 mean regret |
| --- | ---: | ---: | ---: | ---: | ---: |
| Short | 233 | 60.857% | 1.580 | 61.684% | 1.472 |
| Medium | 218 | 59.197% | 3.574 | 57.804% | 3.542 |
| Long | 190 | 59.432% | 3.160 | 62.020% | 2.556 |

Short leaves are materially easier on this descriptive slice, especially in
regret, which is consistent with—but does not prove—the “quiet state”
hypothesis. The slice is by rollout length, not a verified semantic label for
stable normal/card-select/post-chance context, and it does not compare
SimpleAgent rollout counts or cached 25k-A values through production backup.

## Decision table

| Question | Evidence | Conclusion |
| --- | --- | --- |
| Are current features information-limited? | Rich Silver wire contains order, instance, input, queue, status, and pending-choice fields omitted or compressed by the 1,788-value policy vector; exact aliases impose only a 0.866 pp pairwise floor. | **Yes semantically, but no as the measured primary explanation.** |
| Does oracle ordering help? | No faithful root replay. Learned ordering + ordinary UCT was 20/32 wins versus current 20/32, with -1.156 floor and 1.491x CPU. | **Unanswered for oracle; current learned ordering is low-value.** |
| Does oracle PUCT help? | No oracle root replay. Current rank-PUCT was below ordinary UCT: C -3 wins/-2.25 floor and D -5 wins/-3.00 floor versus A. | **Unanswered for oracle; tested rank-PUCT integration is harmful.** |
| Does calibrated visit prior outperform rank prior? | No root snapshots/replay arm; max-Q/max-visit agreement is high but not a search-outcome test. | **Unanswered.** |
| Does oracle leaf evaluation help? | No complete sibling corpus or production-path replay. Current M10 is modest offline and harmful as a direct gameplay replacement. | **Unanswered for oracle; current direct leaf replacement is rejected.** |
| Are quiet leaves materially easier? | Short rollout slice has 60.857% pairwise and 1.580 regret versus 59.197%/3.574 medium; semantic quiet-state labels are unavailable. | **Partial yes, not decision-grade yet.** |

## Synthesis and one recommended direction

The evidence distinguishes two things. The current learned prior has a small
offline improvement over current ordering, but its exact feature aliases do
not impose a large enough ceiling to explain the online result. The currently
tested rank-PUCT integration is the clearest harmful component: it converts
ties into enumeration-dependent unequal priors and performed below ordinary
UCT in the only existing online comparison. The direct learned leaf
replacement is also harmful online, but the missing oracle replay means that
neither result proves that perfect guidance would be useless.

**Recommendation: fix prior integration.** The next experiment should be one
small, root-only replay once parent `BattleStateWire` snapshots are available:
ordinary UCT/current ordering, oracle A-Q ordering with ordinary UCT, oracle
rank prior, and normalized 25k-A visit prior at 16/32/64/128/1000 simulations,
all judged only against frozen 25k-B. This is the shortest experiment that can
separate “accurate guidance has no value” from “the current rank-PUCT plumbing
is harmful.” It requires no new model, no architecture change, and no broad
gameplay benchmark.

## Checks

The analyzer is read-only and uses only Python's standard library. It was
syntax-checked and its output was independently checked against the stored
policy evidence: current-ordering pairwise `0.6636085626911316` and learned
model pairwise `0.6885830784913354` match exactly. No gameplay seeds were run.
The final handoff also ran `git diff --check`.

Exact commands used from the repository root were:

```text
git rev-parse HEAD
python -m py_compile tools\analyze_silver_guidance_alias.py
python tools\analyze_silver_guidance_alias.py .worktrees\silver-policy-prior-25k\build\silver_parent_policy_features.jsonl .worktrees\silver-policy-prior-25k\build\silver_parent_policy_relabel.jsonl .worktrees\silver-policy-prior-25k\build\silver_policy_native_predictions_attempt3.csv --output build\silver_guidance_alias_20260829.json
python -m json.tool build\silver_guidance_alias_20260829.json
git diff --check
```
