# A20 winrate check of the current best stack (2026-10-18)

Status: frozen before launch. Descriptive measurement, no comparison arm, no default change. Ledger §566.

Authorization: Philipp, 2026-10-18 01:00Z, thread "A20 winrate check": "can you run an a20 stack on 512 seeds on 16
workers, 4 threads each. i just want to verify the current winrate. gimme the best stack and a paramters for that."
01:02Z: "definitley some ooc mcts, distilled heart arm with recent fixes, 4096 sims, silver combat also with prior and
new fixes, maybe 10k sims?"

## Stack (`run_unit.sh`, one arm `S`)

Code: main `64b38c88` (#650), all of its defaults (play-changing fixes on, rollout root table g6_E ADR-0046, A20 CTM
ADR-0033, escape penalty 12/35, final-fight leaf ADR-0035, public futures 8). Settings otherwise follow the §524 arm B
environment, with two budget/prior changes Philipp asked for:

- Out of combat: OOC MCTS, tree prior heart1full with `student_sel.bin` (`cf6bf7fb…`, data branch
  `claude/heart1-distill-data` 5a7245aa `results/E_d64_sel_xin/`) as `STS_OOC_HEART1`, `STS_OOC_MCTS_TARGET_PRIOR=1`,
  `STS_OOC_MCTS_LEAF_SELECTS=heart1` (ADR-0047 defaults, set explicitly), rollout3 leaf (`LEAF_POLICY=heart1`,
  `LEAF_VALUE=native` = public X2-B, 3 leaf combats), **4096 simulations** (§524: 512), cpuct 1.5, visits root
  selection, early stop, depth 32, tree rules, widening K=4 α=0.75. Strategic tok net helpers as in §524.
- Combat: native Silver, flat exact 10,000 simulations per root (`bestbench 10000`, exact root budgets, learned stop
  off), **gen-6 MLP g6_E (`ca9bd7f2…`) as root prior (weight 400) and tree prior K=8** (the §516 LP prior settings;
  §516 ran them with learned stopping, this run with flat 10k).
- Imagined combats inside OOC MCTS: the A20 CTM, except that every imagined Shield and Spear and Heart fight
  (`STS_OOC_MCTS_ACT4_SILVER_SIMS=500`) and every combat the CTM refuses (`STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS=500`,
  instead of aborting the search to the V4 fallback) is played by plain native Silver at 500 simulations per root.
  Philipp, 01:15Z: "Can we do silver combat fallback for act 4? I think the ctm doesn't work for them". 01:26Z: "Do
  2.5k sims and not 100. Also do rollout 3". 01:27Z, after the thread estimated ~2.5 s per imagined Act-4
  fight at 2.5k: "500 sims, 24h timeout". CPU cost of these options is otherwise unmeasured.
- Not used (opt-in, not adopted): #642 Heart leaf td3, #652 Act-4 CTM, potion keep prior, V4/heuristic.
- Keys collected, full runs to the Heart, fair (no RNG knowledge), A20.

## Run

512 seeds 111194580–111195091, one `bestbench 10000 1 20 SEED` unit per seed through `tools/seed_guard.sh`, 32
workers (Philipp 01:32Z: "Maybe do 32 workers instead of 16") x 4 units at a time (unit line i goes to worker i mod 32 + 1), 24 h timeout per unit (rc 124).

## Report

Wins (Heart kills) / counted seeds with a Wilson 95% interval; reached Act 4 (CSV `act` ≥ 4); Act-1 deaths; mean
floor; seconds per run and MCTS CPU per OOC decision. A unit counts when rc=0 and its CSV holds the seed's row.
Reference points (other stacks, not paired): §524 arm B 10/64 Heart kills, §516 F 27/512, §497 12.0–12.4%.
