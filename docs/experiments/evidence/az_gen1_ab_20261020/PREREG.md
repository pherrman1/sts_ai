# AZ gen 1b vs student_sel: paired A20 A/B (pre-registration)

Authorized by Philipp, 2026-10-20 17:50Z: "Push it. Then do 512 seeds with 32 workers A/B". The proposal it answers is
in the gen-0 thread at 16:55Z. Gen 1b passed its offline gate with caveats (`../az_gen1_20261020/GATE-1b.md`,
`result-gen1b.json`, ledger §TBD on #732). The project rule: a new prior replaces student_sel only after a paired
A20 A/B win at matched CPU.

## Question
Does gen 1b, used as the OOC prior and rollout net inside the gen-0 search stack, kill the Heart more often than
student_sel at A20?

## Arms (`run_unit.sh` is the source of truth)
- **A:** `STS_OOC_HEART1=student_sel.bin` (`cf6bf7fb…`). This is gen 0's search arm.
- **B:** `STS_OOC_HEART1=gen1b.bin` (`e6aa044c…`, data branch `claude/az-gen1-data`).
- Nothing else differs. Both nets have the same size (d64, 2 layers), so CPU per call matches.
- Both arms, as gen 0's search arm:
  - `heartoutcomegen 1 SEED OUT policy`, OOC MCTS at 4096 sims, prior `heart1full`, TARGET_PRIOR=1,
    LEAF_SELECTS=heart1, rollout3 + X2-B public leaf.
  - Learned OOC stop `ooc_learned_stop_trees.txt:0.99`, GAP_STOP=0, 25% full-budget roots, refusal pruning, CTM rows on.
  - Real combats: flat exact-10k Silver, pinned as in gen 0. Main now defaults to the real-combat learned stop at
    A20 (ADR-0054), so the freeze sets `STS_OOC_MCTS_REAL_LEARNED_STOP=0`, `STS_SILVER_LEARNED_STOP=0` and
    `STS_SILVER_EXACT_ROOT_BUDGETS=1`, recorded in each arm's `.env`.
  - g7f_E rollout root table and root/tree prior (weight 400, from 8 visits).
  - Flexible keys, `STS_OOC_HEART1_WING_BOOTS_COUNTER=1`, `STS_ACTIVE_POWER_FEATURES=1`, explicit engine fixes.
- Code: main `6e62cb64` (merged into the run branch). Main's play-changing parity fixes since gen 0 (0abc831a) apply
  to both arms. So arm A is gen 0's search config on newer code, not a replay of gen 0.
- Open draft PRs #728, #729 and #733 (live-parity engine fixes) have not passed review, so the freeze excludes them.

## Seeds, budget
- 512 fresh paired A20 seeds, 111142376–111142887. Gen 1b never trained on them: its rows came from 111140712–111142375.
- 32 workers × 4 parallel, 16 units each. A unit is one seed, both arms in sequence, with a 7 h timeout per arm.
- Expected cost: gen-0 search arm mean 1,967 s, so 2 × 512 × 1,967 s ≈ 560 core-h. That is about 4.5–6 h on 32 workers.

## Analysis (`analyze.py`)
- **Valid seed:** both arms rc 0, footer `complete` and `integrityPassed`, both banner checks pass. Invalid seeds are
  reported, not replaced.
- **Primary:** Heart kills, B − A, paired: difference with 95% CI and exact McNemar p.
- **Secondary:** reached Act 4, same statistics.
- **Descriptive:**
  - mean floor;
  - wall time per arm (the matched-CPU check);
  - searched / full-budget / aborted roots;
  - the fraction of searched roots where the search's choice differs from the prior's argmax.
- **Decision rule:**
  - **WIN:** McNemar p < 0.05 with B ahead on Heart kills, and B's mean wall per run ≤ 1.10× A's (matched CPU; same
    container, same unit). Then propose gen 1b as the AZ-loop prior, and Philipp decides. B ahead with p < 0.05 but
    above 1.10× is **WIN_AT_HIGHER_CPU**, for Philipp to judge.
  - **WORSE:** p < 0.05 with A ahead.
  - **NOT_SHOWN:** anything else; student_sel stays.
  - At 512 pairs from a ~25% base, this detects roughly ±5 pp. Smaller effects read as NOT_SHOWN.
- B's capture rows are gen-1 self-play data whatever the outcome. A's add to the student_sel pool.

## Verification
`python3 tools/cloud/verify_campaign.py docs/experiments/evidence/az_gen1_ab_20261020`. The lead releases only the
`OK:` workers.
