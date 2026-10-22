# Value head: counterfactual teacher-delta distillation (pre-registered 2026-10-21 ~21:45Z)

Question: can the value head learn raw heart1's clean HP / max HP / gold slopes without losing T1-level accuracy?
Baseline: VDF_T1_alpha1_v0.5 (sel BCE 0.542, KL 0.0593, AUC 0.765); its probes: curHP wrong-sign ~23%, maxHP+5-only
wrong 73.6%, gold+50 wrong 19.5%. Raw heart1 (teacher of the deltas): 12% / 10% / 9%. #777 hinge (M0.3, z recipe)
flattened the head and failed the prices gate.

Intervention (one variable): add a loss on value-logit *differences*. Each batch picks one rule (hp, mhp, gold; round
robin) and random deltas (monotone.py perturb: heal/lose 1-10 HP, +1-10 max HP, +1-100 gold) on 64 rows; target delta =
1.3587 (raw heart1 calibration slope) x raw heart1's delta; loss = sum((ds - dt)^2) / sum(dt^2) (1 = flat student).
Forwards for the deltas run fp32 with TF32 off. Teacher sees the trimmed map (it was trained untrimmed; deltas only).
Everything else = VDF_T1 v0.5 recipe (seed 0, init student_sel, rows_T1, value weight 0.5, alpha 1, no K).
Code: tools/distill.py (patch on gen2/value-targets/tools/distill.py) + monotone.py from main (#777). Default off.

Runs: CF_base (control, report only; must reproduce sel BCE 0.542 +-0.002), CF_w0.3, CF_w1, CF_w3, M0.3 (hinge
on this recipe). All report fixed-delta CF agreement + mono violations (fp32) on sel and val folds.

Gate for a CF run (selection fold): value BCE <= 0.545 and policy KL <= 0.0600; sign agreement with raw heart1 >= 85%
for each of hp (-3), mhp (+5), gold (+50); mono violation mhp <= 30%, gold <= 15%, hp <= 15%. Then (cloud) prices.py:
maxHP+5 price > 0 for >= 90% and -3 HP sign right >= 95% (#777 gate); sibling concordance reported (no bar; X2-B 0.633).
Pick: lowest sel BCE among passing runs. Outcome PASS -> export + native parity, combine with the two-net idea later
(online test needs Philipp's go). FAIL -> ledger negative result.
Cost: ~5 x 35-60 min on Philipp's GPU (~4 h), no gameplay seeds.
