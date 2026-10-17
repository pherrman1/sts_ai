# Card-select student A/B: student_sel vs student C in the A20 Heart stack (pre-registration, 2026-10-17)

Status: frozen before launch. No unit has run. Ledger §524 (coordinator reservation).

Authorization:
- Philipp, 2026-10-17 21:45Z, decision card "Run a short A/B of the new student against student C in the A20 Heart
  stack?": chose "64 seeds".
- Philipp, 21:45Z: "use 8 workers for that".
- Seeds: 111193400–111193463 for the run and 111193464–111193499 for smokes and the reviewer (coordinator reservation).

## Question

Does student C re-distilled with heart1's card-select labels play better as the OOC tree prior and rollout policy,
when card-select targets use it? The student is `student_sel.bin` `cf6bf7fb…`:
- trained on 1.16M keys-on/Act-4/card-select rows plus the old 1.01M rows, with relic counter, act and card-misc inputs;
- data branch `claude/heart1-distill-data` 5a7245aa, `results/E_d64_sel_xin/`.

Offline gate PASS on held-out seeds (`gate.txt`), top-1 vs heart1:
- REMOVE: 0.06% → 97.6%
- TRANSFORM: 0.11% → 97.5%
- UPGRADE: 18.8% → 89.6%
- node rows by act: 90/85/82% → 96/94/91%
- old capture rows: 93.0% → 94.0%

Offline agreement is not play strength. This A/B measures play strength.

## Arms (`run_unit.sh`)

- **A (control)**: the A20 Heart stack the capture ran in ("off" arm of `heart1_select_capture_20261017`, the §504
  arm C), on this commit's defaults:
  - keys collected, full runs (Act 4 included), 512 sims, rollout3 leaf;
  - main's heart1full tree prior (ADR-0042);
  - `STS_OOC_HEART1=studentc.bin` (`eff2f74f…`).
- **B (treatment)**: A with three changes:
  - `STS_OOC_HEART1=student_sel.bin`;
  - `STS_OOC_MCTS_TARGET_PRIOR=1`: compound smith/remove/transform targets share their source's prior by the student's
    logits on the select the source opens;
  - `STS_OOC_MCTS_LEAF_SELECTS=heart1`: rollouts score every card select with the student instead of the chain.

  The tree's own non-UPGRADE card-select screens stay uniform in both arms (`heart1FullScreen`). Lifting that is a
  follow-up only if B helps.
- Both arms also write `STS_OOC_MCTS_DECISION_LOG`. It is observation only and produces the decision-source counts.

Paired by seed: same seed, same worker. The units are 128 one-seed `bestbench` runs through `tools/seed_guard.sh`,
on 8 workers, 4 at a time, with a 4 h timeout per unit.

## Decision rule (`tools/analyze_student_sel_ab.py`)

- Primary: act-3 clear (CSV `act` ≥ 4, i.e. reached Act 4), B vs A on paired seeds.
  - Statistics: exact two-sided McNemar on the discordant pairs; 95% CI by seed bootstrap (2,000 resamples,
    `random.Random(20261017)`).
  - IMPROVED if the difference is > 0 and p < 0.05. WORSE if it is < 0 and p < 0.05. Otherwise NOT_SHOWN.
  - INVALID if more than 4 seeds lack a counted unit in either arm. A unit counts when rc=0 and its CSV holds the seed's row.
- Secondary (descriptive, no decision):
  - Heart kills (`won`) and the paired mean floor difference;
  - act-1 deaths;
  - seconds per run and MCTS CPU per OOC decision;
  - decision-source counts from the decision logs, card-select rows in particular.
- Power: 64 pairs detect only a large act-3 effect, of the §486 size (+23 pp). A +5 pp Heart-kill difference would
  need ~700–1000 pairs, so Heart kills here are descriptive only.
- No default changes whatever the outcome. IMPROVED makes `student_sel` a candidate that Philipp decides on.
  NOT_SHOWN and WORSE go to the ledger.

## Not in scope

No change to the tree's card-select screens, the leaf value model, sims or keys policy.
