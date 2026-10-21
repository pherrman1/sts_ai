# AZ gen 2 vs student_sel: paired A20 A/B (pre-registration)

Prepared 2026-10-21 before any game of this campaign ran. Launch needs Philipp's typed go and worker count;
`__WORKERS__`, `__CODE_COMMIT__` and `__BINARY_SHA256__` are filled at freeze. Gen 2 comes from the offline sweep in
`../az_gen2_prior_sweep_20261021/PLAN.md`. Results are on data branch `claude/az-gen2-data` `6ae35b01`
(`gen2/sweep/results.md`). The pick is `S_d64L2_lr1e-4_a0.3_v0.3_s0`: student_sel fine-tuned at lr 1e-4, anchor 0.3,
value weight 0.3, with 32 value-only rows per run per epoch. Its selection-fold KL(π' ‖ net) is 0.0554, against 0.0654
for gen 1b and 0.103 for student_sel. Native parity was run on 400 records: max |Δ logit| 9.5e-6, 0 argmax
mismatches. The project rule: a new prior replaces student_sel only after a paired A20 A/B win at matched CPU.
Gen 1b also improved offline and came out NOT_SHOWN (§589), so the offline rank only filters candidates.

## Question
Does gen 2, used as the OOC prior and rollout net inside the AZ search stack, kill the Heart more often than
student_sel at A20?

## Arms (`run_unit.sh` is the source of truth)
- **A:** `STS_OOC_HEART1=student_sel.bin` (`cf6bf7fb…`).
- **B:** `STS_OOC_HEART1=gen2.bin` (`fc32d8f4…`, data branch `claude/az-gen2-data`
  `gen2/sweep/weights/S_d64L2_lr1e-4_a0.3_v0.3_s0/student.bin`).
- Nothing else differs. Both nets have the same size (d64, 2 layers), so CPU per call matches.
- Both arms use gen-1b A/B's stack (`../az_gen1_ab_20261020/run_unit.sh`) with two speed changes. Philipp decided
  both for future AZ-loop campaigns on 2026-10-21 at 09:58Z: "Okay let's do learned stop. And try a katago on 1024
  cap. No gain, just fix that".
  1. **Real combats use the learned Silver stop:**
     - `STS_SILVER_LEARNED_STOP=1`, `STS_SILVER_LEARNED_STOP_MODEL=gbt-0cac7cc64364`, `STS_SILVER_EXACT_ROOT_BUDGETS=1`.
     - `STS_OOC_MCTS_REAL_LEARNED_STOP` is left at main's default (on, ADR-0054). Gen 0 and gen 1b ran flat
       exact-10k.
  2. **Fast roots are capped:**
     - `STS_OOC_MCTS_FAST_ROOT_CAP=1024`: searched roots that are not full-budget run at most 1024 simulations.
     - The 25% full-budget roots keep 4096.
     - Banner `fast_root_cap=1024`, checked per arm (rc 94).
- Unchanged from gen 1b's A/B:
  - `heartoutcomegen 1 SEED OUT policy`;
  - OOC MCTS at 4096 sims, prior `heart1full`, TARGET_PRIOR=1, LEAF_SELECTS=heart1, rollout3 + X2-B public leaf;
  - learned OOC stop `ooc_learned_stop_trees.txt:0.99`, GAP_STOP=0, 25% full-budget roots, refusal pruning;
  - CTM rows on;
  - g7f_E rollout root table and root/tree prior (weight 400, from 8 visits);
  - flexible keys, `STS_OOC_HEART1_WING_BOOTS_COUNTER=1`, `STS_ACTIVE_POWER_FEATURES=1`, explicit engine fixes.
- Arm A is therefore not a replay of gen 1b's arm A. Both speed changes and main's parity fixes since 6e62cb64 apply
  to both arms equally.

## Seeds, budget
- 1,024 fresh paired A20 seeds, 111142888–111143911 (reserved by the coordinator 2026-10-21 16:24Z; the first draft's block 111148064–111149087 clashed with
  another thread's seeds). Gen 2 never trained on them: its rows came from
  111140712–111142887.
- 4 parallel per worker; a unit is one seed, both arms in sequence, with a 7 h timeout per arm.
- Expected cost: gen 1b's arms averaged ~1,480 s per run on flat 10k. The two speed changes are estimated at about
  −30% run CPU (speed profile, 2026-10-21). That gives 2 × 1,024 × ~1,050 s ≈ 600 core-h, about 5–6 h on 32 workers.
- **Pre-registered extension:** if the primary result is NOT_SHOWN with the Heart difference at ≥ +1.0 pp, run 1,024 more
  seeds, 111152128–111153151, under the identical frozen config. The analysis then pools all 2,048 seeds with the same
  rule. This single extension is the only interim look. No other stop or extension is allowed.

## Power (from gen 1b's A/B: 107 of 512 seeds discordant, 20.9%)
| paired seeds | 95% CI half-width | effect detected with 80% power |
|---|---|---|
| 1,024 | ±2.8 pp | ~4.0 pp |
| 2,048 | ±2.0 pp | ~2.8 pp |

## Analysis (`analyze.py`, unchanged from gen 1b's except the docstring)
- **Valid seed:** both arms rc 0, footer `complete` and `integrityPassed`, and all four banner checks pass. Invalid
  seeds are reported, not replaced.
- **Primary:** Heart kills, B − A, paired: difference with 95% CI and exact McNemar p.
- **Secondary:** reached Act 4, same statistics.
- **Descriptive:**
  - mean floor;
  - wall time per arm (the matched-CPU check);
  - searched / full-budget / aborted roots;
  - the fraction of searched roots where the search's choice differs from the prior's argmax.
- **Decision rule:**
  - **WIN:** McNemar p < 0.05 with B ahead on Heart kills, and B's mean wall per run ≤ 1.10× A's. Then propose gen 2 as
    the AZ-loop prior, and Philipp decides. B ahead with p < 0.05 but above 1.10× is **WIN_AT_HIGHER_CPU**, for
    Philipp to judge.
  - **WORSE:** p < 0.05 with A ahead.
  - **NOT_SHOWN:** anything else; student_sel stays. With the extension, the verdict comes from the pooled 2,048.
- B's capture rows are self-play data for gen 3 whatever the outcome. A's add to the student_sel pool.

## Scheduling
Static per-worker unit split, so a dead worker loses only its own units. The `schedule queue` mode
(#765) is not used, because of the claim race seen in the value-leaf A/B, unless a fix lands on main before the freeze.

## Freeze waits on the value-leaf A/B (`../az_gen1b_value_leaf_ab_20261020/`)
Philipp, 2026-10-21 13:43Z: gen 2's lead may depend on that campaign. The freeze happens after its verdict.
- **NOT_SHOWN or WORSE:** this A/B runs as written, with the X2-B leaf in both arms.
- **WIN:** both arms get the learned value leaf (`STS_OOC_MCTS_LEAF_HEART1_VALUE`).
  - Arm B uses gen 2's own head. Arm A uses gen 1b's head, since student_sel's value head is untrained.
  - The question is then explicitly whole-net: is gen 2, prior plus value head, better than the current loop net?
    Prior and leaf both differ between arms, so a gain cannot be split between them. That is the AZ-loop question,
    because a generation replaces the whole net.
  - The second candidate, `S_d64L2_lr1e-4_a1_v1_s0`, is added as a third arm only if Philipp asks. It has the best
    value head among the good-KL runs: value BCE 0.549 vs 0.559, policy KL 0.0591 vs 0.0554.
  - PREREG.md and run_unit.sh get updated, and Philipp confirms before launch.

## Verification
`python3 tools/cloud/verify_campaign.py docs/experiments/evidence/az_gen2_ab_20261021`. The lead releases only the
`OK:` workers.
