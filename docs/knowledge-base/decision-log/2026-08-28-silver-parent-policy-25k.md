# Silver 25k parent-action policy model

Date: 2026-08-28

## Predeclared decision

Test whether the existing canonical combat state/action representation can
rank legal Silver actions from corrected 25k-A parent Q labels. Independent
25k-B parent rows are identified before modeling and reserved as test-only.
Training uses centered corrected Q, one fixed XGBoost squared-error recipe, a
deterministic parent-group train/validation split, and validation early
stopping. No visit target, temperature, sweep, gameplay, new corpus, or new
teacher search is permitted.

The primary baseline is the executed order produced by pinned Silver
`BattleSearcher::enumerateActionsForNode`. The registered gate requires at
least three percentage points of pairwise concordance improvement, at least
90% whole-parent bootstrap probability of positive pairwise improvement, at
least 90% probability of lower mean regret, and no more than two percentage
points worse top-action agreement. The only verdicts are
`POLICY_MODEL_OFFLINE_PROMISING`, `POLICY_MODEL_OFFLINE_REJECTED`, and
`POLICY_MODEL_OFFLINE_UNRESOLVED`.

## Immutable inputs verified before modeling

- `relabel.jsonl` SHA-256:
  `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c`.
- `selected_corpus.jsonl` SHA-256:
  `bdac7173f789cd1439438eca5079a167e15de7f9aaf8c4fc242635a38790a2c7`.
- `manifest.json` SHA-256:
  `db67ff9df6a1578a46e4e09038b5f2548772fc9c70fc54a00b1576f659883cd7`.
- Coverage: 500 parent rows per A budget; 496 valid 25k-A parents; 93
  independent 25k-B anchors; all 93 anchors valid. The four invalid A parents
  have the preserved empty failure reason and zero simulations.

The definitive reviewed and CI-passed experiment SHA was
`85599a3d2c6e55f32236ea59c814bdd1250d73bb`. On 93 untouched 25k-B parents,
the model improved exact-order pairwise concordance by 2.497pp and top-action
agreement by 8.602pp, while reducing mean regret by 0.181. However, the
5,000-parent bootstrap probabilities were only 82.20% for positive pairwise
improvement and 65.58% for lower mean regret. Both missed the registered 90%
bar, and pairwise point improvement missed 3pp.

Final verdict: **`POLICY_MODEL_OFFLINE_REJECTED`**. No compact native export,
native model parity, online prior integration, PUCT, or gameplay run is
authorized. Exact metrics, hashes, costs, and descriptive subgroups are in
`docs/experiments/evidence/silver_parent_policy_25k_2026-08-28.json`.

The first frozen feature attempt emitted no dataset and failed closed on a
WARCRY parent because the pre-existing wire-to-live feature adapter did not
restore `CardSelectInfo`. The same-session implementation correction restores
the complete wire card-select/current-queue fields and adds focused parity
coverage. No modeling or 25k-B metric was produced by the failed attempt.

The corrected frozen attempt then found a pinned-Silver/current-live legality
incompatibility (Gambler's Brew with an empty hand). The feature producer was
corrected to exclude an entire incompatible parent atomically and record a
stable exclusion category; it still never emits a partial action set, and
schema, duplicate teacher, missing corpus, and feature-width failures remain
fatal.
