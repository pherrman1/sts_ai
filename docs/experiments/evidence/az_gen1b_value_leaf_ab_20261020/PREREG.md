# Gen-1b value head as the rollout3 end-state value: paired A20 A/B (pre-registration, NOT LAUNCHED)

Philipp, 2026-10-20 20:34Z: "we should somehow test the value head. Open a new thread, that should give me offline
numbers first, then prepare an online comparison by replacing X2-B with the gen1b value head, but keeping rollout3".
This file prepares that comparison. A launch needs Philipp's typed authorization and a worker count, a frozen
RUN_COMMIT and an independent pre-launch review. The offline numbers are in `OFFLINE.md` (ledger §TBD).

## Question
In the gen-0 search stack, does ending each rollout3 leaf in gen 1b's value head instead of X2-B kill the Heart more
often at A20?

## Arms (`run_unit.sh` is the source of truth)
- **A (control):** gen 0's search arm, identical to arm A of `../az_gen1_ab_20261020` (`STS_OOC_HEART1=student_sel.bin`
  `cf6bf7fb…`). Every rollout3 leaf, and every other native anchor evaluation, ends in X2-B.
- **B:** A plus `STS_OOC_MCTS_LEAF_HEART1_VALUE=gen1b.bin` (`e6aa044c…`, data branch `claude/az-gen1-data` 65762545).
  Where X2-B would value a state, B uses sigmoid(gen 1b value logit) on the same heart1 record the prior and the
  AZ-loop capture rows use. States heart1 cannot encode (none expected at rollout ends, which are MAP screens) keep
  X2-B and are counted (`heart1_value_leaf_fallbacks` in the OOC support trace).
- Both arms use student_sel as prior and rollout policy, so the leaf value is the only difference. Gen 1b's policy
  head is not used. If the running gen-1b prior A/B (`../az_gen1_ab_20261020`) makes gen 1b the standard prior before
  this freezes, Philipp may swap both arms' `STS_OOC_HEART1` to gen1b.bin; that is recorded in the freeze.
- Common config (as gen 0 and the gen-1b A/B): `heartoutcomegen 1 SEED OUT policy`, OOC MCTS 4096 sims, prior
  `heart1full`, TARGET_PRIOR=1, LEAF_SELECTS=heart1, LEAF_POLICY=heart1, LEAF_VALUE=native, LEAF_COMBATS=3, learned
  OOC stop 0.99, GAP_STOP=0, 25% full-budget roots, refusal pruning, CTM rows; flat exact-10k Silver real combats
  (`STS_OOC_MCTS_REAL_LEARNED_STOP=0 STS_SILVER_LEARNED_STOP=0 STS_SILVER_EXACT_ROOT_BUDGETS=1`); g7f_E root table and
  root/tree prior; flexible keys; Wing Boots counter 1; `STS_ACTIVE_POWER_FEATURES=1`.

## Known risks, stated before the run
- **Scale.** X2-B is a win estimate with a mean near 0.5 on these leaves; gen 1b predicts the Heart kill (base rate
  about 0.12-0.25). Terminal leaves stay 0 (death) and 1 (Heart kill). B's Q values are therefore compressed and the
  prior weighs relatively more at the same cpuct (1.5). This is part of the intervention as asked, not corrected.
- **Learned OOC stop.** `ooc_learned_stop_trees.txt` was trained on X2-B-scale root Q values; its features include
  root Q gaps (`oocLearnedStopFeatures`). B's compressed Q changes those gaps, so B may stop at other points, which can
  move both win rate and CPU. Kept as is (the ask was to swap only the end value); per-arm search effort is reported.
  Alternatives for Philipp before the freeze: B with a rescaled value, or both arms with the learned stop off.
- **Act 1.** The §522 Heart-leaf A/B (`heart_leaf_td2`, a P(Heart) leaf on rollout3) was NOT_SHOWN with many more
  act-1 deaths (114 vs 69 of 512). Act-1 deaths are reported as a secondary.
- **Gen 1b's value head** passed its gate on a reused validation fold (§573) and memorises runs from epoch 2.

## Seeds, budget
- 512 fresh paired A20 seeds 111144000–111144511 (reserved for this thread: 111144000–111144999; smokes use
  111144990–999; 111144990–991 were used by the code smoke in `smoke/`). Gen 1b never trained on them.
- 32 workers × 4 parallel, 16 units each (worker count is Philipp's choice; units split as unit i → worker i mod W + 1).
  A unit is one seed, both arms in sequence, 7 h timeout per arm.
- Expected cost as the gen-1b A/B: about 2 × 512 × 1,967 s ≈ 560 core-h, plus B's value-head calls.

## Analysis (`analyze.py`)
- **Valid seed:** both arms rc 0, footer `complete` and `integrityPassed`, banner checks pass (rc 94 marks a missing or
  unexpected `leaf_heart1_value=` banner). Invalid seeds are reported, not replaced.
- **Primary:** Heart kills, B − A, paired: difference with 95% CI and exact McNemar p.
- **Secondary:** reached Act 4; act-1 deaths (final act 1); same statistics.
- **Descriptive:** search effort per arm on roots where the learned stop can act (not full-budget, not aborted):
  completed simulations per root and early-stop rate (`search_effort`); mean floor, wall time per arm (matched CPU), searched / full-budget / aborted roots, the fraction of
  searched roots where the search's choice differs from the prior's argmax.
- **Decision rule:**
  - **WIN:** McNemar p < 0.05 with B ahead on Heart kills and B's mean wall per run ≤ 1.10× A's. Then propose the
    value-head leaf for the AZ-loop search; Philipp decides. B ahead with p < 0.05 above 1.10× is
    **WIN_AT_HIGHER_CPU**, for Philipp.
  - **WORSE:** p < 0.05 with A ahead.
  - **NOT_SHOWN:** anything else; X2-B stays.
  - 512 pairs from a ~25% base detect roughly ±5 pp. Smaller effects read as NOT_SHOWN.

## Before launch
1. Freeze: RUN_COMMIT, code commit, binary sha256 into `campaign.manifest` (`__CODE_COMMIT__`, `__BINARY_SHA256__`,
   `__WORKERS__`) and the brief (`__RUN_COMMIT__`, `__AUTHORIZATION__`).
2. Smoke on the frozen binary: one seed from 111144990–999, both arms, rc 0, B's banner shows the value leaf.
3. Independent pre-launch review.

## Verification
`python3 tools/cloud/verify_campaign.py docs/experiments/evidence/az_gen1b_value_leaf_ab_20261020`. The lead releases
only the `OK:` workers.
