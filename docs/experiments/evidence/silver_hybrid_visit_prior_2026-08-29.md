# Silver learned-prior ranking versus mass-shape replay (2026-08-29)

## Scope and result

This bounded follow-up uses the frozen raw-count learned prior and frozen
25k-A visit shares to separate action ranking from prior-mass shape. No model
was trained, no feature or search setting changed, and 25k-B was used only for
replay judgment.

The result points to **learned prior-mass/calibration as the dominant
bottleneck**, with learned action ranking remaining a secondary limitation for
exact top-choice selection:

- learned order + oracle mass reaches `3.500677` mean B regret versus oracle's
  `3.505948`, and improves raw learned regret by `-0.538166 Q`;
- oracle order + learned mass reaches `4.113176`, worse than current UCT
  (`4.051736`) and raw learned PUCT (`4.038843`);
- learned order + oracle mass still trails oracle top-choice agreement by
  `5.95 pp`, so ranking is not perfect;
- the line remains open for review but unresolved. No next model, budget,
  gameplay run, temperature, `c_puct`, or architecture change is authorized.

## Frozen inputs and construction

| Artifact | Path | SHA-256 |
| --- | --- | --- |
| raw learned predictions | `build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_predictions.jsonl` | `f21d1c0e1e1b62434dab6582fd2b53efbba8c8895bd0d6d29d566195ec8112c7` |
| frozen A/B relabels | `.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl` | `abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c` |
| learned-order/oracle-mass priors | `build/silver_hybrid_visit_priors_20260829/learned_order_oracle_mass.jsonl` | `8d3f45d6c63ea0684abbc91c5fdfdd85b91a02abc10ec3a5a3b71dc8810a2c8e` |
| oracle-order/learned-mass priors | `build/silver_hybrid_visit_priors_20260829/oracle_order_learned_mass.jsonl` | `3dece285ae058d46b9c8f5fd50701900429c17eb4f81f9d3cd042ef242d634bc` |
| construction report | `build/silver_hybrid_visit_priors_20260829/report.json` | `b396375ba5d7f86918b852bce80dab6d4a618d1af13c11d062987fd74274bf2e` |
| replay source commit | `581b68bb31a8b62bb94e88c5b783e042880746b1` | — |
| replay executable | `build/root-oracle-cmake/silver_root_oracle_replay` | `d8d08392343ab442ec093e5fa07b64b326755560ff374dfba61bbce9c1a18006` |
| learned-order/oracle-mass replay | `build/silver_hybrid_learned_order_oracle_mass_replay32_r4.jsonl` | `25c5d495bd5b8bda0e0d33f241ad622219f198ff3a5b910a9848cc43380f172b4` |
| oracle-order/learned-mass replay | `build/silver_hybrid_oracle_order_learned_mass_replay32_r4.jsonl` | `3570b311317efe14f65e1ed2b10e5dd372bbe8238e074f08407df34fd1709b65` |
| combined analysis | `build/silver_hybrid_visit_replay32_r4.json` | `e63366bf2df8535d78c485479920cc04a083dc62d44e5d4872a7ff234c63fdae` |

Both synthetic files contain exactly 63 normalized sibling distributions.
Construction used no B labels:

1. `learned_order_oracle_mass_puct`: sort by raw learned score, then assign
   descending exact A visit probabilities by learned rank;
2. `oracle_order_learned_mass_puct`: sort by descending exact A visit share,
   then assign descending learned probability magnitudes by oracle rank.

## Replay conditions

Existing current UCT, oracle visit-PUCT, and raw learned visit-PUCT rows were
reused because the new executable branch only adds hybrid arm names and the
search path/settings for the existing arms are unchanged. Each hybrid was run
over the same 63 roots at 32 simulations with four replicate seeds per root.
All arms share the same saved wire state and deterministic seed per
root/replicate, but treatment-dependent choices can consume different later
RNG draws. Replicates were averaged within root before bootstrap.

## Root-level results

| Arm | Mean B-best probability | Mean B regret | Roots with action change | Mean within-root regret SD | Median within-root regret range | Max range |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Current UCT | 41.2698% | 4.051736 | 45/63 | 2.598646 | 1.118884 | 33.789093 |
| Oracle normalized A-visit PUCT | 51.1905% | 3.505948 | 41/63 | 2.601467 | 0.808100 | 35.195135 |
| Raw learned normalized visit-PUCT | 43.2540% | 4.038843 | 45/63 | 2.712157 | 2.202886 | 35.195135 |
| Learned order + oracle mass | 45.2381% | 3.500677 | 40/63 | 2.261947 | 0.789790 | 33.789093 |
| Oracle order + learned mass | 43.2540% | 4.113176 | 43/63 | 2.973724 | 1.256212 | 45.940390 |

Paired root bootstrap used 10,000 resamples of the 63 root-level differences
with seed `20260830`.

| Treatment vs control | B-best delta | 95% CI | Mean regret delta | 95% CI | Improved / worsened / tied |
| --- | ---: | ---: | ---: | ---: | ---: |
| Learned order + oracle mass vs current | +3.9683 pp | [-2.7778, +10.3175] pp | -0.551058 | [-1.032028, -0.131197] | 21 / 13 / 29 |
| Learned order + oracle mass vs raw learned | +1.9841 pp | [-4.3651, +7.9365] pp | -0.538166 | [-1.040641, -0.112970] | 18 / 6 / 39 |
| Learned order + oracle mass vs oracle | -5.9524 pp | [-11.9048, -0.7937] pp | -0.005270 | [-0.466855, +0.394914] | 7 / 12 / 44 |
| Oracle order + learned mass vs current | +1.9841 pp | [-3.9683, +8.3333] pp | +0.061440 | [-0.515609, +0.696255] | 17 / 15 / 31 |
| Oracle order + learned mass vs raw learned | 0.0000 pp | [-1.1905, +1.1905] pp | +0.074333 | [-0.225740, +0.528904] | 7 / 2 / 54 |
| Oracle order + learned mass vs oracle | -7.9365 pp | [-12.3016, -4.3651] pp | +0.607228 | [+0.162659, +1.175803] | 2 / 17 / 44 |

## Outlier check and decision

For learned order + oracle mass versus current, the largest improvement was
`-7.260745 Q` at `d9998e96ca26a122` and the largest harm was `+3.503125 Q` at
`d0b6bef005e2cb36`. Removing either leaves a negative mean delta (`-0.442838`
or `-0.616448 Q`), so this hybrid's regret recovery is not one-root driven.

For oracle order + learned mass versus current, mean regret was `+0.061440 Q`.
Removing its largest harm (`+11.060127 Q` at `228eb64487cab54d`) gives
`-0.115958 Q`, while removing its largest improvement gives `+0.179540 Q`.
This arm is not a robust positive result.

| Question | Evidence | Conclusion |
| --- | --- | --- |
| Does learned order plus oracle mass succeed? | Regret `3.500677`, essentially oracle's `3.505948`, with `-0.551058 Q` vs current and CI excluding zero. | Yes for regret; mass shape is sufficient to recover nearly all oracle regret gain when paired with learned order. Top-choice remains 5.95 pp below oracle. |
| Does oracle order plus learned mass succeed? | Regret `4.113176`, `+0.061440 Q` vs current with CI including zero, and `+0.607228 Q` vs oracle with CI excluding zero. | No; learned mass shape blocks the oracle ranking benefit. |
| Which bottleneck dominates? | Oracle mass nearly recovers oracle regret, while oracle rank does not rescue learned mass. | Mass/calibration is dominant; ranking remains a secondary top-choice limitation. |
| Should another model be trained now? | Hybrid evidence isolates the failure, but learned-vs-current top/regret effects remain uncertain. | No. Keep the line open for review, but do not expand yet. |

## Exact commands and checks

```text
python -m py_compile tools/build_silver_hybrid_visit_priors.py tools/analyze_silver_hybrid_visit_replay.py
python tools/build_silver_hybrid_visit_priors.py build/silver_parent_visit_prior_raw_20260829/silver_parent_visit_prior_predictions.jsonl C:\Users\pherrman\projects\sts_ai\.worktrees\silver-policy-prior-25k\build\silver_parent_policy_relabel.jsonl build/silver_hybrid_visit_priors_20260829
wsl -e bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-root-oracle-replay && cmake --build build/root-oracle-cmake --target silver-root-oracle-replay -j 4"
wsl -e bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-root-oracle-replay && ./build/root-oracle-cmake/silver_root_oracle_replay build/silver_root_snapshots_63.jsonl /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl build/silver_hybrid_learned_order_oracle_mass_replay32_r4.jsonl 32 4 learned_order_oracle_mass_puct build/silver_hybrid_visit_priors_20260829/learned_order_oracle_mass.jsonl"
wsl -e bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-root-oracle-replay && ./build/root-oracle-cmake/silver_root_oracle_replay build/silver_root_snapshots_63.jsonl /mnt/c/Users/pherrman/projects/sts_ai/.worktrees/silver-policy-prior-25k/build/silver_parent_policy_relabel.jsonl build/silver_hybrid_oracle_order_learned_mass_replay32_r4.jsonl 32 4 oracle_order_learned_mass_puct build/silver_hybrid_visit_priors_20260829/oracle_order_learned_mass.jsonl"
python tools/analyze_silver_hybrid_visit_replay.py build/silver_raw_visit_replay32_r4.jsonl build/silver_hybrid_learned_order_oracle_mass_replay32_r4.jsonl build/silver_hybrid_oracle_order_learned_mass_replay32_r4.jsonl --json-output build/silver_hybrid_visit_replay32_r4.json
python -m json.tool build/silver_hybrid_visit_replay32_r4.json > $null
git diff --check
```

Focused syntax, construction, replay, JSON, and diff checks passed. No model
training, gameplay, budget expansion, PUCT tuning, temperature, or feature
change was performed.
