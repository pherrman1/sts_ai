# 2026-08-15 — Retire dormant combat trainers

Date: 2026-08-15
Session/task: Evidence-led trainer-retirement cleanup

## Decision

Delete `tools/train_deepsets_mcts.py` and `train_value_combat_mlp.py`. Retain
the `combat_deepsets_v1` and `combat_mlp_sparse_v1` runtime loaders and their
other tracked producers.

## Rationale

Neither executable had a tracked self-play, tools, GCP, CI, or maintained
current-research caller; neither produced a tracked deployed artifact. The
DeepSets MCTS-leaf experiment is closed, and its script dereferenced `df_traj`
after deleting it. The flat MLP script selected checkpoints against a target
that omitted the HP term used for training. Repairing dormant trainers would
add unsupported maintenance surface.

## Alternatives considered

- Retain or repair either trainer — rejected because no supported path requires
  either executable and Git/history preserve their research evidence.
- Remove runtime model support — rejected as out of scope: the loaders and
  alternate `combat_deepsets_v1` / `combat_mlp_sparse_v1` producers remain.

## Evidence

- `selfplay/`, `tools/`, `.github/`, maintained knowledge-base pages, and
  tracked artifacts contain no caller or deployed-artifact dependency for
  either retired script.
- `docs/knowledge-base/evaluation/current-research.md` marks the initial
  DeepSets combat VNet line closed; the historical decision and ledger remain.
- `train_value_combat_nn.py` still writes `combat_mlp_sparse_v1`.
- `src/sim/search/CombatValueNet.cpp::CombatValueNet::load` retains the
  `combat_mlp_sparse_v1` and `combat_deepsets_v1` parsers unchanged.

## Status and follow-up

- **Implemented.** No runtime model, artifact, gameplay, search, or active
  training-pipeline behavior changed.