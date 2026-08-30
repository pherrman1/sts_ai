# Silver root-only exploration control

Date: 2026-08-29

## Decision

Record `ROOT_EXPLORATION_REDUCTION_REJECTED`. Keep ordinary Silver UCT as
the default and do not run a fresh gameplay confirmation or restore
Sequential-Halving/root-pruning machinery from this result.

## Evidence and reasoning

The narrow implementation adds one default-off optional coefficient to the
Silver bridge. `BattleSearcher::evaluateEdge` consults it only when the
parent is the current search root and the edge is deterministic. Internal
deterministic c, chance c/widening, unvisited-edge handling, root-edge
storage, final action selection, and rerooting are unchanged. Focused bridge
and integration tests pass, including explicit c=25 equivalence and malformed,
negative, and nonfinite live settings.

The declared candidates were 18.5, 12.5, and 9.9 against unset c=25 control.
The primary replay used 63 multi-action retained 25k-A/B anchors at 64, 128,
256, and 1000 simulations; all 93 anchors were replayed as the integrity
population. The 25k-A selection rule rejected every lower-root candidate
because each introduced new >=3-regret selections at both 128 and 256.
Replay CPU ratios at 1000 were within 1.05x, but the catastrophe rule is an
independent rejection condition. The independent 25k-B gate was therefore not
examined for selection and no candidate was frozen.

This preserves the prior Sequential-Halving and progressive-unpruning
negative results. The historical 931000–931063 gameplay smoke remains
exploratory and is not reused as confirmation evidence.

## Artifacts

- [Evidence report](../../experiments/evidence/silver-root-exploration-sweep-2026-08-29.json)
- `apps/silver_root_exploration_replay.cpp`
- `tools/analyze_silver_root_exploration_replay.py`
- Ledger-06 §193

Baseline full `origin/main` SHA: `034830df6510f1ab37ad4f053c07333fca0970c7`.
