# AZ gen 1: student_sel fine-tune on gen-0 search targets — offline gate (written before training)

Philipp, 2026-10-20 15:46Z and 15:53Z ("Let's gooo", "Let's go") after the trainer defaults were posted in the
gen-0 thread.

## Inputs

- Gen-0 data: data branch `claude/az-gen0-data` 54033d1 (32 verified tars, 1,664 A20 runs, ledger §569).
- Rows: `tools/heart1/az_targets.py convert --beta 2.371373705661655 ROWS w*.tar` on this commit.
  Byte-identical on reruns; per-file sha256 in `rows.sha256` (sha256 of that list `472eb73e…`). Counts in
  `convert.json`: 27,631 policy rows (searched, non-singleton, full-budget roots), 260,416 value-only rows, 441
  full-budget roots dropped for < 2 covered tokens, 206 of 27,631 policy mass dropped on token-less candidates
  (potion discard).
- σ: `fit-sigma` on seed % 8 == 6 (a training fold), 3,356 full-budget roots, label = the 4,096-sim search's
  selected action, π' from the 2,048-sim checkpoint (`sigma_fit.json`). Best constant β = 2.37: NLL 0.374, top-1
  0.921, prior alone NLL 0.437, top-1 0.911. β was also 2.37 at the 512- and 1,024-sim checkpoints. The paper's
  visit-scaled form fit a scale that fell about as 1/visits from 128 to 2,048 sims, so it is not used.
- Init: `student_sel` torch weights (`E_d64_sel_xin/student.pt`, the source of `student_sel.bin` `cf6bf7fb…`).
- Encoding: every row has `wing_boots_counter` 1, so the gen-1 net deploys only with
  `STS_OOC_HEART1_WING_BOOTS_COUNTER=1` (as gen 0 ran). `--extra-inputs` keeps `x_deck_misc`, `x_relic_counter`
  and `x_act`.

## Training (one run, no tuning against the gate split)

```
python3 tools/heart1/distill.py SILVERBOT_REPO OUT --data ROWS/az-*.capture.jsonl.gz \
  --init E_d64_sel_xin/student.pt --extra-inputs --dim 64 --layers 2 --mult 4 --heads 4 --trim-map \
  --lr 3e-4 --epochs 6 --bs 256 --value-weight 1 --anchor-weight 1 --select last --amp --device cuda --workers 6
```

Loss: KL(π' ‖ student) over the tokens the search covered + 1 × value BCE on z (Heart killed) + 1 ×
KL(student_sel ‖ student) over all choice tokens. `--select last`: the validation split is not used for selection.

## Gate (validation split: seeds with seed % 8 == 7, 3,369 policy rows, 35,432 value rows)

Read from `summary.json` (`history[0]` = student_sel at init, final epoch = gen 1):

- **P (policy):** gen-1 validation KL(π' ‖ net) < student_sel's.
- **V (value):** gen-1 validation value BCE (all acts) < the constant base-rate BCE (`const_bce`).
- **PASS** = P and V. Reported, not gated: top-1 agreement with π', value AUC and BCE per act, anchor KL.

On PASS: export with `export_heart1_weights.py --allow-other-checkpoint --n-heads 4 --trim-map`, native parity
(`student_inputs.py score` vs `one_combat heart1score`, max |Δ logit| ≤ 1e-4 on ≥ 300 records), then propose a
paired A20 A/B vs student_sel (needs Philipp's go). On FAIL: no export; the result goes to the ledger.
