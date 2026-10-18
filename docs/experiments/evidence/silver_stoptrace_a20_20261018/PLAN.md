# Learned-stop retrain, step 1: A20 stop traces on the current stack (plan, frozen with this folder)

Question (Philipp, 2026-10-18 19:17Z, gen-7 thread): "should we maybe also retrain the learned stopping? its been a
few silver iterations since we did that … after that, we will make it default maybe". Launch needs his typed
"go 8 workers". Code = main `code_commit` in `campaign.manifest` (after #671/#672/#674). Not a play test: no ledger
verdict is claimed from this step; the offline comparison below gets the next free ledger § with its result.

## Why
The compiled stop model `gbt-770201c31f7b` (ADR-0026, ledger §370/§372) was fitted on 160 A0 runs with the V4 OOC
stack, no keys, `STS_SILVER_EXACT_ROOT_BUDGETS=0`, and a Silver without the rollout card table (ADR-0040), the
rollout root table (ADR-0046/0049), the MLP root/tree prior and active power features. §538 used it on the
current A20 stack, where its search statistics were never seen in training.

## Collection (`run_unit.sh`, one arm `T`)
The §538 F10 configuration (A20 full runs, flat exact 10k, student_sel `policyStep` out of combat, g7f_E as rollout
root table and root prior weight 400 / tree prior K=8, `STS_ACTIVE_POWER_FEATURES=1`) plus `STS_SILVER_STOP_TRACE`,
which runs every checkpoint 250/500/1k/2k/4k/8k/10k of each multi-action root and writes the
`NativeSilverStopModel.h` features and the leader. 512 seeds 111198966-111199477, 8 workers, 4 units at a time,
2 h unit timeout. A unit is rc=97 if the root table did not load and rc=98 if it wrote no trace.
Smoke (seed 111199486, not part of the set): rc 0, 2,163 trace rows, 36 s.

## Offline comparison (step 2, after the tars are verified)
Seeds split by run seed: the first 384 train, the last 128 are held out (never used for fitting or threshold).
- Retrained model: the ADR-0026 recipe unchanged (`tools/silver_learned_stop.py train`, GBT v1 hyperparameters
  + trend features), fitted on the 384 training seeds; threshold chosen on the training seeds (5-fold by seed)
  so that its decision disagreement with the 10k leader equals the old model's on the same training seeds.
- On the 128 held-out seeds, both models are simulated with `silver_learned_stop_cv.simulate` (stop at the first
  strict lock or risk < threshold). Reported per model: simulation saving vs flat 10k and disagreement rate
  (stopped leader != 10k leader), with seed-cluster bootstrap 95% intervals of new − old.
- **Retrain worth a play test** if new − old saving > 0 with its interval excluding 0 while new − old
  disagreement's upper bound <= +0.25 pp; otherwise the old model stays and the line stops here.
Step 3 (only then): new model behind a selector, A20 A/B old vs new learned stop vs flat 10k, its own plan.
