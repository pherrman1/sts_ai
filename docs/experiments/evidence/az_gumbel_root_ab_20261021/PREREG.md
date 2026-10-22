# Gumbel sequential-halving root at OOC full-budget roots: paired A20 A/B (pre-registration)

Philipp, 2026-10-21 21:07Z: "Jo mach den gepaarten a/b mit 32 wirken nach gen2" (32 workers, launch after the gen-2
A/B). This answers the offline result §619: Gumbel SH with M = 16 at 2048 simulations agreed with a uniform
8192-simulation reference more often than PUCT at 4096. The regret is −6.3e-3 in reference Q, at half the root CPU.
That reference shares the leaf evaluator, and Q-based root selection lost twice in play (§414, §560). Only play can
decide.

## Question
At A20, with the current AZ search stack, do full-budget roots that run Gumbel SH (M = 16, 2048 simulations) kill the
Heart at least as often as PUCT at 4096, and at lower CPU?

## Arms (`run_unit.sh` is the source of truth)
- **A (control):** the gen-2 A/B arm A config (`../az_gen2_ab_20261021/run_unit.sh` on #774), with student_sel as the
  OOC prior and rollout net (`cf6bf7fb…`):
  - PUCT at every root;
  - full-budget roots run 4096 sims with stops off;
  - fast roots use the learned OOC stop 0.99 and the 1024 cap.
- **B:** A plus `STS_OOC_MCTS_GUMBEL_ROOT=16` (scale 1) and `STS_OOC_MCTS_FULL_ROOT_SIMS=2048`. On full-budget roots
  only, B samples 16 actions (all of them on nearly every root) by Gumbel + log prior and runs sequential halving over
  2048 simulations. It plays the best survivor by g + log prior + σ(normalised Q). Fast roots and every interior node
  are identical to A.
- Common config:
  - `heartoutcomegen 1 SEED OUT policy`, OOC MCTS 4096 sims, prior `heart1full`;
  - TARGET_PRIOR=1, LEAF_SELECTS=heart1, LEAF_POLICY=heart1, LEAF_VALUE=native (X2-B), LEAF_COMBATS=3;
  - 25% full-budget roots, refusal pruning, CTM rows;
  - real combats with the learned Silver stop (`STS_SILVER_LEARNED_STOP=1`, model gbt-0cac7cc64364,
    `STS_SILVER_EXACT_ROOT_BUDGETS=1`), boss-only prior playouts (`STS_SILVER_PRIOR_PLAYOUT_ELITE=0`);
  - g7f_E root table and root/tree prior, flexible keys, Wing Boots counter 1, `STS_ACTIVE_POWER_FEATURES=1`.
- **Prior after gen 2.** If the gen-2 A/B (`../az_gen2_ab_20261021`) ends WIN before launch and Philipp makes gen 2
  the loop prior, both arms switch `STS_OOC_HEART1` to gen2.bin (`fc32d8f4…`). That needs a re-smoke and a delta
  review, and it is recorded in the freeze.

## Known risks, stated before the run
- **Q selection.** B plays argmax of g + log prior + (50 + max N)·normalised Q. Normalised Q dominates the prior, so B
  plays close to argmax-Q among the survivors. Argmax-Q selection lost twice (§414, §560), and this is the main
  reason the offline win may not carry over.
- **Exploration noise in the played action.** The Gumbel draw makes B's choice stochastic per root (seeded per search).
  Full-budget roots are 25% of roots.
- **Training targets.** B's full-root visit counts follow the halving schedule, not PUCT. The ADR-0043 completed-Q
  target uses Q and visits, so B's capture rows are still valid targets, but their visit shape differs from gen 0-2's.

## Seeds, budget
- 512 fresh paired A20 seeds 111153152–111153663, from the free block 111152128–153899 after gen 2's extension
  (152128–153151). Smokes use 111145018–019 from the speed-profile block.
- 32 workers × 4 parallel (Philipp's count). `schedule queue` (#765 + #773 claim fix), lease 30 min. A unit is one
  seed, both arms in sequence, 7 h timeout per arm.
- Expected cost: combined-stack runs took ~600–1,060 s CPU (`az-speed-profile/REPORT.md` 14:30Z) before #789 (−20–30%). B saves about half
  the full-root CPU, ~25–30% of a run. Estimate: ~2 × 512 × 800 s ≈ 230 core-h, ~2–3 h on 32 × 4 (not measured).

## Analysis (`analyze.py`)
- **Valid seed:** both arms rc 0, footer `complete` and `integrityPassed`, banner checks pass. rc 93 marks a wrong
  `gumbel_root` / `full_root_sims` banner: B must show both, A neither. Invalid seeds are reported, not replaced.
- **Primary:** Heart kills, B − A, paired: difference with 95% CI and exact McNemar p.
- **Secondary:** reached Act 4, same statistics.
- **Descriptive:** mean floor; wall per arm; searched / full-budget / aborted roots; the fraction of searched roots
  where the played action differs from the prior's argmax.
- **Decision rule:**
  - **WIN:** McNemar p < 0.05 with B ahead on Heart kills and B's mean wall ≤ 1.10× A's. Propose the Gumbel root as
    the AZ-loop default; Philipp decides.
  - **WORSE:** p < 0.05 with A ahead.
  - **NON_INFERIOR:** neither of the above, the Heart-kill CI lower bound > −5 pp, and B's mean wall < A's. Propose it
    for the speed gain; Philipp decides. The −5 pp margin is the §564 convention.
  - **NOT_SHOWN:** anything else. PUCT stays.
  - 512 pairs from a ~23% base give a CI of about ±4 pp, so effects smaller than that read as NON_INFERIOR or
    NOT_SHOWN.
- Both arms' capture rows join the gen-3 self-play pool whatever the outcome.

## Before launch
1. Freeze: code commit, binary sha256 and preset into `campaign.manifest`; RUN_COMMIT and authorization into the brief.
2. Smoke on the frozen binary: one seed from 111145018–019, both arms rc 0, banner checks pass.
3. Independent pre-launch review (code: `STS_OOC_MCTS_FULL_ROOT_SIMS`, plus this campaign).

## Verification
`python3 tools/cloud/verify_campaign.py docs/experiments/evidence/az_gumbel_root_ab_20261021`. The lead releases only
the `OK:` workers.

## Freeze (2026-10-21)
- Authorization: Philipp 2026-10-21 21:07Z "Jo mach den gepaarten a/b mit 32 wirken nach gen2" (32 workers, launch
  after the gen-2 A/B releases its workers).
- Code: main `b0a8f5962ec8cd5d1d27ec070ebf90b4b2337797` (#791 `STS_OOC_MCTS_FULL_ROOT_SIMS`, review PASS B).
  Since the gen-2 A/B freeze (`844bd923`), main also has #782 (Gumbel root, §619), #789 (engine speed,
  bit-identical) and #790 (`STS_CORRUPTION_HAND_COST_FIX`, default-on play change, §620). Both arms carry #790, so the
  contrast is unchanged, but absolute numbers are not comparable to gen 2's A/B.
- Preset `linux-gcc-release-x86-64-v3`; binary `one_combat` sha256
  `be70a1c19056c48a32cc00e86240c0f2956c8904c9f2b13d947221d49d0e616b`, published to the bin-cache.
- Prior: student_sel in both arms (gen-2 A/B not finished at freeze).
- Workers: 32. RUN_COMMIT = the commit that adds this record.
