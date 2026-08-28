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

The decision-bearing result, exact frozen/GCP SHA, model hash, costs, metrics,
bootstrap, diagnostics, and final verdict remain pending the draft-PR review,
authoritative CI, and frozen-SHA GCP run.
