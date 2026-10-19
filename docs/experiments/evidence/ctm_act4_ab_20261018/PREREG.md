# Act-4 CTM survival model A/B in the A20 stack (pre-registration, 2026-10-18)

Status: frozen before launch. No unit has run. Ledger entry §TBD (the next free number at merge).

Authorization:
- Philipp, 2026-10-18 01:21Z, in the Act-4 CTM thread: "Merge 652, do 8 workers", answering the proposal of a
  512-pair A20 A/B (00:5xZ).
- Seeds: 111140200–111140711 for the run (coordinator reservation); smokes use 111194390–111194449.

## Question

Does the opt-in Act-4 survival model (§527, `STS_CTM_ACT4_SURVIVAL_MODEL`, trees `05279b3c…`) win more A20 runs when
OOC MCTS prices Shield and Spear and the Heart with it instead of the CTM survival head? The CTM predicts 0.17 Heart
death where the teacher dies 0.68 (§527 TEST). Its rollouts and leaves therefore overrate Act 4, which bears on late
Act-3 and Act-4 decisions (rest, shop, potions, keys). **Inference** (audit `ctm-a20.md`): +2–4 pp Heart kills.

## Arms (`run_unit.sh`)

- **A (control)**: the standard A20 stack at main `95c1ef1f`: keys collected, full runs, 512 OOC simulations,
  rollout3 leaf, `STS_OOC_HEART1=student_sel.bin` (`cf6bf7fb…`), `STS_OOC_MCTS_TARGET_PRIOR=1`,
  `STS_OOC_MCTS_LEAF_SELECTS=heart1` (the §524 arm B, Philipp's 23:01Z standard). The calibrated A20 CTM
  (ADR-0033) is on in both arms.
- **B (treatment)**: A plus `STS_CTM_ACT4_SURVIVAL_MODEL=$RUN/ctm_act4_survival_trees.txt` (copied from the share
  and hash-checked by `worker.sh setup`).

Paired by seed: same seed, same worker. 1,024 one-seed `bestbench` units through `tools/seed_guard.sh`, 8 workers, 4 at
a time, 4 h timeout per unit. Expected cost about 300 s per run (§524), about 85 CPU-h in total.

## Decision rule (`tools/analyze_act4_ctm_ab.py`)

- Primary: Heart kills (CSV `won`), B vs A on paired seeds. Exact two-sided McNemar on the discordant pairs; 95% CI by
  seed bootstrap (2,000 resamples, `random.Random(527)`). IMPROVED if the difference is > 0 and p < 0.05, WORSE if
  < 0 and p < 0.05, otherwise NOT_SHOWN. INVALID if more than 16 seeds lack a counted unit in either arm.
- Secondary (descriptive, no decision): reached Act 4 (act-3 clear), Act-4 conversion (kills per clear), paired mean
  floor difference, act-1 deaths, seconds per run, MCTS CPU per OOC decision, decision-source counts.
- Sanity: the `[ctm-act4-survival]` load line never appears in A logs and appears in B logs of runs whose search
  reached an Act-4 combat.
- Power: at ~12% Heart kills, 512 pairs detect roughly +4–5 pp; a +2 pp effect would be NOT_SHOWN.
- No default change whatever the outcome. IMPROVED makes the model a default candidate that Philipp decides on.
  NOT_SHOWN and WORSE go to the ledger.
