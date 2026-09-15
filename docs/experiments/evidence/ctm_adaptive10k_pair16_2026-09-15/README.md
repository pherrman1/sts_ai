# CTM-scaled 10k versus flat 10k, paired 16 seeds

## Design

Implementation baseline is `608bb810c44173fb8c0036df6e89c71da4d778e3`;
the frozen measured implementation is
`a577fe0c6b7b81fef23e8d960d152766e84f80ae`. The treatment loads the tracked
qualified V2 combat-transition artifact
`selfplay/models/combat_transition_near_full_except_smoke_v2.native` (SHA256
`22c855e0667a58a73835505672b0ae6d03f12e9fb8d64f08893810199246e94e`).

The deterministic expectation path marginalizes the CTM survival, max-HP and
signed-HP distributions to obtain `P(death)` and
`E[postHp/postMaxHp | victory]`. It applies the historical adaptive formula
`0.5 + P(death) + 1 - E[HP fraction]`, clamped to 0.4x..2.0x, to a 10,000
simulation base. It draws no samples and consumes no gameplay RNG. A fight
outside the qualified CTM support retains the 10,000 base.

The fixed exploratory comparison used paired seeds 48--63, A0 Ironclad,
project-fair RNG, keys off, native OOC, Silver exact root budgets, allocated
reuse with experimental 131,072 cap/lazy GC, Silver adaptive off, learned leaf
off and OOC MCTS off. Four workers ran the arms sequentially. No preserved
artifact had this CTM treatment and matched baseline; prior C_psi evidence used
a different model, while prior flat-10k Silver evidence used seeds 16--47.
The arms, seeds and reporting rule were fixed before collection. No tuning,
extra arm or extra seed followed the result.

## Results

| Arm | Wins | Mean floor | Mean final HP | Mean sec/run | Added simulations | Peak process RSS |
|---|---:|---:|---:|---:|---:|---:|
| Flat 10k | 10/16 | 46.1875 | 33.9375 | 28.4177 | 71,840,000 | 2.424 GiB |
| CTM-scaled 10k | 11/16 | 46.2500 | 40.5625 | 19.6017 | 49,331,273 | 2.225 GiB |

The treatment saves 31.33% of added simulations and 31.02% of observed mean
run time. The outcome difference is +6.25 percentage points: both win 10,
both lose 5, flat-only 0, CTM-only 1 (seed 49). With only one discordant pair,
the exact two-sided paired test is `p=1.0`; this does not establish better play.
The final-HP difference mixes changed trajectories and survivor composition.

Across 383 treatment fights, configured budgets range 5,002--13,609, with mean
6,317.49 and median 5,703. There are 365 fights below 10k, 16 above and two
exactly 10k. Because the diagnostic records only the resulting budget, the two
exact-10k cases cannot be separated after the fact into exact model outputs
versus qualified-support fallback. Budgets differed from flat 10k in 381/383
fights, directly confirming that the CTM path controlled allocation. Neither
arm had a retained-cap fallback; maximum allocated nodes after search were
126,966 flat and 111,486 adaptive.

All 16 seeds occur once per arm. All 7,184 flat and 7,294 treatment decision
records have the expected exact-budget, allocated-131072 configuration. All
380/383 per-combat telemetry records have zero conversion, semantic,
transaction and knowledge failures. Both producer exits are zero. External
`time -v` RSS covers each complete four-worker process, not one searcher.

## Interpretation

This small gate supports CTM scaling as a promising compute-efficiency option:
it retained the observed outcome count while using about one-third less search.
It does not qualify the adaptive path as a production default or establish a
win-rate improvement. A larger prospective paired gate would be needed before
promotion. The current implementation therefore remains opt-in; "10k" here is
the caller's base around which the treatment scales.

Run `python3 analyze.py` in this directory to validate the raw records and
regenerate `summary.json` and `manifest.sha256`. `provenance.json` contains the
clean implementation SHA, binary/model hashes, explicit environment, guarded
commands, inventory and fixed decision rule. Compressed producer logs and
decision diagnostics, result CSVs, timing files, paired report and hashes are
preserved here.

Knowledge impact: experimental CTM adaptive-budget integration and exploratory
gameplay/compute evidence; no default, teacher, model or support qualification.
