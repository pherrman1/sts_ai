# Pilot: live OOC MCTS on vs off (frozen plan, 2026-10-06)

Status: **plan only; not authorized to run yet.** Philipp authorizes the run in
the project thread. The run thread then records the binary hash below before any
pooled seed runs.

## Question

Does live OOC MCTS with the default screen leaf (ADR-0027) play better than the
same pipeline with OOC MCTS off? Every recent OOC MCTS comparison (§367, §383)
compared MCTS variants with each other. The last on/off head-to-heads predate the
screen leaf and leaned negative: §243 `OOC_MCTS_WINRATE_DOWN` on 32 pairs, and
§249 −9.4 pp (95% CI −23.4 to +4.7) on 64 pairs.

The §383 MCTS arms won 57–62%. The §377 learned-stopping arm, with OOC MCTS off,
won 80.3% on other seeds. Those runs also differ in Silver budget policy
(exact 10k vs learned stopping), `v_win` (X2-B vs B0) and `STS_REST_WIN`, so
the gap is an **Inference**, not a measured MCTS effect. This pilot changes one
variable per step.

The answer decides whether #399 (distill the MCTS teacher), #415 (fresh
on-policy data) and an OOC MCTS default are worth pursuing.

## Arms

All arms use `arm_env.sh`. The shared profile is the §377 live profile
(`silver_learned_stop/live_env.sh`): fair Silver, the V4 strategic gate stack,
keys off, `STS_REST_WIN=0`, default `v_win` (B0, `STS_WIN_NET` unset),
`OMP_NUM_THREADS=1`. It adds `STS_STOP_AFTER_ACT=3`, which OOC MCTS needs so
that an imagined act-3 boss win is terminal (`ooc_mcts_adapter.cpp`). With keys
off this does not change real play.

| Arm | Change from the previous arm | Purpose |
|---|---|---|
| `learned` | none: current best non-MCTS play, learned Silver stopping (ADR-0026) | reference |
| `flat10k` | Silver switches to flat exact-10k root budgets (`STS_SILVER_EXACT_ROOT_BUDGETS=1`, learned stopping off). `run_driver.cpp` requires this for live OOC MCTS | combat-policy cost of MCTS's precondition |
| `mcts` | `STS_OOC_MCTS=1` with the §383 knobs (2048 sims, cpuct 1.5, visits root selection, early stop, V4 prior and leaf policy, widening 0.5/2, depth 32). `STS_OOC_MCTS_LEAF_VALUE` stays unset, so the leaf is the default `screengbm` | **MCTS effect** |

- `mcts − flat10k` isolates OOC MCTS. It is the only comparison that decides
  the verdict.
- `flat10k − learned` and `mcts − learned` are descriptive. The second answers
  the practical question: does the MCTS stack beat today's best?

## Provenance

- Code: `main` at `5e9583cc` (#416 merge) plus this evidence directory. The
  plan commit carries no source change.
- Binary: Release GCC build of that commit. The run thread records the SHA-256
  here and in the launch command before the smoke seed runs:
  `BINARY_SHA256 = <filled at freeze>`.
- Models (all tracked, SHA-256 prefix):
  - `selfplay/models/ooc_strategic_tok_final.native` `e62abd833fc8cb90`
  - `models/v_win_trees.txt` (B0) `fc52c14cb7239a33`
  - `models/candidates/v_win_x2b_trees.txt` (screen leaf anchor) `a251b33d4f71c1aa`
  - `models/candidates/screen_leaf_gbm_v1.trees` `8e2f9dc78cb31de3`
  - `selfplay/models/combat_transition_deepsets_lizard_t2.native` `abb2a9ead6efd6b9`
  - `selfplay/models/combat_transition_near_full_except_smoke_v2.native` (Brew fallback) `e9a18951710fdfe9`
- Seeds: `48000000..48000127` (128 paired seeds, unused by any ledger entry).
  Smoke: `48009000`, not pooled.
- Ironclad A0, `bestbench 10000 <n> 0 <seed0> <csv>`. Every command goes
  through `tools/seed_guard.sh` (`launch.sh`).

## Execution

1. Build the Release binary and record its hash above.
2. Smoke: `launch.sh BIN SHA OUT smoke`. Each arm must exit 0, and its
   `.meta.json` sidecar must record the arm's settings: `STS_OOC_MCTS=1` and
   the unset leaf only in `mcts`, and learned stopping only in `learned`. If anything fails,
   stop and report; do not fix and rerun under this plan.
3. Run: `launch.sh BIN SHA OUT` on one 4-CPU container: 4 shards of 32 seeds,
   one CPU each. Each shard runs all three arms, with shard k starting the arm
   list at position k mod 3. Per-seed results do not depend on order.
4. A shard that exits nonzero is kept and not retried. The analysis uses the
   seeds present in all arms and says so.

Budget estimate: about 24 s (`learned`, §377), roughly 35–40 s (`flat10k`,
**Inference** from §377's 29 s for #199) and 89 s (`mcts`, §383) per seed.
That is about 150 CPU-seconds per seed, or about 5.3 CPU-hours: roughly
1.5 hours wall time on one 4-CPU container.

## Analysis and decision rule

`analyze.py OUT --out report.json` pairs by seed and reports 95% paired
bootstrap CIs (10,000 replicates, generator seed 20261006) for win and floor
differences, discordant wins and time ratios. The verdict uses the win
difference `mcts − flat10k`:

| Verdict | Condition | Consequence |
|---|---|---|
| `MCTS_BETTER` | CI lower bound > 0 | #399 becomes the next issue; a larger confirmation run is required before any OOC MCTS default change |
| `MCTS_WORSE` | CI upper bound < 0 | #399 and #415 go on hold; OOC MCTS stays off; the negative result goes in the ledger |
| `INCONCLUSIVE` | otherwise | report point estimates and the floor CI; Philipp decides between stopping and a separately authorized extension |

At 128 pairs the win CI is roughly ±10 pp, so this pilot detects only large
effects. An inconclusive result is not evidence of parity.

Descriptive readings, which are not part of the verdict:
- `flat10k − learned` shows how much MCTS's exact-10k precondition costs.
- `mcts − learned` gives the practical headline.
- Only `mcts` changes `v_win` exposure, via the X2-B screen-leaf anchor. The
  non-MCTS fallback chain uses B0 in all arms, as production does. The §383
  runs used X2-B everywhere, so `mcts` here is **not** an exact replay of §383.

## Not in scope

No code change, no tuning, no equal-CPU arm, no other seeds. Any extension
needs a new frozen amendment and Philipp's authorization.
