# §487 OOC MCTS with the V4 policy inside the rollouts (2026-10-15)

Pre-registration: [PREREG.md](PREREG.md). Result and interpretation: ledger §487 in `docs/experiments/ledger-06.md`
(after the run).

- Code commit `8ffa30a9` (`CODE_COMMIT`, main `5dbdcfc4` plus `STS_OOC_MCTS_LEAF_POLICY=prior`), Release
  `one_combat` `2779f937…` (`binary.sha256`, GCC 13.3.0, cloud container). Main's own build reproduces the §486 binary `7fa2a7e9…` in a cloud container.
- Arms (`arm_env.sh`): `v4` (the §486 `v4` arm: §433 `combo`, V4 tree prior, chain rollouts) and `v4roll` (the same
  with V4 policy-head argmax rollouts). One `bestbench 10000 1 20 SEED` unit per seed and arm (`run_unit.sh`, 8 h
  timeout), `NWORKERS` workers over the cohort in `COHORTS` (`worker.sh`); results go to
  `/mnt/project-files/v4-rollout-487/`.
- Smoke (run binary, `/mnt/project-files/v4-rollout-487/smoke.tar.gz`, sha256 `c6e97dc9…`): control on §486 seeds
  107000049 and 107000025 reproduces the §486 `v4` rows (won, floor, act, hpEnd) and every OOC decision in the trace
  exactly (58/58 and 66/66), so the default-off option leaves the chain rollouts unchanged; treatment on fresh seeds
  74072160–74072161 logs `leaf_policy=prior`, takes 1.10M and 2.39M V4 rollout steps, no continuation-limit aborts,
  MCTS CPU 3.1 and 5.3 s per OOC decision (control 4.0 and 2.7 s), 249 and 489 s per run (act 2 deaths).
  Smoke seeds 74072160–74072169 are reserved for this thread (160–161 used).
- Analysis: `python3 tools/analyze_rollout_prior_487.py report.json DIR... --ref486 DIR...` over the extracted `out/`
  folders of this run and of §486 (selftest: `python3 tools/analyze_rollout_prior_487.py selftest`).
