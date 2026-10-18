# Pre-registration: opening hand and first-Silver-search screens for the CTM (#460)

Written 2026-10-18 before any result was seen. Thread "CTM opening hand" (Philipp 01:24Z: "could you follow this
line?"; 01:31Z: "Do offline test. Also test ... replace distribution of HP by distribution of all roots at the start
of combat based on silver simulations"). Both screens are descriptive and change no default.

## Baseline and existing evidence

* OOC MCTS imagines every combat with the CTM (calibrated A20 stack `pathb-a20`, §470/ADR-0033), which conditions on
  the pre-combat state only: no shuffle, no opening hand (`ooc-label-pipeline.md` lists the hand as marginalized).
* The OOC tree's width at a combat chance node is `ceil(K·N^α)` particles (`OocMctsPlanner.cpp:160`), independent of
  the CTM's outcome space, so a hand latent would not widen it.
* Under the fair RNG regime the hand is drawn after the OOC decision. A calibrated hand-conditioned model, averaged
  over fair shuffles, has the same outcome distribution as a calibrated unconditional model. **Inference:** any OOC
  gain can only come from fit quality, not from new information.
* §408/§410: CTM vs low-sim Silver replays (A0): CTM HP RMSE 9.1-11.7 vs Silver prior256×4 8.5; Silver ~400× CPU.

## Screen A: opening hand (offline, no seeds)

* Data: the §443 Stage-4 A20 corpus (data branch `claude/ctm-a20-data` `ctm-a20-stage4/w01..w08`, the 80 `main-*`
  units, 76,316 rows). Victory and death rows with a valid run; escapes excluded.
* Hands: `one_combat ctmopeninghands ROWS OUT 16` rebuilds each fight's opening hand from the row's run seed, floor and
  pre-combat state (`BattleContext::init`), plus 16 fair resampled hands of the same deck under fresh seeds.
  Gate: on the smoke seed below, every reconstructed hand equals the hand recorded live with
  `STS_CTM_ROW_OPENING_HAND=1`.
* Models: XGBoost (400 trees, depth 6, lr 0.05), 5-fold CV grouped by source seed. A = CTM-like pre-combat features;
  B = A + opening-hand card counts. Targets: death (log loss), HP lost on wins (squared error).
* Scores: conditional (B with the realized hand) and marginal (B averaged over the 16 resampled hands) minus A, with a
  95% bootstrap CI over source seeds (`tools/ctm_opening_hand_screen.py`).
* Decision rule: if the marginal delta is negative with the CI excluding 0 for either target, the hand latent is worth
  a CTM schema bump and retrain proposal (`PROMISING`). Otherwise `NOT_SHOWN` for OOC use, and #460 is narrowed to
  places where the hand is visible. The conditional delta is reported as the hand's information content.

## Screen B: first Silver search as an outcome forecast

* Run: `combattransitiongen` at A20 on seeds 111195113-111195160 (48), with `STS_CTM_ROW_OPENING_HAND=1` and
  `STS_CTM_ROW_FIRST_SEARCH=1`. Combat = native Silver flat exact 10,000 sims per root, g6_E root prior (w400) and
  tree prior K=8, rollout root table (main default), learned stop off, fair. Out of combat = the deployed step with
  `STS_OOC_HEART1=student_sel.bin` (cf6bf7fb…) instead of OOC MCTS (CPU). Keys off. Smoke seed 111195112.
* Forecasters on the same realized fights: `ctm` (ctmscorerows, A20 stack), `silverRoot` (all simulations of the
  fight's first search), `silverBest` (simulations through the chosen root edge).
* Scores (`tools/silver_first_search_screen.py`): death Brier and log loss; on wins HP-lost bias and RMSE and the log
  score of the realized HP (Silver histograms add-0.5 smoothed). Silver is scored on battle-end HP (before heals), the
  CTM on RAW post HP (after heals). Paired deltas Silver minus CTM with seed-bootstrap CIs.
* Decision rule: descriptive. If a Silver layer beats the CTM on death Brier and HP log score with CIs excluding 0,
  report it as a candidate soft label for CTM training (its CPU rules it out as an online resolver: §411). Silver sees
  the opening hand; the CTM does not.
* Cost: 48 A20 runs at flat 10k Silver in this thread's container (4 cores); estimated from the smoke before launch.
  Seeds 111195161-111195171 stay unused.
