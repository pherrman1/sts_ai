# OOC root checkpoint diagnostic

## Scope

This is a profiling/decision diagnostic, not a gameplay treatment. The live
policy remained the requested 2,048-simulation visit-selected OOC MCTS policy.
The checkpoint implementation runs a discarded full-budget shadow search from
the same root, path history, model artifacts and derived search seed. It records
root action IDs, priors, visits and Q after 128, 256, 512, 1024 and 2048 shadow
simulations. It never changes the live action, RNG stream or fallback path.

Baseline was current `main` at `bdaf01743e4cab26d8b3b43db6754b5ba8a32303`.
Diagnostic implementation was frozen and tested at `b3a1860ca527382e68ac39167603090fd23fad54`.
The run used historical seeds `12002032` through `12002039`, once each:
Ironclad A0, project-fair, keys off, Act-3 stop, exact 10,000-Silver search,
OMP_NUM_THREADS=1, OOC 2,048, cPuct 1.5, widening 2/0.5, depth 32, policy
prior, native leaf, zero leaf combats, V4 continuation policy, early stop on.
Every seed producer was routed through `tools/seed_guard.sh`.

The executable and model hashes are in `artifact.sha256`; raw output is in
`checkpoints.jsonl`, `mcts.csv`, `runs.csv`, `run.log`, and `time`. The frozen
offline analyzer is `tools/analyze_ooc_root_checkpoints.py`.

## Accounting

The run produced eight unique seed rows and 1,134 unique `(seed, decisionIndex)`
roots. There were 1,133 completed shadow roots and one expected
`smoke_bomb` shadow abort. Completed roots have all five checkpoints. There
were zero completed-root live-action versus final-2048 action mismatches. The
one aborted shadow root is excluded from agreement and rule denominators; it is
retained as support evidence, not silently treated as a settled root.

Results below use all 1,133 completed roots. The multi-action subset contains
898 roots; singleton roots are reported separately by the analyzer and do not
drive the conclusions.

## Checkpoint agreement

Agreement means the visit/Q/ascending-ID leader at the checkpoint equals the
final 2,048 leader.

| Checkpoint | All completed roots | Multi-action roots |
|---:|---:|---:|
| 128 | 92.41% (1,047/1,133) | 90.42% (812/898) |
| 256 | 93.65% (1,062/1,133) | 91.98% (826/898) |
| 512 | 95.41% (1,081/1,133) | 94.21% (846/898) |
| 1024 | 97.18% (1,101/1,133) | 96.44% (866/898) |
| 2048 | 100.00% | 100.00% |

The top-two visit gap is useful and strongly monotone. For all completed roots:

| Visit gap at checkpoint | 128 | 256 | 512 | 1024 |
|---:|---:|---:|---:|---:|
| 0–5% | 54.0% (27/50) | 58.3% (28/48) | 71.2% (37/52) | 68.8% (33/48) |
| 5–10% | 70.5% (31/44) | 77.5% (31/40) | 76.9% (30/39) | 89.2% (33/37) |
| 10–20% | 81.0% (64/79) | 79.3% (69/87) | 85.9% (67/78) | 91.2% (73/80) |
| >20% | 96.4% (925/960) | 97.4% (933/958) | 98.2% (947/964) | 99.4% (962/968) |

Leader stability is useful but not sufficient by itself. Among roots with an
unchanged leader at every observed checkpoint through the stated budget,
agreement is 93.90% at 256, 95.70% at 512 and 97.30% at 1024. The corresponding
unstable-root agreement is 78.95%, 87.50% and 94.83%. Stability is therefore a
good risk discriminator, not proof that the leader cannot change between
checkpoints.

## Hypothetical rules

These are offline counterfactual simulation counts only. They do not rerun
gameplay with reduced budgets and do not authorize deployment.

| Rule | Agreement | Nominal simulations saved vs 2048 | Extra saved vs existing live early stop |
|---|---:|---:|---:|
| Fixed 512 | 95.41% | 75.00% | 60.73% |
| 512 → 2048 if gap < 5% | 96.73% | 71.56% | 54.62% |
| 512 → 2048 if gap < 10% | 97.53% | 68.98% | 50.19% |
| 512 → 2048 if gap < 20% | 98.50% | 63.81% | 42.06% |
| 256 → 512 → 2048, gap < 10% | 96.20% | 81.56% | 69.65% |
| Stable + 256 → 512 → 2048, gap < 10% | 96.29% | 80.79% | 68.73% |

The first promising candidate is therefore `512 → 2048 if gap < 10%`: it
retains 97.53% checkpoint agreement while removing 68.98% of nominal search
simulations. It is still only a candidate rule. The 52 disagreements at fixed
512 and the one late support abort show why this diagnostic cannot itself
change the live policy.

## Verification

- `ooc_mcts` and `ooc_mcts_adapter`: PASS.
- `ooc_mcts_live_startup`: PASS, including checkpoint-shadow startup and invalid
  combination/budget cases.
- `ooc_root_checkpoint_analysis_selftest`: PASS.
- Seed run: exit 0; eight expected seeds exactly once; eight MCTS rows; one
  `smoke_bomb` shadow abort; zero completed-root action mismatches.
- The shadow adds substantial runtime. Its process time was `729.81s`; this is
  diagnostic overhead and is not a production timing result.

Knowledge impact: current OOC performance research now has checkpoint
agreement, gap conditioning, leader-stability, and hypothetical-savings
evidence. No gameplay, search default, model, or quality baseline changed.
