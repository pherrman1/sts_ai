# OOC self-play / expert-iteration loop: prior work and a design (2026-10-09)

Read-only analysis against main `fec0ce0b`. No seeds were run. Every claim cites the ledger
(`docs/experiments/ledger-0*.md`) or an issue; lines marked **Inference** are mine.

## 1. What already exists

| Piece | What it was trained on | Ledger / issue |
|---|---|---|
| Outcome-labelled self-play loop (2026-07) | `selfplay/loop.sh`: play N runs, label states with run victory, retrain a unified V_win (P(win \| state)) + combat value/policy, paired gate, promote. Ran ~9 iterations, 500-2,000 runs each, at a much weaker agent (20-30% wins). | §37-§52 (ledger-02) |
| Its verdict for OOC | Unified V_win as card/shop scorer: card-only −7.8 score [−12.6, −3.0], shop-only −4.6 [−7.6, −1.6] vs control; "learning card/shop later needs action-value/ranking targets or randomized counterfactual coverage, not more iterations of the same state classifier". | §50 |
| V4 prior (`ooc_strategic_tok_final`) | Token net; policy head on the behaviour policy's `chosen` action, value/Q heads on Tier-B `labelWon` (strategicgen2: heuristic OOC main run + 1-3 fight branch continuations, bootstrapped). Not trained on MCTS visits and not on its own play. | ledger-03 (V4 rungs), §149 |
| Soft search-distillation targets | softmax(labelWon/τ) policy targets: falsified on gate. | §104 |
| Label-noise wave | futures=2, de-quantisation, trainer denoising: all null; "the one-ply label ranking itself is the ceiling". The iterative play→search→train loop (5.7.3) was named as the remaining option. | §105 |
| Relabel with the current controller | 1,500 fresh seeds (801k rows), V4 recipe retrained: −10.2 pp [−17.6, −2.7]. Closed as a distribution lever. | §141, §142 |
| X2-B (current `v_win`, leaf input) | XGBoost on #334: 1,024 source games of the frozen V4 + exact-10k Silver policy, plus 14,632 deferred sibling branches played to the end; MAP rows labelled with `finalWon` (TRAIN 333k / VAL 69k rows). This **is** a leaf trained on run victory of our own play. Data scale still helps NLL: half→full TRAIN 0.4729→0.4445 (`DATA_SCALE_SIGNAL`). | #334, §368, §374, §379 |
| Screen GBM leaf (default leaf) | Residual on X2-B margin with screen features, same #334 corpus; "near its ceiling, fresh on-policy data is #415". | §383, ADR-0027, #415 (open) |
| Counterfactual card labels | E3 (1,000 seeds, branch futures per option): card rewards NEGATIVE, even a random card pick ties V4; boss relics F2 ≈ V4, X2-B −4.8 pp. F2 as live leaf −13.3 pp. | §396, §401 |
| Model-free outcome leaf in search | `bossrollout`: uniform prior, 1/0 for beating the next boss in a V4+CTM rollout: 9/32 (28%) vs rollout3 25/32. | §391 |
| Uniform prior | 4 R seeds: uniform beats V4 prior +13/32 (inconclusive); fresh 32-seed pilot uniform prior + rules: 18/32 (56%) vs flat10k 78% context. | §392, §393 |
| Visit distillation of OOC MCTS | Never done for OOC (only for the combat policy in §38-§52). Planned as #399, deliberately deferred until a better leaf exists. | #399 (open) |

**So:** the "leaf from run victory" half has been done twice (V_win loop, X2-B) and is not new.
What has never been done is the closed loop with an MCTS teacher whose visit counts train the prior.

## 2. How the recent evidence bears on it

- §411 (128 seeds): OOC MCTS + prod CTM 75.8%, + Silver resolver 78.9%, MCTS off 78.1%. No MCTS arm beats off,
  and a perfect-ish combat resolver adds nothing. The combat model is not the bottleneck.
- Q-select screen (65M, done 18:40Z): picking the root by Q is −37.5 pp; Q arms skip 34% of card rewards and take
  Neow MaxHP 71%. The leaf is biased and the V4 prior is what keeps play sane.
- **Consequence for "start uniform":** a uniform prior hands the root decision to that biased leaf (§393: 56%).
  Expert iteration needs the search teacher to be stronger than the policy it replaces. Iteration 0's visit
  distributions would distil the leaf's bias (skip cards, MaxHP Neow) into the new prior. **Inference:** start
  from the V4 prior, not uniform.
- Headroom: §396 says card choice at A0 barely moves P(win) (random ties V4). With an ~80% base rate, a binary run
  label carries little information about any single OOC choice (see §3). The real A0 headroom is the ~20% boss
  deaths. A20 has more headroom but the prod CTM is broken at A20 (card-strength probe finding), so an A20 loop
  must wait for #468's stack and a check that it supports ASC 20.
- §384/§401/§396: every learned leaf so far fails to rank the choices that matter; more on-policy data is the one
  lever the #334 line has not pulled (#415).

## 3. Label noise, data and cost arithmetic

- Win label Bernoulli, p ≈ 0.78 → variance 0.17. Root Q gaps between top actions are 0.01-0.03 (card-eval analysis).
  Resolving a 0.02 win-probability difference between two actions from independent outcomes at 2σ needs about
  n ≈ 2·(2)²·0.17/0.02² ≈ 3,400 runs **per arm of one contrast**. A GBM pools across states, but each run gives
  one bit shared by ~50 OOC decisions. #334 (1,024 games + 14.6k paired branches, far more efficient than
  on-policy runs) still could not price cards. **Inference:** a few thousand on-policy games will improve NLL
  (DATA_SCALE_SIGNAL) but may not fix ranking.
- CPU per run (A0): MCTS-off run ≈ 62 CPU s (§406 plain 10k); prod OOC MCTS adds 45 s (§411) → ≈ 110 CPU s per
  self-play game. 1,024 games ≈ 31 CPU-h ≈ 16 workers × 4 cores for ~30 min plus build (fits the 32-worker
  Q-screen experience). 10k games ≈ 300 CPU-h.

## 4. Recommendation

Do not start the full loop yet. First resolve the main uncertainty for free: **does the outcome-trained leaf's
decision quality improve with more own-play games at all?**

### Step 0 (no seeds, offline, ~1-2 CPU-h)
Learning curve on existing outcome-labelled data: retrain the frozen X2-B recipe (5 XGBoost seeds) on 1/8, 1/4,
1/2, 1/1 of the #334 TRAIN **sources** (whole trajectories with their branches, source-clustered). Evaluate on the
frozen splits:
1. VALIDATION MAP NLL;
2. E3 counterfactual selection gain for card rewards and boss relics (§396 metric, frozen E3 VALIDATION rows);
3. bias: share of card-reward states where the model prefers skip, and Neow MaxHP preference (Q-screen symptom).

Data: the full #334 corpus is on Philipp's machine (`~/Documents/sts/artifacts/vwin-refresh-334/`), cloud returns
partly in `/mnt/project-files/vwin334-cloud-returns/`, E3 in `/mnt/project-files/ooc-cf-pilot/`. Tooling exists
(`tools.vwin_e1_focal`, E3 analysis).

Pre-registered rule (per doubling, slope from 1/2 → 1/1, source-clustered bootstrap, 10,000 draws):
- `GO`: pooled selection gain improves by ≥ +0.005 with CI lower > 0, **and** skip preference falls.
- `STOP`: pooled gain CI upper < +0.005, or skip preference flat/rising. Record as a ledger negative:
  outcome labels from own play are not the limiting resource for ranking at this scale; the loop is shelved.
- else `INCONCLUSIVE` → extrapolate, ask Philipp.

### Iteration 0 (only on GO and Philipp's word; after #468 merges)
- Teacher: prod OOC MCTS (V4 prior, screengbm leaf, 2048 sims, new CTM stack, exact-10k live Silver), A0.
- Play 1,024 games, seeds 66000000-66001023 (smoke 66009000). Capture per root: rich state, screen contents,
  candidate keys, visit counts, Q, chosen action; per run `finalWon`. Needs a small capture change (#415 sinks
  under live MCTS; the `vwinrefreshgen` frozen-policy guard rejects MCTS today).
- Train, one variable at a time: (a) leaf = X2-B recipe (GBM) on #334 + new games; prior unchanged.
  (b) later iteration: GBM prior student on visit distributions (#399), only once the leaf has passed.
- Gate: 256 paired seeds 66100000-66100255, arms `off`, `prod`, `cand-leaf`. Cost ≈ 3 × 256 × ~100 s ≈ 21 CPU-h.
- Rule: `CONTINUE` to iteration 1 if cand − prod ≥ 0 pp with 95% CI lower > −4 pp and offline skip bias below
  prod's; `STOP` if cand − prod CI upper < 0 or point < −2 pp. Nothing is promoted unless it also beats `off`.
- Total iteration 0 ≈ 31 + 21 ≈ 52 CPU-h (~1 h wall on 16 × 4-core workers).
