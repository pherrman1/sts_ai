# AZ gen 2: offline prior sweep and heart1 teacher route (written before training)

Requested by Philipp 2026-10-21 06:54Z ("Use my GPU for training") and 06:55Z (hyperparameter/architecture search for
the prior, more epochs; whether to keep training heart1 and distil smaller nets). Gen 1b (student_sel fine-tuned on
gen 0's π' targets) passed its offline gate but was NOT_SHOWN online (§589). This sweep is offline only; it picks at
most two candidates for one later paired A20 A/B, which needs Philipp's authorization and worker count.

## Data (fixed before any training)
- Rows from `tools/heart1/az_targets.py convert --beta 2.371373705661655` (β of §573, unchanged):
  - gen 0 search arm, 1,664 runs (`../az_gen1_20261020/rows.sha256`, list sha256 `472eb73e…`);
  - gen-1b A/B arm A (student_sel prior), 512 runs, files `az-SEED.capture.jsonl.gz`;
  - gen-1b A/B arm B (gen-1b prior), 512 runs, files renamed `az-b-SEED.capture.jsonl.gz`.
  Per-file sha256 in `rows.sha256` here (list sha256 `757a0623…`); data branch `claude/az-gen2-data` `67f510f`. Counts: policy rows 27,631 + 8,343 + 8,294; value rows 260,416 + 79,720 +
  80,607.
- B-arm π' builds on gen 1b's prior (the net that searched). **Inference:** still a valid improved-policy target for
  that state; the anchor term keeps the student near student_sel.
- Splits by run seed (both arms of a seed fall in the same fold): validation `seed % 8 == 7` (report only, never
  used to choose), selection `seed % 8 == 6` (`--select fold`), the rest trains.

## Stage S: direct student training (init student_sel, `--extra-inputs`, `--trim-map`, Wing Boots rows as captured)
- Base recipe = gen 1b (§573): d64, 2 layers, mult 4, heads 4, bs 256, lr 3e-4, value weight 1, anchor weight 1.
- Grid at d64/L2: lr {1e-4, 3e-4, 1e-3} × anchor weight {0, 0.3, 1, 3} × value weight {0.3, 1}; 20 epochs, epoch
  chosen on the selection fold. 24 runs.
- Architecture at the best grid point: d96/L2, d128/L2, d64/L3. student_sel's weights do not fit these sizes, so
  they start from random init with anchor weight 0 and are reported as a separate group. 3 runs. **Inference:**
  44k policy rows are few for a net trained from scratch; Stage T is the fairer test of a larger student.
- Seeds: torch seed 0; the best grid point and the best architecture are re-run with seeds 1 and 2 to show spread.

## Stage T: heart1 teacher route
1. Fine-tune heart1 (silverbot `heart1.pt`, sha256 `deaba59d…`, its own size) on the same rows with lr {1e-4, 3e-4},
   anchor to heart1, value weight 1, 20 epochs, `--select fold`.
2. Label every captured state that has a heart1 record (policy and value rows of all three sources) with the
   fine-tuned teacher's logits, plus the original student_sel distillation set if it is on the PC.
3. Distil a d64/L2 student (init student_sel) on teacher logits over those states, with value weight 1 on rows with z.

## Metrics and choice
- Per run: selection-fold objective, validation KL(π' ‖ net), top-1 vs π' argmax, value BCE / const BCE / AUC per act,
  anchor KL to student_sel, chosen epoch, wall time.
- Candidate rule: lowest selection-fold policy KL among runs whose selection-fold value BCE < const BCE. A size other
  than d64/L2 qualifies only if the native forward costs ≤ 1.10× student_sel per call (`oocmctsselftest`-style
  microbench on the cloud binary), the matched-CPU rule of the A/B. Teacher route wins if its distilled student beats
  the best Stage-S student on the selection fold.
- Reported last, never used to choose: validation-fold numbers of the pick, gen 1b and student_sel.
- Caveat carried forward: gen 1b improved validation KL by 30% and was NOT_SHOWN online, so offline rank is a filter,
  not evidence of strength.

## Execution
Philipp's GPU via Remote Control, in a scratch worktree made with `tools/agent/worktree.py`; the live parity canary's
checkout and the game install are not touched. Rows travel on the never-merged data branch `claude/az-gen2-data`;
weights, logs and `summary.json` per run come back on it. `STS_ACTIVE_POWER_FEATURES` does not apply (OOC net);
`STS_OOC_HEART1_WING_BOOTS_COUNTER=1` at capture, training and deploy as in gen 1.
