# Silver normalized-visit prior confirmation at 32 simulations (2026-08-29)

## Scope and frozen implementation

This is the smallest confirmatory replay requested after the 1,260-row
root-oracle matrix. It runs only budget 32 and only two arms over the same 63
frozen multi-action roots:

1. current ordering + ordinary UCT;
2. normalized frozen 25k-A visit prior + root PUCT.

Each root/arm was searched with four replicate seeds. The same four-seed set
was used for both arms of each root. The frozen 25k-B labels remain the only
judgment source. Replicates were aggregated within root before any statistical
comparison; they were not treated as independent samples.

The final executable was frozen before this replay at source commit
`5a26b07804e28484ca348610f9026554a019c664`, with binary SHA-256
`e047390d7f0fe1ddb31642276a7f636f4a85714b5e86b75a0fe526e881a19c4e`.
The preceding replay implementation and analysis commits remain in the same
branch history. No new prior formula, gameplay run, model training, or broad
refactor was performed.

## Root-level result

For each root, the four replicate outcomes were first reduced to:

- probability of selecting the frozen-B best action;
- mean frozen-B regret.

The reported aggregate is the mean of those 63 root-level quantities. Paired
root bootstrap resampled the 63 roots 10,000 times using
`random.Random(20260830)` and the inclusive percentile rule.

| Arm | Mean probability of selecting frozen-B best | Mean frozen-B regret | Roots with any selected-action change | Mean within-root regret SD | Mean within-root regret range | Median within-root regret range | Maximum within-root regret range |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Current UCT | 41.269841% | 4.051736 | 45 / 63 | 2.598646 | 6.080980 | 1.118884 | 33.789093 |
| Normalized A-visit PUCT | 51.190476% | 3.505948 | 41 / 63 | 2.601467 | 6.141508 | 0.808100 | 35.195135 |

Treatment-minus-control differences:

| Quantity | Difference | Paired root-bootstrap 95% CI |
| --- | ---: | ---: |
| Mean B-best selection probability | **+9.920635 pp** | **[+3.174603, +17.063492] pp** |
| Mean frozen-B regret | **-0.545788 Q** | **[-1.004520, -0.116493] Q** |

At the root level, normalized visit-PUCT had lower mean regret on 24 roots,
higher mean regret on 9 roots, and exactly tied mean regret on 30 roots.

The largest root-level regret changes were:

- best treatment improvement: `-7.260745 Q` at root `d9998e96ca26a122`;
- largest treatment harm: `+5.920758 Q` at root `f47c1d6977c181fd`.

The signed sum of root-level regret deltas was `-34.384644 Q`. Removing the
largest negative root leaves a mean delta of `-0.437482 Q`; removing the
largest positive root leaves `-0.650087 Q`. The sign therefore does not
depend on either single extreme, although the within-root ranges show that
search stochasticity remains substantial.

## Replicate stability

Replicate stability is descriptive only; the four replicates for a root are
not independent statistical units.

| Arm | Roots with stable selected action | 2 unique actions | 3 unique actions | 4 unique actions | Mean unique actions/root |
| --- | ---: | ---: | ---: | ---: | ---: |
| Current UCT | 18 | 30 | 12 | 3 | 2.000000 |
| Normalized A-visit PUCT | 22 | 25 | 13 | 3 | 1.952381 |

Within-root regret dispersion across the four seeds:

| Arm | Mean SD | Median SD | Maximum SD | Mean range | Median range | Maximum range |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Current UCT | 2.598646 | 0.526489 | 13.794345 | 6.080980 | 1.118884 | 33.789093 |
| Normalized A-visit PUCT | 2.601467 | 0.394895 | 15.239940 | 6.141508 | 0.808100 | 35.195135 |

The treatment changes selected action on 41 roots versus 45 for current UCT.
Its median within-root regret range is smaller, but its maximum range is
slightly larger. This does not show that the treatment is variance-free; it
shows that the root-averaged advantage survives four seeds without an obvious
increase in aggregate instability.

## RNG conditions

For each root, replicate `r` used the same deterministic seed in both arms.
Replicate 0 is the original frozen 25k-A teacher seed. Replicates 1–3 are
deterministically derived from that A seed. The arms therefore share the same
replicate seed set and initial wire state.

They still do not share identical realized search/chance trajectories after
the first treatment-dependent choice. Different root priors can choose
different edges and consume different subsequent RNG draws. Thus this is a
root×replicate common-seed comparison, not a perfectly matched random-number
stream experiment. The requested statistical unit remains the root after
replicate aggregation.

## Decision

The normalized visit-prior result survives the requested four-seed
confirmatory replay:

- the root-level mean regret effect remains clearly negative;
- its paired bootstrap 95% CI excludes zero;
- the top-choice probability effect is positive with a CI excluding zero;
- the effect remains negative after removing either largest regret outlier;
- 24 roots improve versus 9 worsen after replicate averaging;
- replicate instability is substantial but not materially worse in the
  treatment’s median dispersion.

Therefore authorize one small integration-focused follow-up for the
normalized visit-prior path. Keep it bounded to the existing root-replay
setting and 32 simulations first; do not expand to another budget unless that
follow-up poses a specific unanswered integration question. Do not run
gameplay, train a model, tune PUCT, or introduce another prior formula yet.

## Provenance and exact command

Frozen inputs were unchanged from the prior replay:

- 63-root snapshot JSONL: `7cfc9371f1d1cfe3e48f7cbda3f6b0e7dc55d417be9d1612303d8e50ab67cc51`;
- 25k-A/B relabel JSONL: `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c`;
- final confirmatory replay executable source commit:
  `5a26b07804e28484ca348610f9026554a019c664`;
- replay executable SHA-256:
  `e047390d7f0fe1ddb31642276a7f636f4a85714b5e86b75a0fe526e881a19c4e`;
- confirmatory replay JSONL SHA-256:
  `c07e754d01b2bfd7d091e7e5ad351d1e6ed8f1e47593a6faf6c1497345342c6a`;
- root-aggregated analysis JSON SHA-256:
  `d8486472de898374ea9d0c4c319a369b2a800c0d7d2f231e65c4f586a33a2823`.

The final replay command was:

```text
wsl -e bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-root-oracle-replay && ./build/root-oracle-cmake/silver_root_oracle_replay build/silver_root_snapshots_63.jsonl /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl build/silver_root_oracle_confirm32_r4.jsonl 32 4 current_uct,oracle_visit_puct"
```

The aggregation command was:

```text
python tools/analyze_silver_root_confirm.py build/silver_root_oracle_confirm32_r4.jsonl --json-output build/silver_root_oracle_confirm32_r4.json
```
