# AZ loop generation 0: A20 self-play capture (pre-registration)

Authorized by Philipp, 2026-10-19:
- 21:57Z: "Do 4096, do the stopped learning, freeze later. But maybe let's already measure runtime".
- 22:01Z, confirming the learned stop: "Oke do learned for now".
- 22:05Z, launch: "wait for the two merges it wanted, then freeze on this new main, and start as many seeds such that 32 workers are done in 6 hours".

Thread "AZ loop readiness"; decision history in `/mnt/project-files/az-loop-readiness/READINESS.md`.

## Purpose
Gen 0 is the first data generation of the AlphaZero loop (ADR-0043 Gumbel completed-Q targets). It produces:
1. **Policy-target rows** (`heartoutcomegen ... policy`) for every searched OOC decision of A20 runs. Each row has the student_sel record and tokens, the prior, visits, Q, checkpoints and `root.fullBudget`, and is joined to the run outcome.
2. **Real-combat CTM rows** (`STS_HEART_OUTCOME_CTM_ROWS=1`, `*.ctm.jsonl.gz`), used to check CTM drift (§470 gates).
3. **A paired search-off arm** on the same seeds: student_sel alone through `bestbench`. It gives the descriptive "search vs prior" contrast.

This is data generation. It makes no confirmatory claim. The paired contrast is reported as descriptive: Heart kills and Act-4 reach per arm, McNemar exact p.

## Frozen configuration
See `run_unit.sh`, which is the source of truth.
- **Search arm:** OOC MCTS with 4096 sims. Prior: student_sel (`heart1full`, TARGET_PRIOR=1, LEAF_SELECTS=heart1). Leaf: rollout3 + X2-B public. Imagined Act-4 fights use CTM with the ADR-0048 survival model; other CTM-refused fights use Silver 500.
- **Search stops:** learned OOC stop `models/candidates/ooc_learned_stop_trees.txt:0.99`, set explicitly. The gap stop is off (`STS_OOC_MCTS_GAP_STOP=0`). 25% of roots get the full budget (`STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25`), exempt from every stop. Refusal pruning is on (ADR-0052).
- **Real combats (both arms):** flat exact-10k Silver. run_driver.cpp refuses Silver learned stop when OOC MCTS is on. g7f_E is the rollout root table and the root/tree prior (weight 400, tree prior from 8 visits).
- **Both arms:**
  - flexible keys (`STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask`, Act-3 backstops kept);
  - `STS_OOC_HEART1_WING_BOOTS_COUNTER=1` (#681);
  - `STS_ACTIVE_POWER_FEATURES=1`, `STS_REWARDLESS_COMBAT_RNG_FIX=1`, `STS_HAND_UPGRADE_ALL_FIX=1`.
- **Training rules for gen-0 consumers:**
  - Train the value head only with `tools/heart1/distill.py --extra-inputs`, with the Wing Boots flag = 1 recorded in provenance.
  - Never use the capture `value` field (the untrained student_sel head) as a target.
  - Pack combat nets with STS_ACTIVE_POWER_FEATURES=1.

## Seeds, budget, layout
- 1,664 seeds 111140712-111142375 (coordinator-approved 2026-10-19 22:30Z). One unit = one seed, both arms in sequence.
- 32 workers × 4 parallel. Timeouts: 7 h for the search arm (rc 124), 2 h for the off arm.
- Timing basis, 2026-10-19 on #680 head aa313f25, 4 seeds: search arm mean 15.8 min (323-1461 s), 1-2 min for the off arm. Expected wall about 4.8 h.

## Validity and analysis
- A seed is valid when both arms have rc 0, the search-arm footer has `complete` and `integrityPassed` true, and both banner checks pass (learned stop loaded, Act-4 survival model).
- Invalid seeds are reported, not replaced.
- Verify with `python3 tools/cloud/verify_campaign.py docs/experiments/evidence/az_gen0_20261019`.
- Ledger §TBD reports:
  - row counts, the fullBudget fraction, Heart kills per arm with a paired 95% CI, and CTM row counts;
  - no gate.
