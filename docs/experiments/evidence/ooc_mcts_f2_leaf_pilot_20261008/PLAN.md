# Pilot: F2 as the OOC MCTS leaf value (plan, 2026-10-08)

Status: frozen after independent pre-run review (launcher provenance fix in `56dee75a`); run and result in [README.md](README.md), ledger §401. Wording notes from the review were added after the run. Philipp approved the
pilot ("yes lets go", 2026-10-08) after the 128-pair cloud proposal.

## Question

Does OOC MCTS play better when its leaf value is F2 instead of X2-B?

- **F2** is the GBM trained on #334 TRAIN plus the E3 counterfactual tranche
  (§396).
- On E3 VALIDATION map rows, F2 scored NLL 0.479 against X2-B's 0.496.
- At boss relics, F2 picked +6.0 pp better than X2-B (CI +2.0 to +10.4). That
  result is descriptive: it was outside the pre-registered rule.
- F2 drops the four hidden-future fields (`nextEliteId`, `nextFight0/1/2`,
  #397), which X2-B reads. It still reads `remElites`, `remFights`,
  `monOffset` and `eliteOffset`, which V4 lists as leaks. The reviewer infers
  no leak here, because MCTS particles resample the monster lists.

§384 found OOC MCTS 21.9 pp worse than flat10k, with losses concentrated at
bosses. This pilot changes only the leaf model.

## Arms

All arms share the §384 profile (`arm_env.sh`):

- §377 live profile with fair Silver and the V4 gate stack;
- keys off and `STS_REST_WIN=0`;
- B0 `v_win` for the non-MCTS chain (`STS_WIN_NET` unset);
- `STS_STOP_AFTER_ACT=3`;
- flat exact-10k Silver, which live OOC MCTS requires.

| Arm | OOC MCTS | Leaf |
|---|---|---|
| `flat10k` | off | none (reference, §384 arm) |
| `x2b` | §384 knobs (2048 sims, cpuct 1.5, visits, early stop, V4 prior and leaf policy, widening 0.5/2, depth 32) | `native` (V4 continuation to the next map checkpoint), valued by X2-B via `STS_OOC_MCTS_LEAF_WIN_MODEL` |
| `f2` | same | same, valued by F2 |

Why the `native` leaf: F2 was trained on the first MAP row after a screen,
which is exactly the state the `native` leaf values. The default `screengbm`
leaf is a residual on a pinned X2-B anchor, so F2 cannot replace X2-B there.
§383 found `native`, `direct` and `screengbm` within noise of each other on
X2-B (wins +1.4 pp and 0 pp).

**Only `f2 − x2b` decides the verdict.** `f2 − flat10k` and `x2b − flat10k`
are descriptive. The first answers whether F2 brings MCTS back to non-MCTS
strength.

## Provenance

- **Code:** branch `claude/project-thread-oyjjlk`.
  - `47ed812a` adds `tools/vwin_export_ensemble.py`.
  - `4c98bad1` adds the F2 trees.
  - `733b9da2` adds `STS_OOC_MCTS_LEAF_WIN_MODEL` (research option, default
    unset).
  - The plan commit carries no source change.
- **Binary:** Release `one_combat`, GCC 13.3, built from `733b9da2`.
  `BINARY_SHA256 = b3a17200ed57573c9d110723ee0f1ec5eb4c4fa1937457c9e4676a5c6bf1ac6a`.
- **Models** (SHA-256 prefix):
  - `selfplay/models/ooc_strategic_tok_final.native` `e62abd833fc8cb90`
  - `models/v_win_trees.txt` (B0, non-MCTS chain) `fc52c14cb7239a33`
  - `models/candidates/v_win_x2b_trees.txt` (`x2b` leaf) `a251b33d4f71c1aa`
  - `models/candidates/v_win_f2_e3_trees.txt` (`f2` leaf) `9d1280907d5fe31c`
  - The combat models are the defaults at this commit, recorded from the
    smoke log's `[live OOC MCTS ON` line.
- **F2 export:**
  - Source: the three F2 seeds from the §396 run at dc6fd330 on Philipp's
    machine (`F2-s{0,1,2}.ubj`), margin-averaged into one tree file. The
    hashes are in `models/candidates/v_win_f2_e3_trees.json`.
  - Check: on E3 VALIDATION the export reproduces NLL 0.4788 and card-reward
    gain +0.017; boss relic is +0.015 vs +0.012 for the probability average.
  - Exporter parity against XGBoost on E3 seeds: 1.6e-7.
- **Seeds:** `57000000..57000127`, 128 paired seeds, unused by any ledger
  entry or project file. Smoke: `57009000`, not pooled.
- **Command:** Ironclad A0, `bestbench 10000 <n> 0 <seed0> <csv>`, through
  `tools/seed_guard.sh` (`launch.sh`).

## Execution

1. **Smoke:** `launch.sh BIN SHA 733b9da262c7cc9bd8018920b8943e9c5b60b7dd OUT smoke`. Every arm must exit 0.
   - `flat10k`: no `[live OOC MCTS ON` line.
   - `x2b` and `f2`: the log has `[live OOC MCTS ON sims=2048` with
     `leaf_value=native` and `leaf_win_model=` naming the arm's tree file.
   - All arms: the `.meta.json` sidecar has `silverExactRootBudgets` true.

   If a check fails, stop and report. Do not fix and rerun under this plan.
2. **Run:** `launch.sh BIN SHA 733b9da262c7cc9bd8018920b8943e9c5b60b7dd OUT` on one 4-CPU cloud container,
   4 shards of 32 seeds, one CPU each. Shard k starts the arm list at
   position k mod 3.
3. **Failures:** a shard that exits nonzero is kept and not retried. The
   analysis uses the seeds present in all arms. The verdict is provisional if
   any `x2b` or `f2` seed failed.

**Budget (Inference):** §384 measured 58 s per run for `flat10k` and 114 s for
`mcts` with `screengbm`. §383 put the `native` playout leaf at about 1.8× the
OOC cost of a direct leaf. That suggests roughly 160 s per MCTS run, about
380 CPU-seconds per seed, or about 13.5 CPU-hours: 3.5 to 4 hours of wall time
on one 4-CPU container. Doubling that is still acceptable; stop if a shard
exceeds 3× the estimate.

## Analysis and decision rule

`analyze.py OUT --out report.json` pairs runs by seed. For win and floor
differences it reports 95% paired bootstrap CIs (10,000 replicates, generator
seed 20261008), along with discordant pairs and time ratios.

| Verdict (`f2 − x2b` wins) | Condition | Consequence |
|---|---|---|
| `F2_BETTER` | CI lower bound > 0 | F2 becomes the candidate OOC leaf. A confirmation run and an ADR are needed before any default change. |
| `F2_WORSE` | CI upper bound < 0 | Negative result to the ledger; X2-B stays. |
| `INCONCLUSIVE` | otherwise | Report point estimates; Philipp decides whether to stop or extend. |

At 128 pairs the win CI is about ±10 pp, so only large effects are detectable.
`STS_OOC_MCTS` stays off by default whatever the verdict.

## Not in scope

No default change, no `screengbm` refit on F2, no other seeds, and no
learned-stop arm. Any extension needs a new frozen amendment and Philipp's
authorization.
