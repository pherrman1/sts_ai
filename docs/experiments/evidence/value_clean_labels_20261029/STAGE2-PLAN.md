# Stage 2: V_A4 = P(Heart kill | public state at Act-4 entry), offline (frozen before TEST is read, 2026-10-29)

Data: all complete, integrity-passed games whose log banner says "Act 4 strong" from the share campaigns
key-rules-ab, gumbel-qcap-ab, expert-anchored-ab, card-rule-ab (existing games, no seeds). Entry = first state row with act == 4.
Label = outcome.heartKilled. Split by seed % 4: TEST 3, VALIDATION 2, TRAIN 0/1 (paired arms share a seed, so share a split).
Features: public heart1 record via outcome_divergence_pairs_20261025/s0.py features() + hp fraction.
Models: G = XGBoost (depth/mcw grid on VALIDATION, early stop on VALIDATION, refit nothing); H = logistic on HP scalars;
C = deployed Act-4 CTM (models/candidates/ctm_act4_survival_trees.txt): (1 - pdeath(S&S input)) * (1 - pdeath(same input, heart=1)),
raw and logistic-recalibrated on TRAIN (C gets the S&S-entry input, i.e. after the Act-4 campfire: favours C);
GC = G with logit(C) as an extra feature.
Gate (TEST, opened once): BCE(G) < BCE(C_recal) with seed-bootstrap 95% CI of the difference below 0, and every decile of G
within +-3 pp of the observed rate or inside its binomial 95% CI. Pick G vs GC by VALIDATION BCE only.
