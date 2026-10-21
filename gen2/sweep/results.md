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
11. Not done here: native-forward parity of the exported students (needs the one_combat build; gen 1 did it on the cloud binary)
    and the ≤1.10× native-cost microbench (no non-d64/L2 size qualifies anyway).

Columns: "sel" = selection fold (seed % 8 == 6), "val" = validation fold (seed % 8 == 7, report only). Objective =
policy KL + value weight × value BCE + anchor weight × anchor KL (so objectives are only comparable at equal weights).

## Stage S grid (K=32, pack, val-at-end, patience 3, cap 20; init student_sel; seed 0), sorted by selection policy KL

| run | chosen / run ep | sel objective | sel policy KL | sel value BCE / const / AUC | val KL to π' | val top-1 | val value BCE / const / AUC | val BCE·const·AUC per act (1 / 2 / 3 / 4) | anchor KL sel / val | wall min |
|---|---|---|---|---|---|---|---|---|---|---|
| S_d64L2_lr1e-4_a0.3_v0.3_s0 | 17 / 20 | 0.2269 | 0.0554 | 0.5590 / 0.6420 / 0.740 | 0.0542 | 0.9333 | 0.5255 / 0.6216 / 0.758 | 0.554·0.559·0.615 / 0.497·0.606·0.788 / 0.519·0.676·0.819 / 0.525·0.679·0.804 | 0.0125 / 0.0125 | 7.6 |
| S_d64L2_lr1e-4_a1_v0.3_s0 | 17 / 20 | 0.2318 | 0.0558 | 0.5616 / 0.6420 / 0.737 | 0.0536 | 0.9365 | 0.5299 / 0.6216 / 0.752 | 0.553·0.559·0.615 / 0.503·0.606·0.781 / 0.528·0.676·0.812 / 0.530·0.679·0.803 | 0.0075 / 0.0075 | 7.5 |
| S_d64L2_lr1e-4_a0_v0.3_s0 | 12 / 15 | 0.2253 | 0.0568 | 0.5616 / 0.6420 / 0.736 | 0.0555 | 0.9315 | 0.5331 / 0.6216 / 0.747 | 0.553·0.559·0.611 / 0.507·0.606·0.775 / 0.535·0.676·0.805 / 0.536·0.679·0.800 | 0.0173 / 0.0173 | 4.8 |
| S_d64L2_lr1e-4_a1_v1_s0 | 9 / 12 | 0.6182 | 0.0591 | 0.5487 / 0.6420 / 0.754 | 0.0561 | 0.9324 | 0.5179 / 0.6216 / 0.772 | 0.556·0.559·0.618 / 0.483·0.606·0.805 / 0.501·0.676·0.828 / 0.522·0.679·0.810 | 0.0104 / 0.0103 | 4.6 |
| S_d64L2_lr1e-4_a0.3_v1_s0 | 9 / 12 | 0.6139 | 0.0596 | 0.5496 / 0.6420 / 0.755 | 0.0569 | 0.9313 | 0.5180 / 0.6216 / 0.772 | 0.556·0.559·0.619 / 0.482·0.606·0.806 / 0.502·0.676·0.828 / 0.526·0.679·0.810 | 0.0157 / 0.0156 | 4.6 |
| S_d64L2_lr3e-4_a1_v0.3_s0 | 8 / 11 | 0.2365 | 0.0597 | 0.5542 / 0.6420 / 0.756 | 0.0556 | 0.9307 | 0.5178 / 0.6216 / 0.775 | 0.558·0.559·0.622 / 0.478·0.606·0.810 / 0.504·0.676·0.830 / 0.531·0.679·0.806 | 0.0105 / 0.0106 | 4.3 |
| S_d64L2_lr1e-4_a3_v0.3_s0 | 20 / 20 | 0.2422 | 0.0606 | 0.5705 / 0.6420 / 0.728 | 0.0569 | 0.9372 | 0.5420 / 0.6216 / 0.736 | 0.556·0.559·0.609 / 0.517·0.606·0.765 / 0.551·0.676·0.794 / 0.551·0.679·0.796 | 0.0035 / 0.0035 | 7.6 |
| S_d64L2_lr3e-4_a0.3_v0.3_s0 | 8 / 11 | 0.2334 | 0.0609 | 0.5581 / 0.6420 / 0.756 | 0.0580 | 0.9296 | 0.5180 / 0.6216 / 0.777 | 0.559·0.559·0.625 / 0.476·0.606·0.811 / 0.506·0.676·0.830 / 0.531·0.679·0.807 | 0.0168 / 0.0169 | 4.3 |
| S_d64L2_lr3e-4_a3_v0.3_s0 | 9 / 12 | 0.2432 | 0.0615 | 0.5498 / 0.6420 / 0.752 | 0.0572 | 0.9348 | 0.5179 / 0.6216 / 0.771 | 0.552·0.559·0.622 / 0.484·0.606·0.802 / 0.506·0.676·0.826 / 0.523·0.679·0.806 | 0.0056 / 0.0056 | 4.6 |
| S_d64L2_lr3e-4_a1_v1_s0 | 3 / 6 | 0.6393 | 0.0618 | 0.5643 / 0.6420 / 0.742 | 0.0586 | 0.9280 | 0.5323 / 0.6216 / 0.756 | 0.562·0.559·0.603 / 0.496·0.606·0.790 / 0.531·0.676·0.807 / 0.549·0.679·0.797 | 0.0132 / 0.0133 | 2.4 |
| S_d64L2_lr1e-4_a0_v1_s0 | 9 / 12 | 0.6120 | 0.0618 | 0.5502 / 0.6420 / 0.755 | 0.0590 | 0.9300 | 0.5183 / 0.6216 / 0.772 | 0.556·0.559·0.619 / 0.482·0.606·0.807 / 0.503·0.676·0.828 / 0.529·0.679·0.809 | 0.0211 / 0.0211 | 3.9 |
| S_d64L2_lr3e-4_a0.3_v1_s0 | 3 / 6 | 0.6314 | 0.0621 | 0.5637 / 0.6420 / 0.743 | 0.0594 | 0.9293 | 0.5332 / 0.6216 / 0.755 | 0.561·0.559·0.602 / 0.495·0.606·0.790 / 0.536·0.676·0.805 / 0.552·0.679·0.799 | 0.0184 / 0.0184 | 2.4 |
| S_d64L2_lr1e-4_a3_v1_s0 | 9 / 12 | 0.6300 | 0.0628 | 0.5507 / 0.6420 / 0.749 | 0.0589 | 0.9320 | 0.5193 / 0.6216 / 0.768 | 0.556·0.559·0.615 / 0.487·0.606·0.801 / 0.501·0.676·0.827 / 0.523·0.679·0.806 | 0.0055 / 0.0055 | 4.6 |
| S_d64L2_lr3e-4_a0_v0.3_s0 | 6 / 9 | 0.2322 | 0.0629 | 0.5644 / 0.6420 / 0.752 | 0.0612 | 0.9259 | 0.5247 / 0.6216 / 0.770 | 0.558·0.559·0.618 / 0.486·0.606·0.803 / 0.521·0.676·0.822 / 0.537·0.679·0.806 | 0.0220 / 0.0222 | 3.0 |
| S_d64L2_lr3e-4_a0_v1_s0 | 3 / 6 | 0.6288 | 0.0643 | 0.5645 / 0.6420 / 0.743 | 0.0614 | 0.9259 | 0.5345 / 0.6216 / 0.754 | 0.562·0.559·0.602 / 0.495·0.606·0.789 / 0.540·0.676·0.803 / 0.557·0.679·0.799 | 0.0237 / 0.0236 | 2.0 |
| S_d64L2_lr3e-4_a3_v1_s0 | 3 / 6 | 0.6549 | 0.0645 | 0.5679 / 0.6420 / 0.734 | 0.0602 | 0.9282 | 0.5332 / 0.6216 / 0.754 | 0.558·0.559·0.607 / 0.502·0.606·0.784 / 0.530·0.676·0.810 / 0.563·0.679·0.790 | 0.0075 / 0.0077 | 2.4 |
| S_d64L2_lr1e-3_a1_v0.3_s0 | 3 / 6 | 0.2638 | 0.0745 | 0.5527 / 0.6420 / 0.748 | 0.0706 | 0.9160 | 0.5267 / 0.6216 / 0.759 | 0.555·0.559·0.610 / 0.491·0.606·0.793 / 0.526·0.676·0.807 / 0.539·0.679·0.790 | 0.0235 / 0.0240 | 2.4 |
| S_d64L2_lr1e-3_a3_v0.3_s0 | 5 / 8 | 0.2933 | 0.0777 | 0.5589 / 0.6420 / 0.745 | 0.0711 | 0.9197 | 0.5267 / 0.6216 / 0.769 | 0.550·0.559·0.624 / 0.493·0.606·0.799 / 0.534·0.676·0.815 / 0.532·0.679·0.805 | 0.0160 / 0.0157 | 3.1 |
| S_d64L2_lr1e-3_a0.3_v0.3_s0 | 3 / 6 | 0.2593 | 0.0813 | 0.5592 / 0.6420 / 0.748 | 0.0782 | 0.9106 | 0.5308 / 0.6216 / 0.758 | 0.556·0.559·0.610 / 0.491·0.606·0.794 / 0.539·0.676·0.804 / 0.556·0.679·0.796 | 0.0340 / 0.0341 | 2.3 |
| S_d64L2_lr1e-3_a3_v1_s0 | 2 / 5 | 0.7035 | 0.0831 | 0.5601 / 0.6420 / 0.754 | 0.0772 | 0.9191 | 0.5300 / 0.6216 / 0.765 | 0.575·0.559·0.619 / 0.485·0.606·0.802 / 0.516·0.676·0.817 / 0.538·0.679·0.794 | 0.0201 / 0.0203 | 2.0 |
| S_d64L2_lr1e-3_a1_v1_s0 | 1 / 4 | 0.6945 | 0.0883 | 0.5766 / 0.6420 / 0.708 | 0.0836 | 0.9110 | 0.5532 / 0.6216 / 0.715 | 0.554·0.559·0.594 / 0.532·0.606·0.752 / 0.578·0.676·0.769 / 0.569·0.679·0.780 | 0.0296 / 0.0299 | 1.7 |
| S_d64L2_lr1e-3_a0_v0.3_s0 | 3 / 6 | 0.2585 | 0.0892 | 0.5644 / 0.6420 / 0.748 | 0.0874 | 0.9012 | 0.5335 / 0.6216 / 0.758 | 0.557·0.559·0.611 / 0.489·0.606·0.796 / 0.549·0.676·0.803 / 0.574·0.679·0.798 | 0.0423 / 0.0433 | 2.0 |
| S_d64L2_lr1e-3_a0.3_v1_s0 | 1 / 4 | 0.6830 | 0.0955 | 0.5755 / 0.6420 / 0.719 | 0.0908 | 0.9090 | 0.5470 / 0.6216 / 0.730 | 0.554·0.559·0.600 / 0.522·0.606·0.765 / 0.562·0.676·0.785 / 0.599·0.679·0.789 | 0.0400 / 0.0399 | 1.7 |
| S_d64L2_lr1e-3_a0_v1_s0 | 1 / 4 | 0.6836 | 0.1063 | 0.5773 / 0.6420 / 0.721 | 0.1014 | 0.9032 | 0.5473 / 0.6216 / 0.733 | 0.555·0.559·0.600 / 0.520·0.606·0.769 / 0.562·0.676·0.786 / 0.611·0.679·0.787 | 0.0543 / 0.0542 | 1.4 |

## Architectures (random init, anchor weight 0, at the best grid point lr 1e-4 / value weight 0.3; anchor KL vs student_sel via --anchor-ref)

| run | chosen / run ep | sel objective | sel policy KL | sel value BCE / const / AUC | val KL to π' | val top-1 | val value BCE / const / AUC | val BCE·const·AUC per act (1 / 2 / 3 / 4) | anchor KL sel / val | wall min |
|---|---|---|---|---|---|---|---|---|---|---|
| A_d128L2_lr1e-4_a0_v0.3_s0 | 20 / 20 | 0.3638 | 0.1906 | 0.5774 / 0.6420 / 0.717 | 0.1877 | 0.8608 | 0.5603 / 0.6216 / 0.710 | 0.566·0.559·0.589 / 0.545·0.606·0.723 / 0.569·0.676·0.778 / 0.573·0.679·0.772 | 0.1257 / 0.1323 | 9.8 |
| A_d96L2_lr1e-4_a0_v0.3_s0 | 17 / 20 | 0.4069 | 0.2246 | 0.6074 / 0.6420 / 0.664 | 0.2266 | 0.8467 | 0.5745 / 0.6216 / 0.677 | 0.569·0.559·0.604 / 0.563·0.606·0.721 / 0.596·0.676·0.757 / 0.598·0.679·0.754 | 0.1549 / 0.1576 | 8.2 |
| A_d64L3_lr1e-4_a0_v0.3_s0 | 20 / 20 | 0.4260 | 0.2386 | 0.6247 / 0.6420 / 0.635 | 0.2342 | 0.8412 | 0.5859 / 0.6216 / 0.661 | 0.567·0.559·0.617 / 0.573·0.606·0.701 / 0.628·0.676·0.719 / 0.630·0.679·0.724 | 0.1611 / 0.1650 | 8.0 |

## Seed reruns of the pick and the 40-epoch cap check

| run | chosen / run ep | sel objective | sel policy KL | sel value BCE / const / AUC | val KL to π' | val top-1 | val value BCE / const / AUC | val BCE·const·AUC per act (1 / 2 / 3 / 4) | anchor KL sel / val | wall min |
|---|---|---|---|---|---|---|---|---|---|---|
| S_d64L2_lr1e-4_a0.3_v0.3_ep40_s0 | 12 / 15 | 0.2270 | 0.0567 | 0.5544 / 0.6420 / 0.741 | 0.0547 | 0.9320 | 0.5228 / 0.6216 / 0.760 | 0.550·0.559·0.615 / 0.495·0.606·0.790 / 0.516·0.676·0.820 / 0.525·0.679·0.803 | 0.0131 / 0.0129 | 5.7 |
| S_d64L2_lr1e-4_a0.3_v0.3_s0 | 17 / 20 | 0.2269 | 0.0554 | 0.5590 / 0.6420 / 0.740 | 0.0542 | 0.9333 | 0.5255 / 0.6216 / 0.758 | 0.554·0.559·0.615 / 0.497·0.606·0.788 / 0.519·0.676·0.819 / 0.525·0.679·0.804 | 0.0125 / 0.0125 | 7.6 |
| S_d64L2_lr1e-4_a0.3_v0.3_s1 | 17 / 20 | 0.2265 | 0.0553 | 0.5583 / 0.6420 / 0.740 | 0.0543 | 0.9337 | 0.5252 / 0.6216 / 0.758 | 0.552·0.559·0.614 / 0.497·0.606·0.788 / 0.519·0.676·0.819 / 0.525·0.679·0.804 | 0.0126 / 0.0125 | 7.5 |
| S_d64L2_lr1e-4_a0.3_v0.3_s2 | 14 / 17 | 0.2259 | 0.0550 | 0.5574 / 0.6420 / 0.737 | 0.0538 | 0.9339 | 0.5277 / 0.6216 / 0.753 | 0.550·0.559·0.616 / 0.501·0.606·0.782 / 0.526·0.676·0.813 / 0.529·0.679·0.802 | 0.0122 / 0.0122 | 6.4 |

## Stage T (T1 teacher scored on π' directly; T3's own run targets teacher logits, so its π' numbers are E_T3_on_gen2)

| run | chosen / run ep | sel objective | sel policy KL | sel value BCE / const / AUC | val KL to π' | val top-1 | val value BCE / const / AUC | val BCE·const·AUC per act (1 / 2 / 3 / 4) | anchor KL sel / val | wall min |
|---|---|---|---|---|---|---|---|---|---|---|
| E_T3_on_gen2 | 1 / 1 | 0.6524 | 0.1000 | 0.5524 / 0.6420 / 0.741 | 0.0956 | 0.9121 | 0.5256 / 0.6216 / 0.759 | 0.551·0.559·0.598 / 0.501·0.606·0.790 / 0.512·0.676·0.822 / 0.560·0.679·0.792 | 0.0352 / 0.0370 | 0.5 |
| T1_heart1_lr1e-4_a1_v1_bs256_s0 | 1 / 4 | 0.6995 | 0.1178 | 0.5462 / 0.6420 / 0.768 | 0.1085 | 0.9021 | 0.5015 / 0.6216 / 0.786 | 0.540·0.559·0.637 / 0.468·0.606·0.813 / 0.483·0.676·0.858 / 0.506·0.679·0.857 | 0.0355 / 0.0355 | 11.0 |
| T3_distill_d64L2_lr3e-4_a0_v1_s0 | 1 / 4 | 0.5934 | 0.0410 | 0.5524 / 0.6420 / 0.741 | 0.0412 | 0.9405 | 0.5256 / 0.6216 / 0.759 | 0.551·0.559·0.598 / 0.501·0.606·0.790 / 0.512·0.676·0.822 / 0.560·0.679·0.792 | 0.0352 / 0.0370 | 9.5 |

## Reference, reported last and never used to choose (lr-0 single-epoch passes = the net unchanged, same folds)

| run | chosen / run ep | sel objective | sel policy KL | sel value BCE / const / AUC | val KL to π' | val top-1 | val value BCE / const / AUC | val BCE·const·AUC per act (1 / 2 / 3 / 4) | anchor KL sel / val | wall min |
|---|---|---|---|---|---|---|---|---|---|---|
| E_gen1b | 1 / 1 | 0.6323 | 0.0654 | 0.5669 / 0.6420 / 0.725 | 0.0616 | 0.9256 | 0.5479 / 0.6216 / 0.729 | 0.550·0.559·0.592 / 0.531·0.606·0.756 / 0.566·0.676·0.777 / 0.560·0.679·0.794 | 0.0145 / 0.0149 | 0.5 |
| E_student_sel | 1 / 1 | 0.7924 | 0.1031 | 0.6893 / 0.6420 / 0.415 | 0.1010 | 0.9354 | 0.6885 / 0.6216 / 0.394 | 0.688·0.559·0.484 / 0.687·0.606·0.441 / 0.690·0.676·0.435 / 0.698·0.679·0.515 | 0.0000 / 0.0000 | 0.5 |
| S_d64L2_lr1e-4_a0.3_v0.3_s0 | 17 / 20 | 0.2269 | 0.0554 | 0.5590 / 0.6420 / 0.740 | 0.0542 | 0.9333 | 0.5255 / 0.6216 / 0.758 | 0.554·0.559·0.615 / 0.497·0.606·0.788 / 0.519·0.676·0.819 / 0.525·0.679·0.804 | 0.0125 / 0.0125 | 7.6 |

## Side test: full data (no value subsample), pack + val-at-end — stopped after 7 points by decision

| run | chosen / run ep | sel objective | sel policy KL | sel value BCE / const / AUC | val KL to π' | val top-1 | val value BCE / const / AUC | val BCE·const·AUC per act (1 / 2 / 3 / 4) | anchor KL sel / val | wall min |
|---|---|---|---|---|---|---|---|---|---|---|
| S_d64L2_lr1e-4_a1_v0.3_s0 | 4 / 7 | 0.2322 | 0.0548 | 0.5580 / 0.6420 / 0.736 | 0.0544 | 0.9343 | 0.5343 / 0.6216 / 0.746 | 0.546·0.559·0.610 / 0.515·0.606·0.767 / 0.541·0.676·0.801 / 0.538·0.679·0.795 | 0.0100 / 0.0102 | 8.0 |
| S_d64L2_lr1e-4_a0.3_v0.3_s0 | 4 / 7 | 0.2265 | 0.0553 | 0.5557 / 0.6420 / 0.738 | 0.0558 | 0.9307 | 0.5311 / 0.6216 / 0.750 | 0.546·0.559·0.611 / 0.511·0.606·0.772 / 0.534·0.676·0.806 / 0.535·0.679·0.797 | 0.0148 / 0.0150 | 14.7 |
| S_d64L2_lr1e-4_a0_v0.3_s0 | 4 / 7 | 0.2236 | 0.0572 | 0.5547 / 0.6420 / 0.739 | 0.0580 | 0.9276 | 0.5298 / 0.6216 / 0.752 | 0.546·0.559·0.610 / 0.509·0.606·0.774 / 0.531·0.676·0.809 / 0.534·0.679·0.797 | 0.0196 / 0.0197 | 10.1 |
| S_d64L2_lr1e-4_a1_v1_s0 | 3 / 6 | 0.6191 | 0.0620 | 0.5451 / 0.6420 / 0.753 | 0.0577 | 0.9283 | 0.5149 / 0.6216 / 0.770 | 0.547·0.559·0.615 / 0.486·0.606·0.800 / 0.502·0.676·0.827 / 0.504·0.679·0.817 | 0.0120 / 0.0118 | 7.0 |
| S_d64L2_lr1e-4_a0.3_v1_s0 | 3 / 6 | 0.6116 | 0.0629 | 0.5436 / 0.6420 / 0.755 | 0.0592 | 0.9261 | 0.5143 / 0.6216 / 0.770 | 0.547·0.559·0.614 / 0.485·0.606·0.801 / 0.502·0.676·0.828 / 0.502·0.679·0.819 | 0.0169 / 0.0167 | 7.3 |
| S_d64L2_lr1e-4_a0_v1_s0 | 3 / 6 | 0.6079 | 0.0650 | 0.5429 / 0.6420 / 0.755 | 0.0614 | 0.9234 | 0.5141 / 0.6216 / 0.770 | 0.548·0.559·0.613 / 0.484·0.606·0.802 / 0.501·0.676·0.828 / 0.501·0.679·0.820 | 0.0212 / 0.0211 | 10.1 |
| S_d64L2_lr3e-4_a1_v1_s0 | 1 / 4 | 0.6599 | 0.0733 | 0.5694 / 0.6420 / 0.716 | 0.0676 | 0.9237 | 0.5508 / 0.6216 / 0.724 | 0.548·0.559·0.601 / 0.535·0.606·0.751 / 0.575·0.676·0.774 / 0.565·0.679·0.780 | 0.0172 / 0.0169 | 4.7 |

## Side test: value subsample (K per run per epoch), recipe lr 3e-4 / a1 / v1

| run | chosen / run ep | sel objective | sel policy KL | sel value BCE / const / AUC | val KL to π' | val top-1 | val value BCE / const / AUC | val BCE·const·AUC per act (1 / 2 / 3 / 4) | anchor KL sel / val | wall min |
|---|---|---|---|---|---|---|---|---|---|---|
| K_d64L2_lr3e-4_a1_v1_k16_ep20_s0 | 5 / 20 | 0.6372 | 0.0633 | 0.5619 / 0.6420 / 0.751 | 0.0589 | 0.9295 | 0.5265 / 0.6216 / 0.768 | 0.563·0.559·0.619 / 0.487·0.606·0.800 / 0.518·0.676·0.819 / 0.540·0.679·0.796 | 0.0120 / 0.0119 | 11.3 |
| K_d64L2_lr3e-4_a1_v1_k16_s0 | 5 / 8 | 0.6376 | 0.0634 | 0.5622 / 0.6420 / 0.751 | 0.0590 | 0.9289 | 0.5267 / 0.6216 / 0.768 | 0.563·0.559·0.619 / 0.487·0.606·0.800 / 0.518·0.676·0.819 / 0.540·0.679·0.796 | 0.0120 / 0.0119 | 4.8 |
| K_d64L2_lr3e-4_a1_v1_k32_ep20_s0 | 3 / 20 | 0.6390 | 0.0618 | 0.5640 / 0.6420 / 0.742 | 0.0586 | 0.9280 | 0.5321 / 0.6216 / 0.756 | 0.562·0.559·0.603 / 0.496·0.606·0.790 / 0.531·0.676·0.808 / 0.548·0.679·0.797 | 0.0132 / 0.0133 | 15.6 |
| S_d64L2_lr3e-4_a1_v1_s0 | 1 / 4 | 0.6540 | 0.0713 | 0.5669 / 0.6420 / 0.724 | 0.0648 | 0.9278 | 0.5482 / 0.6216 / 0.728 | 0.549·0.559·0.595 / 0.532·0.606·0.750 / 0.569·0.676·0.770 / 0.556·0.679·0.786 | 0.0158 / 0.0155 | 13.5 |

Per-epoch selection-fold policy KL / value BCE (const 0.642):

- K_d64L2_lr3e-4_a1_v1_k16_ep20_s0: ep1 0.0669/0.629, ep2 0.0631/0.599, ep3 0.0672/0.563, ep4 0.0629/0.574, ep5 0.0633/0.562, ep6 0.0651/0.572, ep7 0.0640/0.624, ep8 0.0664/0.600, ep9 0.0649/0.634, ep10 0.0673/0.649, ep11 0.0659/0.668, ep12 0.0667/0.683, ep13 0.0681/0.693, ep14 0.0675/0.749, ep15 0.0686/0.737, ep16 0.0688/0.753, ep17 0.0689/0.767, ep18 0.0686/0.762, ep19 0.0688/0.768, ep20 0.0687/0.771
- K_d64L2_lr3e-4_a1_v1_k32_ep20_s0: ep1 0.0647/0.625, ep2 0.0642/0.575, ep3 0.0618/0.564, ep4 0.0660/0.573, ep5 0.0633/0.591, ep6 0.0657/0.632, ep7 0.0665/0.683, ep8 0.0659/0.680, ep9 0.0671/0.722, ep10 0.0697/0.740, ep11 0.0707/0.849, ep12 0.0706/0.856, ep13 0.0700/0.922, ep14 0.0702/0.968, ep15 0.0712/0.972, ep16 0.0710/0.993, ep17 0.0715/1.015, ep18 0.0713/1.024, ep19 0.0713/1.028, ep20 0.0714/1.027
- S_d64L2_lr3e-4_a1_v1_s0: ep1 0.0713/0.567, ep2 0.0716/0.569, ep3 0.0702/0.657, ep4 0.0742/1.025
- S_d64L2_lr3e-4_a1_v1_s0: ep1 0.0733/0.569, ep2 0.0719/0.593, ep3 0.0720/0.659, ep4 0.0738/0.887

## Speed benchmarks (1 epoch, full cached data, lr 3e-4 / a1 / v1)

| run | chosen / run ep | sel objective | sel policy KL | sel value BCE / const / AUC | val KL to π' | val top-1 | val value BCE / const / AUC | val BCE·const·AUC per act (1 / 2 / 3 / 4) | anchor KL sel / val | wall min |
|---|---|---|---|---|---|---|---|---|---|---|
| bench_a_k16 | 1 / 1 | 0.7120 | 0.0713 | 0.6308 / 0.6420 / 0.624 | 0.0638 | 0.9282 | 0.6008 / 0.6216 / 0.633 | 0.557·0.559·0.528 / 0.591·0.606·0.621 / 0.672·0.676·0.632 / 0.689·0.679·0.677 | 0.0099 / 0.0098 | 1.4 |
| bench_a_k32 | 1 / 1 | 0.7049 | 0.0652 | 0.6287 / 0.6420 / 0.640 | 0.0605 | 0.9319 | 0.5959 / 0.6216 / 0.648 | 0.560·0.559·0.541 / 0.586·0.606·0.648 / 0.660·0.676·0.650 / 0.660·0.679·0.695 | 0.0110 / 0.0110 | 1.1 |
| bench_base | 1 / 1 | 0.6543 | 0.0714 | 0.5670 / 0.6420 / 0.724 | 0.0649 | 0.9276 | 0.5482 / 0.6216 / 0.728 | 0.549·0.559·0.595 / 0.532·0.606·0.750 / 0.569·0.676·0.770 / 0.556·0.679·0.786 | 0.0159 / 0.0156 | 2.7 |
| bench_c_valend | 1 / 1 | 0.6597 | 0.0732 | 0.5694 / 0.6420 / 0.716 | 0.0677 | 0.9245 | 0.5508 / 0.6216 / 0.724 | 0.548·0.559·0.601 / 0.534·0.606·0.751 / 0.575·0.676·0.774 / 0.565·0.679·0.780 | 0.0171 / 0.0168 | 2.5 |
| bench_d_pack | 1 / 1 | 0.6537 | 0.0712 | 0.5668 / 0.6420 / 0.724 | 0.0649 | 0.9278 | 0.5481 / 0.6216 / 0.728 | 0.548·0.559·0.595 / 0.532·0.606·0.750 / 0.569·0.676·0.770 / 0.556·0.679·0.786 | 0.0157 / 0.0155 | 1.4 |
| bench_e_pack_valend | 1 / 1 | 0.6599 | 0.0734 | 0.5693 / 0.6420 / 0.716 | 0.0677 | 0.9239 | 0.5507 / 0.6216 / 0.724 | 0.548·0.559·0.601 / 0.534·0.606·0.751 / 0.575·0.676·0.774 / 0.565·0.679·0.780 | 0.0172 / 0.0169 | 1.3 |
| bench_f_pack_bs1024 | 1 / 1 | 0.6770 | 0.0660 | 0.5964 / 0.6420 / 0.688 | 0.0626 | 0.9283 | 0.5716 / 0.6216 / 0.695 | 0.554·0.559·0.572 / 0.560·0.606·0.722 / 0.611·0.676·0.720 / 0.606·0.679·0.747 | 0.0146 / 0.0146 | 1.3 |

## Notes
- Shuffle-noise floor: the same recipe with only the shuffle RNG stream shifted moved selection KL by ~0.002 (bench_base vs
  bench_c_valend); seed reruns of the pick differ by ±0.0002.
- Wall times of runs that shared the GPU (ktest K_* runs ran alongside grid points) are inflated.
- bench_b_bs1024 (unpacked bs 1024) hit CUDA OOM and has no summary.
- Weights: d64 students (`student.pt` + native export `student.bin`, `--n-heads 4 --trim-map`) in `weights/`, sha256 in
  `weights/SHA256SUMS`. Not pushed (24 MB each): the T1 teacher, kept on the PC at
  `~/h1distill/gen2/sweep/T1_heart1_lr1e-4_a1_v1_bs256_s0/student.pt` (sha256 `610b509b…`; export `--n-heads 8`, untrimmed,
  sha256 `d42b1c99…` at `~/h1distill/gen2/export/T1_heart1.bin`), and the teacher-labeled rows (`~/h1distill/gen2/teacher_rows`, 2,816 files).

