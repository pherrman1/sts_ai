# Card-reward rule screen at A20: student_sel vs value head vs uniform search (pre-registration)

Written 2026-10-26 before any campaign game ran. Origin: Philipp's card-reward depth questions in the project thread
"Measure OOC MCTS depth on card rewards" (2026-10-25/26). Philipp, 2026-10-26 22:21Z: "mach a vs b vs c vs d auf 256
seeds. die frage ist wie wir die suche gestalten, i.e. welche paramter bekommt sie". The search parameters below are
the ones proposed in the thread at 22:3xZ; the launch still needs Philipp's typed go and worker count.

## Background (single-seed diagnostics, seed 111379970, not ledger evidence)
- The production tree on a card-reward root reaches ~1 floor (next combat is a chance node with ~2,000 particles);
  student_sel puts >= 0.97 prior on one option in 13/15 roots, so the other options get 1-3 visits and their Q is
  noise. Any comparison of card evaluators therefore needs a root that does not follow the prior.
- With 8192 simulations split evenly over the options, Q noise between widening variants was ~0.005; option gaps were
  0.01-0.03.
- Evaluated directly on the post-pick state, X2-B (M0) separates options by 0.037 on average and prefers Skip in 5/13
  roots; SR_crn_r2_s2_ep20 separates by 0.162 and agrees with the student_sel pick in 11/13. There is no ground truth
  in these diagnostics; this screen supplies it (real games).

## Arms (`run_unit.sh` is the source of truth)
Every arm is today's A20 default (main db216ff0 + this PR's research flag): map-only OOC search at full budget for
map roots (ADR-0061), student_sel tree prior and rollout policy (`cf6bf7fb…`), rollout3 + X2-B leaf with M0
calibration (ADR-0057), learned OOC stop 0.99, fast-root cap 1024, 25% full-budget fraction, learned Silver stop with
exact root budgets for real combats, Act-4 strong (ADR-0060, unset = on), g7f_E root table and prior, boss-only prior
playouts, keys on, default CTM (§679). The arms differ only in who decides a real root on a card-reward screen
(`REWARDS` with a card reward, after the rule chain):
- **A (control):** today's default, student_sel decides (`by=heart1_screen`).
- **B (value):** `STS_OOC_MCTS_CARD_RULE=value` with `STS_OOC_MCTS_CARD_RULE_HEART1_VALUE=sr_value.bin`
  (SR_crn_r2_s2_ep20, sha256 `28523fb5…`, data branch `claude/az-gen2-data` gen2/value-sr-crn/weights): each root
  action's successor state is valued by the head alone (sigmoid of the value logit, no calibration, X2-B where heart1
  cannot encode the state); argmax. No rollout, no search.
- **C (search, X2-B):** `STS_OOC_MCTS_CARD_RULE=search`, `..._SIMS=8192`, `..._BOSS_EDGE=1`: 8192 simulations split
  evenly over every root action (uniform Gumbel root, no early, gap or learned stop, no root noise); below the root the
  live tree (student_sel PUCT prior, cpuct 1.5, widening K=4 alpha 0.75, tree rules, merged outcomes); rollout3 + X2-B
  (M0) leaf; the map step into the act boss is a tree edge instead of a leaf boundary; play the action with the best
  mean Q.
- **D (search, SR leaf):** as C with `STS_OOC_MCTS_CARD_RULE_HEART1_VALUE=sr_value.bin`: the rollout-end anchor is the
  SR head alone (no M0) in these roots only.

Decisions by the card rule record `by=card_rule`; with the policy capture they keep the root row (candidates,
priors, visits, Q, selected key).

## Seeds and scale
- Campaign: **111387000-111387255** (256 seeds, free block 111381000-111389989 of the seed ledger; repo seed guard
  clean). One unit = one seed with A, B, C, D in sequence (order rotated by seed % 4) on one lane.
- Smokes: 111387990-111387999 (111387990 used for the pre-launch smoke).
- Cost: see SMOKE.md (per-arm wall on the smoke seed); estimate A, B ~550 s, C, D ~850 s per game -> ~200 core-hours.

## Endpoints
- **Primary:** Heart kills, B - A, C - A, D - A, paired: exact discordance counts (exact McNemar p), 95% seed
  bootstrap CI of the paired difference.
- **Secondary:** Act-4 arrival for the same contrasts; D - B (does search add to the head), D - C (leaf); kills per
  Act-4 arrival; mean final floor; deaths by act.
- **Mechanism:** first-divergence attribution per contrast (as #854); per rule arm: card_rule roots, share of picks
  off the student_sel argmax, skip count.
- **Cost:** mean wall per arm and ratios.

## Decision rule (frozen)
This is a screen of 256 seeds (paired resolution roughly +-5 pp on Heart kills); it cannot show an effect, only rank
the arms. Per arm X in {B, C, D} on Heart kills X - A:
- **PROMISING:** diff >= +2.0 pp. Follow-up proposal: extend that arm (and A) to 1,024 seeds (needs Philipp's go).
- **STOP:** diff <= 0. No follow-up for that arm.
- **INCONCLUSIVE** otherwise; reported, Philipp decides.
No default changes from this screen.

## Known limitations
- 256 seeds; arms share seeds, so the four contrasts are correlated.
- B and D use one value head (SR_crn_r2_s2_ep20) whose offline sibling ranking was only marginally above X2-B
  (0.667 vs 0.664, §649) and whose training data were on-policy; agreement with student_sel is expected.
- C and D cost more CPU than A; a default change would need the matched-CPU AZ-loop rule.
- The SR head is uncalibrated against death (0) and kill (1) terminals inside the rollout; C uses M0 for that.
