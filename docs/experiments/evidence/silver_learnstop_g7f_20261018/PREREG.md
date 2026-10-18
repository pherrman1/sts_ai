# Learned stopping with the gen-7f table and prior at A20: pre-registered plan

Authorization: Philipp 2026-10-18 13:46Z ("can you start experimenting with combining learned stopping and the
new rollout? i.e. make sure that this a strong enough combat model with 2.5k sims") and 17:39Z ("do the
learned stopping test plan"); 8 workers per the plan posted in the gen-7 thread (15:5xZ). Code commit
`code_commit` in `campaign.manifest` = main f15b345b (merge of #668, which made g7f_E the default rollout
root table, ADR-0049). The result gets the next free ledger § when it is recorded.

## Question
With the gen-7f MLP as rollout root table and as root/tree prior, does Silver's learned stopping (ADR-0026)
play as well as flat 10k at A20, and how much does flat 2.5k lose? §516 answered the first question for the
old stack (student C, no table, g6_E prior); this re-runs it on the current stack and adds the 2.5k arm.

## Arms (same binary, same seeds, paired; `run_unit.sh`)
| Arm | Silver budget |
| --- | --- |
| F10 (control) | flat exact 10k (`STS_SILVER_LEARNED_STOP=0`, `bestbench 10000`) |
| F25 | flat exact 2.5k (`STS_SILVER_LEARNED_STOP=0`, `bestbench 2500`) |
| L | learned stopping (`STS_SILVER_LEARNED_STOP=1`, checkpoints up to 10k, `bestbench 10000`) |

Common: `STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated
STS_SILVER_VNET_LEAF_DIRECT=0 STS_ACTIVE_POWER_FEATURES=1`;
`STS_SILVER_ROLLOUT_ROOT_TABLE=STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt` (sha256 c45dcc0a…),
`STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_SILVER_TREE_PRIOR_MIN_VISITS=8`. A20 full runs to the Heart
(`STS_STOP_AFTER_ACT=0 STS_COLLECT_KEYS=1 STS_FAIR=1`), one thread per process. A unit whose log lacks
"rollout root table model loaded: models/combat_policy_mlp_g7f_E.txt" is recorded rc=97.

**OOC policy:** every out-of-combat decision by student_sel `policyStep` (`STS_OOC_HEART1=student_sel.bin`,
sha256 cf6bf7fb…, no OOC MCTS, no `STS_OOC_STRATEGIC_*`, so no V4 net); only the key rule runs before it.
`STS_OOC_DECISION_TRACE` records the deciding policy; the report lists the counts per arm.

## Seeds and size
512 seeds 111197822-111198333, 3 arms, 1,536 units in `units.txt` (arm-major, so unit i and its paired
units land on worker i%8+1). 8 workers, 4 units at a time, unit timeout 2 h (rc 124).

## Endpoints and decision rules (`analyze.py`)
A seed counts only when all three arms finished with rc 0 and wrote their result rows; dropped seeds are listed.
- **Primary:** reached Act 4 (`act >= 4` or `won`), paired L − F10, Newcombe (1998, method 10) 95% interval.
  NON_INFERIOR when the lower bound > −5 pp; LOSS_SHOWN when the upper bound < 0; otherwise NOT_SHOWN.
- **Secondary:** F25 − F10 reached Act 4, same rule. Heart kills for both (paired interval, exact McNemar p),
  mean floor, mean process CPU seconds per run and the CPU ratios L/F10 and F25/F10.
- L − F25: descriptive only.

## Smoke (seeds 111195812-111195813, not part of the test; frozen binary 636258d7…)
All 6 units rc 0; table and prior loaded in every arm; learned stop on only in L. OOC decisions: heart1
585, heart_key 15, nothing else. CPU per run F10 36.8 s, F25 31.2 s, L 19.6 s (2 seeds, noisy).

## Cost estimate (Inference from §516 and the smoke)
About 1.5–2 CPU-min per seed for all three arms, 13–17 core-hours; per worker roughly 30–45 min wall.
