# 2026-08-07 — Gate-stack-distribution vnet retrain (§129): NULL, deployed model stays

Date: 2026-08-07
Session/task: §126 follow-up — retrain the combat value leaf on
gate-stack-distribution labels (`STS_DATAGEN_GATES`) and gate whether it
replaces the deployed honest-data model.

## Decision

- **No replacement.** The gate-stack-distribution vnet (`build/v_combat_gated.txt`,
  733 trees, sha256 `5322c9f1…`) does not beat the deployed honest-data model
  (`build/v_combat_honest.txt` @α0.3): at its own α optimum it is −4.3pp
  @1k/α0.3, +2.7pp @1k/α0.5, −3.1pp @3k/α0.5 vs the deployed points — all
  n.s., direction mixed (EXPERIMENTS.md §129). The deployed model and the
  §126 default stay.
- `STS_DATAGEN_GATES` stays opt-in (default off; unset behavior verified
  byte-identical): useful when datagen distribution alignment is wanted for
  other label types, and it is now the documented way to produce
  gate-stack-distribution combat labels.

## Rationale

- The gated model's α optimum shifted up (0.5 vs 0.3), consistent with
  better calibration on the deployment distribution — the retrain changed
  the model as expected — but the transfer ceiling is not higher: both
  models strongly beat no-vnet (~+9-15pp) and are statistically
  indistinguishable from each other. The §126 +12pp gain is robust to the
  label distribution; the label distribution is not the next lever.
- **Inference:** the heuristic-OOC label distribution is a sufficient
  training set for the leaf's job (valuing imagined battle continuations),
  so the run-level distribution mismatch does not cost measurable winrate.

## Alternatives considered

- Promote the gated model at α0.5 — rejected: +2.7pp @1k (n.s.) against
  −3.1pp @3k (n.s.); no significant win at either operating point, and a
  flip would invalidate the §126 provenance for no measured benefit.
- Retrain on more gated seeds — rejected: 499k rows vs 287k showed no
  volume effect beyond calibration; the comparison is a model-distribution
  question, not a data-volume one.

## Evidence

- `EXPERIMENTS.md` §129 (full gate table, provenance, artifacts).
- `apps/one_combat.cpp::datagenGateStack`, `runCombatGenSeed`,
  `g_datagenGates` (env `STS_DATAGEN_GATES`).
- Per-seed CSVs `build/gv_{a03_1k,a05_1k,a07_1k,a03_3k,a05_3k_final}.csv`
  (the α0.5 @3k arm was resumed mid-run at 24 threads: 171+81+4 gap seeds
  merged by seed — a working kill/restart resume pattern since `bestbench`
  rows are per-seed and seed-order-independent).
- `docs/archive/research/plans/plan-winrate-ideas-2026-08-07.md` §4.3 follow-up.

## Status and follow-up

- Implemented and recorded; no default change. The vnet line is closed at
  both label distributions; remaining vnet follow-ups (if the line reopens)
  would be architecture (e.g. a transformer leaf), not labels.
