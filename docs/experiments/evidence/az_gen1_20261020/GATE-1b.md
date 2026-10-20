# AZ gen 1b: retrain with epoch selection on a held-out fold (written before training)

Gen 1 ([GATE.md](GATE.md), [result-gen1.json](result-gen1.json)) FAILED its gate on V. Policy passed: validation
KL to π' went from 0.0868 to 0.0568. The value head overfit: validation value BCE was best at epoch 2 (0.495, AUC
0.80) and rose each later epoch to 0.699, above the constant 0.639. `--select last` kept epoch 6. **Inference:** all
states of a run share one label, so 1,456 training runs give few independent value labels.

Only one thing changes: the epoch is chosen on a fold held out of training, not taken as the last one.

## Training

Same rows (`rows.sha256`), init, encoding and command as GATE.md, except `--select last` becomes `--select fold`.
With that, the files with seed % 8 == 6 (208 runs) leave training and form the selection fold. The kept epoch
minimises, on that fold, the training objective: policy KL + 1 × value BCE + 1 × anchor KL.

```
python3 tools/heart1/distill.py SILVERBOT_REPO OUT --data ROWS/az-*.capture.jsonl.gz \
  --init E_d64_sel_xin/student.pt --extra-inputs --dim 64 --layers 2 --mult 4 --heads 4 --trim-map \
  --lr 3e-4 --epochs 6 --bs 256 --value-weight 1 --anchor-weight 1 --select fold --amp --device cuda --workers 6
```

β stays 2.37, even though it was fitted on fold 6. It is one scalar, and that fit used only the search's own
checkpoints, never a trained net.

## Gate (unchanged; validation seeds seed % 8 == 7)

Read from `summary.json`: `history[0]` is student_sel; the gen-1b numbers are `best_val_kl` and `value` at
`selected_epoch`.
- **P:** gen-1b validation KL(π' ‖ net) < student_sel's (0.0868 in gen 1; re-read from this run's `history[0]`).
- **V:** gen-1b validation value BCE (all acts) < `const_bce`.
- **PASS** = P and V. Reported, not gated: top-1, value AUC and BCE per act, anchor KL, selected epoch.

Integrity check: `history[0]` must reproduce gen 1's init numbers (val KL 0.086767, top-1 0.946275), which shows the
init is the same student_sel. On PASS: export, native parity as in GATE.md, then a paired A20 A/B vs student_sel
(needs Philipp's go). On FAIL: ledger, no A/B.

**Caveat (to carry into the ledger):** gen 1b is a second gate attempt on the same validation fold. It was designed
after gen 1's validation curve had been seen, so a V pass is weaker evidence than a first-attempt pass. The paired
A20 A/B stays the deciding test.
