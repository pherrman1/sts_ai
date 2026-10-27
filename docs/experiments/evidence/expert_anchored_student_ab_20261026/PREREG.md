# Expert-anchored student_sel vs student_sel: paired A20 A/B (pre-registration)

Written 2026-10-26 before any campaign game ran. Origin: experiment 7 of the 2026-10-26 deep-research report
(contextual preference ranker on expert decisions), thread "Train a card ranker on expert picks". Offline analysis:
`../expert_picks_20261026/RESULT.md`. `__CODE_COMMIT__` and `__BINARY_SHA256__` are filled at freeze.

**Authorization:** Philipp, 2026-10-26 22:03Z: "lets go. how many workers would we need if we have around 16 hours?";
22:56Z: "go on 16 workers after the boss relic workers are done". Worker count: 16. Launched by the coordinator after
the independent pre-launch review passes this RUN_COMMIT.

## Question
At A20, student_sel decides every non-map screen by its argmax (ADR-0061). Offline it agrees with Baalorlord on 50% of
card rewards, 27% of smith targets and 50% of boss relics, and a GBM predicts his picks 13-23 pp better. Does a
student_sel fine-tuned toward his picks on those screens kill the Heart more often than student_sel?

## Candidate (fixed before the run; `../expert_picks_20261026/`)
- `tools/heart1/distill.py` from student_sel's own checkpoint (`student.pt` `1f96f4bf…`, data branch
  `claude/heart1-distill-data` `results/E_d64_sel_xin/`), same shape and flags (d64, 2 layers, mult 4, 4 heads,
  `--trim-map --extra-inputs`), lr 3e-4, 4 epochs, `--select last`, Wing Boots counter 1.
- Expert rows: Baalorlord's A20 Ironclad card rewards, smith targets, shop removals and boss relics, rebuilt from his
  run files (runs whose replayed deck is within 2 cards of the logged one). Target
  log((1 − α) p_student_sel + α e_expert). **Rest-site choices are not taught** (Philipp's decision card, see thread;
  §688: the bot loses 1.4-3x more HP per fight, and a separate thread prices rest vs upgrade).
- Anchor rows: the 62,576 decision records of the gen-3 exploration trajectories (§640's games), target =
  student_sel's own logits, so states the expert never visits keep student_sel's choices.
- α: 0.3 or 0.6, chosen offline before freeze by the gates below; the chosen one is `expert.bin`.
  **Chosen: α = 0.6** (only α 0.6 passes gate 1: card reward +8.0 pp, smith +12.5 pp; map drift 1.2%, no screen above
  4.7%; parity 1.1e-5; `../expert_picks_20261026/RESULT.md`). `expert.bin` sha256
  `145061444b796ca81339fdb4a7a20dd582c0aba25e2fd3df0c684bac385cae73`.

### Offline gates (held-out expert runs: 1/8 by run hash; all gen-3 bot records)
1. Held-out expert top-1 on card rewards up ≥ 8 pp over student_sel.
2. Bot-state drift: the share of gen-3 decisions whose argmax changes, per screen, is reported; > 40% on any screen
   picks the lower α; any change on map screens > 2% fails (maps are searched and must stay put).
3. Hand spot check of changed bot-state decisions per screen.
4. Native parity: `one_combat heart1score` vs torch on 500 records, max |Δ logit| < 1e-4.

## Arms (`run_unit.sh` is the source of truth)
- **A:** `STS_OOC_HEART1=student_sel.bin` (`cf6bf7fb…`).
- **B:** `STS_OOC_HEART1=expert.bin` (`14506144…`).
- Nothing else differs. Same network size, so CPU per call matches (wall ratio reported).
- Both arms: today's A20 default stack: map-only OOC search at the full budget (`STS_OOC_MCTS_SCREENS` unset,
  `STS_OOC_MCTS_FULL_BUDGET_FRACTION=1`, banner `screens_a20_default=map_full_budget`), student_sel (A) or the
  candidate (B) as tree prior, rollout policy and the deciding policy of every other screen; rollout3 + X2-B leaf with
  M0 calibration; default CTM; learned Silver stop with exact root budgets; Act-4 strong (ADR-0060); g7f_E root table
  and prior; boss-only prior playouts; flexible keys; Wing Boots counter on; engine fixes explicit. The env list is
  §683's MAP arm with the screen filter left at its default.

## Seeds and scale
- **111384000–111385023** (1,024 seeds, reserved by the coordinator 2026-10-26 22:18Z), smokes 111385990–111385999.
- One unit = one seed, A and B in sequence (order rotated by seed % 2), 7 h timeout per arm.
- Cost: §683's MAP arm took 647 s per game on a busy 4-lane container, before Act-4 strong. Expected 0.18–0.25
  core-h per game → 2,048 games ≈ 370–510 core-h; on 16 workers × 4 lanes ≈ 6–8 h wall if containers are not slowed.

## Endpoints and decision rule (`analyze.py`)
- **Valid seed:** both arms rc 0, footer `complete` and `integrityPassed`, all banner checks pass. Invalid seeds are
  reported, not replaced.
- **Futility look (the only interim look):** once the first 256 seeds (111384000–111384255) are verified,
  `analyze.py DIR --futility`: Act-4 arrival B − A ≤ −3.0 pp → **STOP** (remaining units cancelled, verdict STOP).
  Otherwise the run continues unchanged. No look can stop the run for success.
- **Primary:** Heart kills, B − A, paired: exact McNemar p and a 95% seed-bootstrap CI.
  - **IMPROVED:** p < 0.05 and CI above 0, with B's mean wall ≤ 1.10× A's. Then the candidate is proposed as the A20
    student and Philipp decides.
  - **WORSE:** p < 0.05 and CI below 0.
  - **NOT_SHOWN:** anything else; student_sel stays.
- **Secondary:** Act-4 arrival, kills per Act-4 arrival, mean floor, deaths by act; first-divergence attribution by
  screen (which screen's change first separated each pair).
- The candidate changes only ~3% of bot card-reward decisions, so many pairs will be identical or diverge late;
  the discordance is likely below the 21% assumed next, which narrows the CI but needs a large per-change effect.
- Power (gen-1b/2 discordance ~21%): 1,024 pairs give a 95% half-width of about ±2.8 pp; 80% power at about 4 pp.

## Scheduling
`schedule queue`, lease 45 min, share `/mnt/project-files/expert-anchored-ab`. The key-rules A/B launches at the same
time on its own workers, so expect slower containers.
