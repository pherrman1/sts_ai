# X5 loss clusters on 15,363 A20 games (2026-11-01)

Roadmap item X5 (one-year roadmap, §739) and the rest of X4. Offline only: no games run, no seeds. Philipp,
2026-11-01 ("start a thread for x5"). Extends §729's loss mining (2,816 games) to every A20 campaign on the share
that has per-fight CTM rows. Findings: [research/a20-loss-mining.md](../../../knowledge-base/research/a20-loss-mining.md)
(section "X5: loss clusters on 15,363 games").

## Data (read-only, project share)

| label | share dir | ledger | arms (games) | in the primary set |
|---|---|---|---|---|
| vchooser | value-chooser-ab | §727 | A, B (1,536 each) | A (B lost −15 pp) |
| r1 | value-clean-labels-run1 | §720 | base (1,282) | base |
| keys | key-rules-ab | §691 | F, R (1,024 each) | F (R = rigid keys, −6 pp) |
| expanch | expert-anchored-ab | expert-anchored A/B | A, B (1,025 each) | both |
| maponly | ooc-map-only-search | §683 | D, MAP, OFF (1,024 each) | all |
| ctmcal | ctm-calibration-ab | §676 | A, C (512 each) | both |
| qcap | gumbel-qcap-ab | §693 | A, B (512 each) | both |
| vlevel | value-level-ab | §661 | A, M, MS, S (1,024 each) | all |
| cardrule | card-rule-ab | §712 | A, B, C, D (255 each) | A (B-D lost 9-19 pp) |

18,688 complete games; the **primary set** (15,363) keeps every arm within 4 pp of its campaign's best arm
(`common.primary`), which drops only arms that failed their gate badly. All are A20 Ironclad with the learned-stop
Silver combat of their date (Act 4 strong from §691 on), student_sel out of combat, with or without OOC MCTS. The
campaigns share some seed blocks (e.g. r1 and expanch both use 111384000+), so all CIs resample seeds.

`aivat-replay-676` (§698): every recorded fight of the §676 guard (1,024 games, 23,503 fights) replayed from the
identical entry state with 4 fresh combat draws at that date's production combat (Act 4 strong off).

## Scripts (`run_all.sh WORKDIR`, ~25 min, mostly share I/O; needs numpy and scikit-learn)

| script | what |
|---|---|
| `extract_all.py`, `extract_aivat.py` | compact per-game / per-replay pickles from the unit tars |
| `clusters.py` | deaths by stage × entry-HP band: share of runs, per-fight rate, P(Heart kill \| survived the same cell), ceiling, per-campaign range |
| `potential.py` | sibling-standardized excess deaths per boss/elite at equal entry-HP band and potions, × continuation = Heart-kill potential; seed bootstrap; per campaign |
| `decksig.py` | per cluster: seed-grouped 5-fold CV of death on resources vs resources + deck/relics (L2 logistic, GBM); out-of-fold deck-risk quartiles |
| `strikes.py` | boss death by Strikes left in the deck × entry HP |
| `aivat_luck.py` | per cluster: how often a real death's entry state also dies in the 4 redraws (state-determined vs luck) |
| `x4_power.py` | X4: paired SD per seed pair for Heart kill and reached act 2/3/4, every paired campaign; pairs per half-width |

## Limits

Observational. "Potential" is a counterfactual bound, not a measured effect: the sibling bound assumes a boss could
be made as survivable as its act siblings at equal entry HP and potions, and part of every gap is the boss's own
difficulty (the expert also dies more at Awakened One than at Donu & Deca). Deck features are counts by card id and
relic one-hots; synergy beyond what the GBM finds is not captured. The §698 replays are one older configuration
(§676, Act 4 strong off), so the Heart rows there are not today's Act-4 budget. No in-fight logs.
