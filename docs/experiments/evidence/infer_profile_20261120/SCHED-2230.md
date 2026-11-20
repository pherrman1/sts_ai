<!-- Relayed by the run's thread from the PC, 2026-11-20 22:32 CET. -->

# Confirmation + scheduler stats, amber_scratch 2026-11-20 ~22:25 CET

Process PID 1178460 (c5_repo @d12d4d2e), --packed-heads + --force-potions, no --ooc-canon. A5, 450 games, 11 workers (default), --batch default 2048 (trainer effectively 1024/step per log). Taken just before the 22:29 restart onto --ooc-canon.

## Throughput (6 rows 22:25:24-22:27:57)
| | moves/s | pos/s |
|---|---|---|
| before (21:25, c4_repo, no packed-heads/force-potions) | 10,639 | 209,161 |
| 22:05 | 10,051 | 195,538 |
| 22:25 | 11,930 (+12 %) | 233,006 (+11 %) |
infer forward 344.4, wait_pack 440.6, gpu_ms infer/train 659 / 430. Window win 41.5 %.
dmon (22:28): SM mean 74.1 %, mem 51.4 %. top 30 s: 66.8 % user, 6.5 % sys, 26.7 % idle.
What differed at 22:05 (unclear): StS2 closed only ~21:56 (GPU/compositor after-effects?), run 25 min old, row noise. Asc/games/flags identical 22:05-22:25.
Changed 21:25 -> 22:25: only --packed-heads, --force-potions, code c4 -> c5 (d12d4d2e). (--ooc-canon briefly 21:29-21:31, crash.)

## cmdline (22:28)
```
python3 tools/az_bench/selfplay.py --module-dir build/linux-gcc-release --resume .../ckpt_738152_r3303599.pt --out-dir .../amber_scratch --seed-base 140000000 --ascension 0 --curriculum --utility amber2-root --merge-cards --no-fast-noise --q-rescale --c-scale 0.1 --value-ema-halflife 20 --value-ema-search --value-ema-moves full --w-soft-policy 8 --explore-amber --explore-per-offer --pick-target 0.01 --chance-on-reveal --cross-combat --sim-help --eval-cache --packed-h2d --train-packed --gpu-timing --hours 168 --compile --fused-layer --report 30 --force-keys on --full-candidates 8 --malloc-trim --window 10000000 --max-pending 0 --curriculum-winrate 1.01 --games 450 --compact-samples --replay-dict-tokens 3 --replay-actions-per-sample 8 --compress-targets --heart-log 0.1 --force-rewards --attn-row-bounds --packed-heads --force-potions --replay-save .../replay --replay-load .../replay
```
(ascension 5 comes from the ASCENSION file.)

## schedstat over 30.5 s (running / runqueue wait / sleeping)
- Workers (11 threads): 61.8-64.0 % / 6.2-6.7 % / 29.8-31.7 %
- Inference thread (TID 1178672): 73.8 % / 3.8 % / 22.5 %
- Trainer (TID 1178673): 41.2 % / 3.3 % / 55.5 %
- torch intra-op (5): ~4 % / 1-2.4 % / ~94 % each
- pt_autograd_0: 5.2 % / 2.1 % / 92.7 %
- cuda-EvtHandlr: 0 / 2.1 / 97.9
- rest (main, pack pool, others): idle, <= 2 % running
PC reading: workers ~63 % running and ~30 % sleeping (waiting), inference 74 % busy, GPU 74 %; trainer half idle at replay-ratio cap. CPU 27 % idle overall.
Full JSON rows and raw files follow.

## Rows 22:25 (key fields; full ~5 KB JSON lines on PC: amber_scratch/confirm_rows_20261120_2228.jsonl)
Format: time | moves | pos | cache | infer_batches/s | rows/batch | tok/row | infer_ms {wait_pack, weights, h2d, fwd, out, sync, submit} | train_ms {take_add, idle, sample, h2d, fwd_bwd, sync, opt} | gpu_ms {inf, train} | worker_cpu {search, step, encode} | pack_s | trained_samples | samples_added | win | floor
```
22:25:24 | 11864 | 232404 | 45913 | 179.1 | 1280.7 | 37.20 | 432.6 7.4 60.1 339.3 35.8 60.9 47.1 | 88.7 417.3 46.6 39.3 135.0 243.3 29.4 | 656.0 446.3 | 6.866 2.895 1.624 | 0.2615 | 767036416 | 97865601 | 0.4274 | 47.13
22:25:54 | 12221 | 237704 | 47157 | 184.5 | 1280.9 | 37.37 | 433.5 7.6 60.2 349.0 36.3 54.9 48.7 | 70.5 465.2 44.8 37.3 128.7 220.8 27.7 | 660.7 414.6 | 6.935 2.924 1.673 | 0.2687 | 767179776 | 97936964 | 0.3935 | 46.85
22:26:25 | 11872 | 232411 | 45477 | 182.7 | 1280.9 | 37.46 | 445.5 7.6 61.5 345.4 36.2 59.7 48.5 | 72.6 445.1 46.0 41.3 127.5 241.2 28.9 | 665.1 438.6 | 6.925 2.922 1.633 | 0.2611 | 767330304 | 98012459 | 0.4347 | 46.76
22:26:55 | 11815 | 230975 | 45529 | 179.8 | 1285.1 | 37.46 | 442.3 7.5 60.3 342.6 35.8 61.5 47.4 | 76.0 432.5 48.0 38.4 130.1 245.8 29.7 | 661.7 443.3 | 6.883 2.911 1.626 | 0.2636 | 767483904 | 98089269 | 0.4028 | 46.69
22:27:26 | 11958 | 233320 | 45875 | 180.5 | 1288.7 | 37.44 | 443.9 7.5 60.7 340.7 35.8 60.0 47.7 | 72.5 453.7 44.8 38.5 125.0 234.7 27.9 | 655.7 426.4 | 6.935 2.928 1.641 | 0.2646 | 767632384 | 98163666 | 0.3963 | 46.23
22:27:57 | 11848 | 231219 | 45673 | 182.2 | 1283.6 | 37.47 | 445.6 7.8 60.6 349.1 36.8 56.8 49.0 | 73.3 471.4 44.0 37.2 124.7 219.1 27.4 | 656.3 407.9 | 6.914 2.918 1.632 | 0.2655 | 767773696 | 98234114 | 0.4351 | 46.54
```
trained/added 2.00. Stalls 7 (const), invalid 0, kf 0, nonfinite 0, grad_norm mean 4.1-5.5. Token buckets mostly 96 (~4,300-4,850/window), 128: 575-1,754.
vs 21:25: worker_cpu search 6.25 -> 6.91, step 2.66 -> 2.92, encode 1.46 -> 1.64; gpu infer 808 -> 659 ms/s; batches/s 160 -> 181.
Note: worker_cpu "search" includes step+encode per speed thread.
Remaining raw files (post_ph_rows, infer_profile_ph json/log) stay on PC amber_scratch/; key numbers in packed-heads-live.md.
