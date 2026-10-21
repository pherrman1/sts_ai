# AZ gen 2 offline prior sweep — results

Plan: `docs/experiments/evidence/az_gen2_prior_sweep_20261021/PLAN.md` on `claude/project-thread-3e3pyf` @ `41e3a2ac`.
Run on Philipp's PC (RTX 3060 Ti 8 GB, shared with the desktop and the live parity canary's game), 2026-10-21.

## Provenance
- Code: `41e3a2ac` + the local `tools/heart1/distill.py` changes in `tools/distill.py.patch` (full file
  `tools/distill.py`, sha256 `0f25037c…`; every run in the Stage S/T tables used this exact file, recorded in its `train.log`).
- Rows: `gen2/rows` on this branch @ `67f510f`, 2,688 files, verified against `gen2/rows.sha256` (list sha256 `757a0623…`).
  Folds by run seed: validation seed % 8 == 7 (56,882 rows), selection seed % 8 == 6 (57,873), train the rest (350,256 rows / 2,016 files).
- Init: `E_d64_sel_xin/student.pt` (student_sel; its export re-made here has sha256 `cf6bf7fb…` = expected).
  heart1: `heart1.pt` from the pinned release URL, sha256 `deaba59d…` verified. silverbot @ 84ab3ea (`~/h1distill/silverbot-84ab3ea`).
- Fixed flags (Stage S): `--extra-inputs --trim-map --select fold --device cuda --amp --bs 256 --epochs 20 --patience 3
  --pack --val-at-end --value-k 32 --threads 1 --workers 4 --cache`, torch seed 0, `STS_OOC_HEART1_WING_BOOTS_COUNTER=1`.
  Exact per-run args in each `runs/<group>/<name>/train.log`; drivers in `tools/`.

## Answer
- **Stage S pick (plan rule: lowest selection policy KL with selection value BCE < const): `S_d64L2_lr1e-4_a0.3_v0.3`** —
  selection policy KL 0.0554, validation KL 0.0542, top-1 0.933, selection value BCE 0.559 vs const 0.642.
  Seeds 1/2: 0.0553 / 0.0550 (spread ±0.0002). Export sha256 (s0) `fc32d8f4…`.
  For reference the gen-1b recipe (lr 3e-4 / a1 / v1) gets 0.0618 with K=32 and 0.0713–0.0733 on full data.
- Main effects (min / mean selection policy KL over the other two factors): lr 1e-4 0.0554/0.0590, 3e-4 0.0597/0.0622,
  1e-3 0.0745/0.0870; value weight 0.3 0.0554/0.0663, 1 0.0591/0.0724; anchor 0 0.0568/0.0735, 0.3 0.0554/0.0692,
  1 0.0558/0.0665, 3 0.0606/0.0684.
- Larger students from random init are far behind (d128/L2 0.191, d96/L2 0.225, d64/L3 0.239): too few policy rows.
- Value subsample vs full data: at the hot gen-1b recipe K=32 helps a lot (0.0618 vs 0.0713–0.0733), but at the winning
  lr 1e-4 / v0.3 the 7-point full-data side table is as good (a1/v0.3 0.0548, a0.3/v0.3 0.0553): K=32 does not change the pick.
- 40-epoch cap does not help (0.0567 at a 40-epoch OneCycle, stopped at epoch 15) → 20-epoch cap kept.
- heart1 fine-tune (T1) fits π' much worse than the student (selection KL 0.118), best value head of the day
  (selection BCE 0.546, AUC 0.768).
- **Teacher route loses.** T3 (d64/L2 from student_sel distilled on the fine-tuned teacher's logits + z) scores selection
  policy KL 0.0999 / validation KL 0.0956 on π' (`E_T3_on_gen2`) vs 0.0554 / 0.0542 for the Stage-S pick; its value
  head is on par (selection BCE 0.552 vs 0.559). Against its own teacher targets T3 reaches KL 0.041, so the
  distillation works — the teacher is just far from π'.
- **Candidates for a later A20 A/B: `S_d64L2_lr1e-4_a0.3_v0.3_s0` only** (no second qualifier: every other size fails
  the plan's d64/L2 rule or is far worse). Report-only validation fold: pick KL 0.0542 / top-1 0.933 / value BCE 0.526
  (const 0.622, AUC 0.758); gen 1b 0.0616 / 0.926 / 0.548 (AUC 0.729); student_sel 0.1010 / 0.935 / 0.689 (no value training).
- Caveat carried forward from PLAN: offline rank is a filter, not evidence of online strength (gen 1b improved
  validation KL 30% and was NOT_SHOWN online).

## Deviations from PLAN.md (all decided before the affected results were read)
1. Checkouts: standalone `git clone --shared` checkouts instead of `tools/agent/worktree.py` — current main commits
   `json`/`pybind11` as dangling symlinks to `/home/user/sts_ai/...`, so `worktree.py create` fails for any current-main start point.
2. Speed (07:01Z AZ thread): rows encoded once to a memory-mapped tensor cache (`--cache`); early stop after 3 epochs
   without a better selection objective (`--patience 3`, cap 20). Equivalence: 1-epoch losses/metrics identical to the original code.
3. `--pack` (drop padding to the batch's longest row; fp32 max |Δ| 7.6e-6 vs the fixed-size forward; native forward drops padding
   the same way) and `--val-at-end` (validation fold scored once at the chosen epoch; it is report-only). 2.2× faster per epoch.
4. **Value subsample `--value-k 32`** (Philipp, 08:41Z): each epoch trains on every row with a policy target plus 32 value-only
   rows per run (capture file), fresh each epoch (seed·100003+epoch). Chosen after the side test below; applies to Stage S and T1.
   The full-data grid was stopped after 7 points (kept below as a side table).
5. Grid point 1 of the original (unpacked) code was re-run under the final flags; its unpacked run is in the side table.
6. Architecture runs report anchor KL against student_sel via a new eval-only `--anchor-ref` (training unaffected).
7. Seed reruns: only the pick (d128/L2 seed reruns skipped, AZ thread 10:42Z: 3.5× worse, cannot change the choice).
   40-epoch cap check added (AZ thread 10:16Z).
8. Stage T: one heart1 fine-tune at lr 1e-4 only (lr 3e-4 dropped, AZ thread 07:20Z); heart1 trained untrimmed with zero-init
   `--extra-inputs`; uncached (`--compact`) with the same K=32 sampling (uncached path checked identical to the cached one).
   T3 (all rows carry teacher logits, so K has no effect) is scored on Stage S's π' folds by one lr-0 epoch (`E_T3_on_gen2`).
9. T3 data: the student_sel distillation set (128 files on this PC) was labeled too (2,630,411 rows in all), but it was
   captured before #638 (`wing_boots_counter` 0) while gen2 rows carry 1; `distill.py` refuses mixed sets and old records
   cannot be re-encoded, so T3 trains on the gen2 states only (all 465k rows carry teacher logits; z where present).
10. bs 1024 (+lr ×2) was benchmarked only: OOM unpacked (≈3.5 GB of GPU free), no speedup packed.
11. Not done here: the ≤1.10× native-cost microbench (no non-d64/L2 size qualifies anyway). Native parity: see "Native parity".

Columns: "sel" = selection fold (seed % 8 == 6), "val" = validation fold (seed % 8 == 7, report only). Objective =
policy KL + value weight × value BCE + anchor weight × anchor KL (so objectives are only comparable at equal weights).
