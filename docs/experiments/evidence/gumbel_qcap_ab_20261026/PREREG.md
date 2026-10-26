# Gumbel root with the Muesli-style Q cap at A20 map roots: paired A/B (pre-registration)

Philipp, 2026-10-26 22:57Z (thread "Cap Q influence in OOC search"): "merge 689, lets go with 16 workers after the
boss relic thing is done". #869 merged as §689 (`9a37d780`). This A/B is the play test §689 left open.

## Question
At A20 on today's stack, do map roots that run a Gumbel sequential-halving root with the capped Q term
(`STS_OOC_MCTS_GUMBEL_QCAP=1`, M = 16, 2048 simulations) kill the Heart at least as often as PUCT at 4096, at lower
CPU?

## Evidence so far
- §635: uncapped Gumbel SH (M16@2048) lost 9.4% vs 20.7%. It overruled the prior on 17.3% of searched roots,
  because (50 + N)·min-max Q makes any Q gap worth hundreds of logits.
- §689 (offline, 48 full roots, same leaf as reference): capped SH leaves the prior argmax on 10.4% of roots
  (uncapped 66.7%, PUCT 2.1%), never at top prior ≥ 0.9; regret vs the leaf reference equals PUCT 4096
  (+0.44e-3 [−1.14, +2.08]) at about half the full-root CPU.
- Guess, no evidence: play effect 0 to +1 pp. The realistic outcomes are NOT_SHOWN or NON_INFERIOR at lower CPU.

## Arms (`run_unit.sh` is the source of truth)
- **A (control):** today's A20 OOC default. `STS_OOC_MCTS_SCREENS` unset = map roots only (ADR-0061), each at the
  full 4096-simulation budget because `STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25` is set; PUCT; most-visited played.
- **B:** A plus `STS_OOC_MCTS_GUMBEL_ROOT=16 STS_OOC_MCTS_GUMBEL_QCAP=1 STS_OOC_MCTS_FULL_ROOT_SIMS=2048`. Map roots
  sample 16 actions (all of them on nearly every map root) by Gumbel + log prior, run sequential halving over 2048
  simulations, and play the best survivor by g + log prior + clip((Q − V)/SE, −1, 1). Every node below the root,
  and every non-map screen, is identical to A.
- Common: `heartoutcomegen 1 SEED OUT policy`, student_sel (`cf6bf7fb…`) as OOC prior and rollout net,
  TARGET_PRIOR=1, LEAF_SELECTS=heart1, LEAF_POLICY=heart1, default A20 leaf (rollout3 + X2-B with M0, ADR-0057),
  default CTM (§679), Act-4 strong default (ADR-0060), learned OOC stop 0.99 / fast cap 1024 (inactive on map-only
  full roots), real combats with the learned Silver stop (`gbt-0cac7cc64364`, exact root budgets), g7f_E root table and
  prior, boss-only prior playouts, flexible keys, Wing Boots counter 1, `STS_ACTIVE_POWER_FEATURES=1`, engine fixes
  explicit. Arm order alternates by seed parity.

## Seeds, budget
- 512 fresh paired A20 seeds 111381000–111381511 (free block 111381000–111389989, below the expert-anchored A/B's
  reservation 111384000–111385023). Smokes 111383990–111383991.
- 16 workers × 4 parallel (Philipp's count), `schedule queue`, lease 45 min. One unit = one seed, both arms, 7 h
  timeout per arm. Launch after the boss-relic (#856) workers finish.
- Cost (estimate from the smoke, see SMOKE.md): about 2 × 512 games.

## Analysis (`analyze.py`, the §635 script)
- **Valid seed:** both arms rc 0, footer `complete` and `integrityPassed`, banner checks pass (rc 91: B must show
  `full_root_sims=2048`, `gumbel_root=16:1` and `gumbel_qcap=1`, A none of them; rc 94: both arms must show
  `screens_a20_default=map_full_budget`). Invalid seeds are reported, not replaced.
- **Primary:** Heart kills, B − A, paired difference with 95% CI and exact McNemar p.
- **Secondary:** reached Act 4, same statistics.
- **Descriptive:** mean floor; wall per arm; searched / full-budget roots; fraction of searched roots where the
  played action differs from the prior's argmax.
- **Decision rule (as §635):**
  - **WIN:** McNemar p < 0.05 with B ahead and B's mean wall ≤ 1.10× A's. Propose the capped Gumbel map root as the
    A20 default; Philipp decides.
  - **WORSE:** p < 0.05 with A ahead. Flag stays off.
  - **NON_INFERIOR:** not significant, Heart-kill CI lower bound > −5 pp and B's wall < A's. Report the CPU saving;
    any default change is Philipp's call.
  - **NOT_SHOWN:** otherwise.

## Known risks, stated before the run
- The Gumbel draw makes B's played action stochastic per root (seeded per search). With a 0.99 prior it overrules
  the prior about 1% of the time from g alone; at weaker priors more often. That is exploration noise in play.
- 512 pairs detect about ±4 pp, so a 0–1 pp effect will read NOT_SHOWN or NON_INFERIOR.
- Map-only roots differ from §635's all-screen full roots; §689's replay used all screens.
