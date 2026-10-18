# A/B: prior-argmax playouts vs production greedy Silver (A20, fight level, 8 workers)

Status: authorized by Philipp (2026-10-18 15:03Z, thread "Better fast leaf evaluation": "Yes but do 8 workers.
Make sure that act4 fights go through ctm. Fallbacks should not use the prior rollout"), answering the proposal to
compare prior playouts with production Silver at about matched CPU. Written before any result. Ledger §540 (with
the pilot entry). Seeds: 111197708–111197771 (64 sources) from the block 111197692–111197791.

## Background

Pilot (same PR, `../silver_prior_playout_pilot_20261018/`): at equal 2,500 simulations, prior-argmax playouts
lowered HP lost by 1.45 [0.31, 2.51] per fight, score +3.8 [−2.4, +10.3] INCONCLUSIVE, at 7.6x CPU per simulation
(268 vs 35 ms per decision; production greedy 10k: 145 ms).

## Design

`one_combat ctmsilvergen` at Ascension 20, armset `priorpl`, the pilot's harness (student C source runs, gen-6 E
root prior w400, hallway every 3rd, R = 2 combat-RNG redraws, ADR-0046 root table on, keys off, run stops after
Act 3 unless the source collects Act 4 by itself). All arms use the root prior and the tree prior (K = 8):

- `greedy10000`: production Silver budget with greedy playouts (control arm of the A/B).
- `priorpl2500`: prior playouts at 2,500 simulations (about 1.8x the control's CPU per decision in the pilot).
- `priorpl10000`: prior playouts at 10,000 simulations (upper end, about 7.6x).

Imagined fights: the source runs use no OOC MCTS, so there are none. The armset refuses
`STS_OOC_MCTS_ACT4_SILVER_SIMS`, `_UNSUPPORTED_SILVER_SIMS` and `_COMBAT_RESOLVER`, and
`playImaginedCombatWithSilver` always forces greedy playouts, so fallbacks never use prior playouts.

Campaign: 64 units (one source seed each), 8 workers, 4 units at once per worker (`tools/cloud/worker.sh`).

## Analysis and decision rule

`analyze.py` (the pilot analyzer with these arms) on the extracted worker tars: per arm fight score, win, HP lost,
CPU per fight and per simulation; paired contrasts vs `greedy10000` with 95% seed bootstrap (all, boss, elite,
normal, Act 4).

Labels per prior arm vs `greedy10000`, all fights: score BETTER if the CI lower bound > 0, WORSE if the upper
bound < 0, else NOT_SHOWN; HP lost BETTER if the CI upper bound < 0, WORSE if the lower bound > 0, else NOT_SHOWN.
`priorpl2500` is the primary arm (the one cheap enough to deploy in real fights). No default change in this PR;
any default proposal goes to Philipp with these numbers.
