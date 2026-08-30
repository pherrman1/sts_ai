# Silver root-only oracle-prior replay (2026-08-29)

## Scope

This is the small follow-up authorized after the learned-guidance alias
diagnostic. It uses exactly 63 valid multi-action parent anchors identified by
the frozen 25k-B labels. It does not train, run campaign gameplay, or modify
the frozen judgment labels. Every oracle ordering/prior is derived from
25k-A; every top-choice and regret result below is judged against 25k-B.

The requested code baseline is
`298f017f38ef3a01333bcdd87586c413f73de4ff`. The task branch was created at
that SHA and then cherry-picked preservation commit `5bcabb8` as a separate
diagnostic-only commit; `5bcabb8` was not used as the experiment baseline.

## Minimal snapshot mechanism

The selected exact-state corpus already contained complete
`BattleStateWire` parent envelopes. Therefore no new simulator labels were
needed. `tools/extract_silver_root_snapshots.py` filters the corpus using the
frozen valid 25k-B parent rows with `root_action_count > 1`, verifies the
complete A/B action surface for every group, and saves one complete parent
wire per group in `silver_root_snapshot_v1` JSONL.

The resulting file has 63 snapshots and SHA-256
`7cfc9371f1d1cfe3e48f7cbda3f6b0e7dc55d417be9d1612303d8e50ab67cc51`.

## Replay arms

Each arm starts a fresh Silver search from the saved root, uses the 25k-A
teacher RNG identity for common random-number comparison, and uses
`reuseCapMode=NONE`, matching the frozen teacher relabel configuration.

- `current_uct`: ordinary UCT and current Silver action order.
- `oracle_order_uct`: stable 25k-A Q-descending root order and ordinary UCT.
- `oracle_rank_puct`: the same oracle order with the existing diagnostic
  triangular rank prior and root PUCT exploration constant 2.5.
- `oracle_visit_puct`: the same oracle order with normalized 25k-A root visit
  counts and root PUCT exploration constant 2.5.

The optional guidance is root-only and default-off. It is diagnostic plumbing,
not a production integration or a claim that rank-PUCT should be shipped.

## Frozen 25k-B results

There are 63 anchors in every cell. “Top choice” means the replay-selected
root action equals the highest-Q action in frozen 25k-B; regret is frozen-B
best Q minus frozen-B Q of the replay-selected action.

| budget | current UCT top / regret | oracle order UCT top / regret | oracle rank-PUCT top / regret | oracle visit-PUCT top / regret |
| ---: | ---: | ---: | ---: | ---: |
| 16 | 49.206% / 3.223794 | **57.143% / 3.026895** | 49.206% / 3.210151 | 53.968% / 3.043238 |
| 32 | 47.619% / 3.632738 | 50.794% / 3.264061 | 52.381% / 3.106321 | **57.143% / 2.992752** |
| 64 | 47.619% / 3.228524 | 46.032% / 3.272103 | 50.794% / 3.189520 | **52.381% / 3.121917** |
| 128 | 42.857% / 3.707522 | 47.619% / 3.754310 | 50.794% / 3.190456 | **55.556% / 3.006543** |
| 1000 | 60.317% / 3.770995 | **63.492% / 3.551682** | 52.381% / 3.159325 | 60.317% / **2.279731** |

The primary A/B comparison is current UCT versus oracle Q ordering. Oracle
ordering gains +7.94, +3.17, -1.59, +4.76, and +3.17 percentage points of
top-choice agreement at 16/32/64/128/1000, respectively. Regret changes by
-0.196899, -0.368677, +0.043578, +0.046787, and -0.219313 Q units. Thus
perfect ordering is useful at some low budgets, but the effect is modest and
not consistently monotone.

Rank-PUCT does not preserve the ordering benefit reliably: relative to oracle
order UCT its top-choice result is -7.94 pp at 16 and -11.11 pp at 1000,
although it has lower mean regret in the displayed run. The normalized visit
prior is more consistent: it has lower mean regret than both rank-PUCT and
current UCT at every budget, and its top-choice agreement is higher than
current UCT at 16/32/64/128 (equal at 1000). This is evidence for a prior
integration effect, not a justification to change production PUCT yet.

## Decision table

| Question | Evidence | Conclusion |
| --- | --- | --- |
| Are current features information-limited? | The preserved alias report finds 19 exact feature collisions, 17 non-tied B-Q pairs, a 0.866 pp unavoidable pairwise floor, and a 99.134% feature-only ceiling. | Yes semantically, but the measured alias ceiling is too small to explain the online regression by itself. |
| Does oracle ordering help? | It improves primary B top-choice agreement at 16, 32, 128, and 1000, but not 64; the largest gain is +7.94 pp at 16. | Yes, modestly and inconsistently. |
| Does oracle rank-PUCT help? | It does not reliably retain oracle-order performance and is 11.11 pp below oracle-order UCT at 1000 on top choice. | Not as a robust integration. |
| Does calibrated visit prior outperform rank prior? | Visit-PUCT has lower mean B regret at all five budgets and better top choice than rank-PUCT at 16, 64, 128, and 1000. | Yes in this bounded replay; this is a follow-up hypothesis, not a production change. |
| Does oracle leaf evaluation help? | Not tested by this root-only follow-up. | Open; no causal claim. |
| Are quiet leaves materially easier? | Not tested by this root-only follow-up. | Open; no causal claim. |

## Recommendation

Recommend exactly one next direction: **fix prior integration**. The A/B arm
shows that accurate root ordering has some low-budget value, so the search
integration is not wholly low-value. The rank-PUCT arm shows that the current
prior conversion can erase that value, while normalized A visits are a more
promising diagnostic prior. Keep this as a small offline integration
experiment; do not start a gameplay gate or a broad PUCT redesign from these
63 roots alone.

## Provenance and commands

Frozen inputs:

| Artifact | SHA-256 |
| --- | --- |
| selected exact-state corpus | `bdac7173f789cd1439438eca5079a167e15de7f9aaf8c4fc242635a38790a2c7` |
| 25k-A/B relabels | `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c` |
| canonical policy features | `0377aaef862362cdf1fa3925579a73b66381cbd646762a0453b6a939149923bd` |
| frozen model predictions used by the reproduced alias check | `9d3ad9377276ee7c15421e902f70c3623bcd6b78a767cd9e3e8c8361b7c1aecb` |

Generated replay output SHA-256:
`4bbb0e54c104ef90b032fdda221338dc09e31ff04405f4baf8411743c93827d1`.

Exact commands, from the clean task worktree:

```text
git fetch origin main
git rev-parse origin/main
git rev-parse --verify '298f017f38ef3a01333bcdd87586c413f73de4ff^{commit}'
git worktree add -b exp/silver-root-oracle-replay .worktrees/silver-root-oracle-replay 298f017f38ef3a01333bcdd87586c413f73de4ff
git cherry-pick 5bcabb8
python tools/agent/gcp_benchmark.py copy-from pilot-artifacts/b444517/selected_corpus.jsonl build/pilot-selected_corpus.jsonl
python tools/extract_silver_root_snapshots.py build/pilot-selected_corpus.jsonl C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_relabel.jsonl build/silver_root_snapshots_63.jsonl
wsl -e bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-root-oracle-replay && cmake -S . -B build/root-oracle-cmake -DCMAKE_BUILD_TYPE=Release && cmake --build build/root-oracle-cmake --target silver-root-oracle-replay silver-bridge-test -j 4"
python tools/analyze_silver_guidance_alias.py C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_features.jsonl C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_relabel.jsonl C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_policy_native_predictions_attempt3.csv --output build/silver_guidance_alias_reproduced.json
wsl -e bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-root-oracle-replay && ./build/root-oracle-cmake/silver_bridge_test"
wsl -e bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-root-oracle-replay && ./build/root-oracle-cmake/silver_root_oracle_replay build/silver_root_snapshots_63.jsonl /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl build/silver_root_oracle_replay.jsonl"
python tools/analyze_silver_root_oracle_replay.py build/silver_root_oracle_replay.jsonl
git diff --check
```

The generated replay binary SHA-256 is
`a44e3cacb42ca479dfff41a82251a58b2262df98b459c2ec3486c771a0d3a47d`; the
focused bridge-test binary SHA-256 is
`0493e42ca50795c54f3ccd4c736c2183c0d5324ec4a9928c74e1b4eba54d6475`.
