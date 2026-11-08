# Silver leaf prices from the stage-2 pilot: whole A20 runs, net-0420 policy alone, flat Silver 1,000 (pre-registration, 2026-11-08)

**Authorization.** Philipp 2026-11-08 00:06 CET: decision card "Offline-Fit, dann Gate" (stage 4 of the leaf plan:
fit offline on all pilot units, then propose a gate). At 00:40 CET he first declined the gate ("vermutlich
verschwendetes compute"), then typed at 00:48 CET: "Na gut lass doch p1 messen, die 3 vorgeschlagenen arms von dir."
and at 00:50 CET, for the worker count: "Glaube 4 workers reichen" (leaf-estimator thread of this project).

**Question.** Do the global victory-leaf prices fitted in stage 4 on the pilot's CRN pairs raise the A20 Heart kill
rate of whole runs over Silver's default leaf (arm P1)? Does the part of P1 that earlier gates never tested, the
Fairy price, do so on its own with max HP and gold (arm PF)?

**Motivation.**

- Stage-2 pilot (ledger §763): 61,739 forks at fight ends with one change per copy, played to the run end on common
  random numbers. Stage 4 (offline, `/mnt/project-files/leaf-plan/stage4/RESULT.md`, plan `PLAN.md` written before
  the fit on all units): with the HP scale fitted per act on the HP pairs, four global prices explain the non-HP
  pairs better than Silver's default leaf. Cross-family skill against a per act × family constant: P1 26.6 bp
  [17.7, 35.3], default 12.2 bp [7.5, 17.5], P1 − default +14.4 bp [8.3, 20.2]. Per-act prices (P4) are not clearly
  better (+3.8 [−0.2, +7.5]) and unstable in acts 3-4, and no state-dependent model (net-0420's critic, MLP heads on
  its trunk, LightGBM) beats P1.
- P1 in HP units: Fairy 47.6 on top of its death save (0.3 max HP), every other potion 3.67, max HP 2.41 per point,
  gold 0.124 per gold (fold ranges 40-53, 3.1-4.2, 2.2-2.7, 0.11-0.14). Silver's defaults: 11, 11, 2.0, 0.25.
- Prior evidence against cheaper potions: §542 (student_sel, exact 10k Silver) arm W, with non-Fairy potions 5.0,
  Fairy and Smoke Bomb 11, max HP 1.1 and gold 0.01, lost 5.9 pp of wins [−9.0, −2.5]; §513 found potions 7.8
  NOT_SHOWN with negative point estimates. The pilot measures the marginal value of one held potion under a policy
  that spends potions at price 11; a leaf that spends them at 3.7 is a non-marginal change. The Fairy price was never
  tested (W kept it at 11) and is the pilot's best-resolved price (74.8 HP [65, 85] in total). PF separates the two.

**Setup.** The pilot's source-run setting (`../fight_end_pairs_pilot_20261107/run_unit.sh`), as a whole-run
benchmark like §762: LONG_C's net-0420 (sha 8c0bd16c…, the PPO baseline) as the whole out-of-combat policy,
temperature 0, no OOC MCTS; combat = Silver with an exact flat budget of 1,000 simulations per root, learned stop off,
Act-4 strong off, g7f_E root and tree prior (combat B). `bestbench 1000 1 20 SEED`. Engine: main ccc53a48 (#1003
merged), every other default as on main; no code change, the three flags exist (`STS_SILVER_POTION_WEIGHTS` #610,
`STS_SILVER_MAXHP_WEIGHT` and `STS_SILVER_GOLD_WEIGHT` #673).

**Arms.** All three on every seed, in an order rotated by seed (arm index (i + seed) mod 3). The leaf changes every
combat decision, so no control reuse.

| arm | environment added to the common setting |
|---|---|
| D | none (potions 11, Fairy 11 + death save, max HP 2.0, gold 0.25) |
| P1 | `STS_SILVER_POTION_WEIGHTS=*=3.7,FAIRY_POTION=47.6` `STS_SILVER_MAXHP_WEIGHT=2.4` `STS_SILVER_GOLD_WEIGHT=0.12` |
| PF | `STS_SILVER_POTION_WEIGHTS=*=11,FAIRY_POTION=47.6` `STS_SILVER_MAXHP_WEIGHT=2.4` `STS_SILVER_GOLD_WEIGHT=0.12` |

`run_unit.sh` checks per game: binary and net hashes, the seed line, flat budget, the root-prior banner; in P1 and PF
the line `[silver] research leaf: gold=0.12 maxhp=2.4 victoryTurnPenalty=0.4 concave=0 potionWeights=on`, in D no
research-leaf line; no max-backup, risk-veto or price-table line in any arm; the `[heart1_ppo]` game line or a listed
combat abort.

**Seeds.** New block 111820000-111822047 (2,048 seeds, all three arms); smokes 111829990-111829999. Checked unused in
the repository (main ccc53a48 and the open PR branches; again on main 24a08be2) and the project notes on 2026-11-08.
The smokes 111829990-111829991 were played before the launch.

**Primary.** Two contrasts, X − D for X in {P1, PF}: d = Heart kill X − D per seed, seeds in ascending order. A seed
counts for a contrast if both of its games finished rc 0 with all checks (a combat abort is a counted loss and
listed); dropped seeds are listed, never imputed; more than 20 dropped seeds in a contrast = INCOMPLETE. SPRT per
ADR-0064 (`tools/sprt_gate.py` at ccc53a48), variant **gainer**: d0 = 0, d1 = +2 pp, **α = 0.025** (Bonferroni over
the two contrasts), β = 0.05, look every 64 pairs, cap = analysed seeds ≤ 2,048. H1 → **GO**; H0 → **NOT_SHOWN**;
CAP → 97.5% seed bootstrap of the mean d (10,000 resamples, seed 20261108): GO if lo > 0, STOP if the mean ≤ 0, else
INCONCLUSIVE. The mean d and its 95% CI are reported in every case. `analyze.py --self-test` covers drops, an abort,
both verdict paths and INCOMPLETE.

**Candidate rule.** One contrast GO → that arm is the candidate. Both GO → P1 only if the 95% CI of P1 − PF is above
0, else PF (fewer changes). Neither → no candidate.

**Secondary reading (not a gate).** Each contrast through `sprt_gate.py --variant nonregression` (d0 = −1.5 pp,
α = β = 0.05) and the bootstrap: NOT_WORSE if the 95% lo > −1.5 pp. P1 − PF (the potion level) with its 95% CI.
Descriptive: Act-3 clears and final floor (X − D with CIs), cpu_sec/run per arm and its ratio to D, combat aborts,
games over 300 s wall, max wall per arm.

**Decision.** A candidate becomes a default candidate for combat B and the PPO loop; Philipp decides, with its own
PR and ADR. Otherwise the flags stay research-only and the defaults stay. A ledger entry either way; a P1 NOT_SHOWN
with a negative mean d would repeat §542 with Heart-kill prices, which says that marginal CRN prices are not directly
usable as leaf weights (relevant for the learned price head and stage 5 of the leaf plan).

**Cost.** 3 × 2,048 games at ~21 s (the pilot's source runs took 20.7 s on average) ≈ 36 core-h; 4 workers × 4 lanes
≈ 2.2-2.5 h plus setup. The SPRT is read after the full run (no early stop of the campaign).

**Smoke (author container, before launch).** Seeds 111829990-111829991, all three arms rc 0 with all checks; see
README.md.

**Launch.** 4 workers (Philipp 00:50 CET), started by the coordinator with `BRIEF-worker.md`; RUN_COMMIT is the commit
that adds this text (named in the share copy of the brief and in the result). K's prelaunch review of this folder runs
during the launch. If it requires a change to `run_unit.sh`, the manifest or the arms, the workers are stopped, the
outputs are discarded unanalysed and the campaign restarts from a new run commit on the same seeds. The analysis rules
above may be corrected only before any game of the block is read.
