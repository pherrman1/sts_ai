<!-- Relayed by the run's thread from the PC, 2026-11-21 19:25 and 19:31 CET; read from /proc and metrics.jsonl, nothing attached to the process. -->

# Speed measurement 2026-11-21 19:21–19:24 CET (amber_scratch, PID 1903783)

## 1. Run
- Start 18:41:37 CET (resume ckpt_916188.pt); measured 40–43 min after start.
- Code aux_repo 963ea4bf4 (main, #1147..#1155), native build build/linux-gcc-release (18:40).
- --early-finish on; #1147 included (key infer_early_packed_per_batch present).
- --parallel-nodes 4, --aux-fights, --explore-clean-keys, --hp-ema-search on. Savescum on, A20, 1.22M net (128x4), 64/16 sims, 11 workers x 300 games.
- No other CUDA job (desktop only); training process 4486 MiB.
- Command (cwd aux_repo via tools/seed_guard.sh):
```
python3 tools/az_bench/selfplay.py --module-dir build/linux-gcc-release --resume .../amber_scratch/ckpt_916188.pt --out-dir .../amber_scratch --seed-base 140000000 --ascension 0 --curriculum --utility amber2-root --merge-cards --no-fast-noise --rng-fix --parallel-nodes 4 --hp-ema-search --replay-hp-bytes 96 --q-rescale --c-scale 0.1 --value-ema-halflife 20 --value-ema-search --value-ema-moves full --w-soft-policy 8 --savescum --explore-amber --explore-clean-keys --explore-resume --pick-target 0.01 --chance-on-reveal --cross-combat --sim-help --eval-cache --packed-h2d --train-packed --gpu-timing --hours 168 --compile --fused-layer --report 30 --force-keys on --full-candidates 8 --malloc-trim --window 10000000 --max-pending 0 --curriculum-winrate 1.01 --games 300 --compact-samples --replay-dict-tokens 3 --replay-actions-per-sample 8 --compress-targets --heart-log 0.1 --force-rewards --attn-row-bounds --packed-heads --force-potions --ooc-canon --early-finish --replay-save .../amber_scratch/replay --replay-load .../amber_scratch/replay --net 128x4 --teacher-ckpt .../amber_scratch/ckpt_786401.pt --teacher-net 0.44M --kickstart-mix 0.5 --aux-fights
```

## 2. Six metrics rows (19:21:36–19:24:06, report 30 s)
Units: *_ms_per_s in ms/s; cpu in CPU s/s (11 workers); pack s/s.

| time | moves/s | pos/s | cache hits/s | batches/s | rows/batch | tok/row | inf.wait_pack | inf.weights | inf.h2d | inf.forward | inf.out | inf.sync | inf.submit | tr.take_add | tr.idle | tr.sample | tr.h2d | tr.fwd_bwd | tr.sync | tr.opt | tr.loss_read | tr.publish | gpu inf | gpu tr | cpu search | cpu step | cpu encode | pack s/s | early/b | early_packed/b | tok buckets |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 19:21:36 | 8202 | 126902 | 71554 | 62.1 | 2038.0 | 40.31 | 172.0 | 5.8 | 42.8 | 162.2 | 38.4 | 467.5 | 82.3 | 197.4 | 49.3 | 40.6 | 13.1 | 99.1 | 561.0 | 28.6 | 9.4 | 0.1 | 937.6 | 709.7 | 4.928 | 1.797 | 1.134 | 0.156 | 0.035 | 0.019 | 80:95 96:1211 128:609 |
| 19:22:07 | 7958 | 123456 | 69068 | 60.7 | 2034.0 | 40.11 | 178.8 | 6.0 | 48.3 | 164.0 | 29.6 | 462.0 | 82.8 | 189.0 | 52.5 | 40.6 | 15.6 | 99.1 | 564.1 | 28.8 | 10.1 | 0.1 | 936.6 | 716.3 | 4.8 | 1.753 | 1.094 | 0.1615 | 0.036 | 0.015 | 80:65 96:1022 128:785 |
| 19:22:38 | 8245 | 127593 | 71829 | 62.9 | 2032.1 | 40.31 | 177.5 | 5.6 | 45.0 | 161.8 | 32.2 | 466.0 | 81.5 | 194.3 | 105.6 | 36.5 | 13.2 | 88.0 | 528.0 | 26.7 | 10.0 | 0.1 | 935.3 | 667.1 | 4.965 | 1.815 | 1.131 | 0.1595 | 0.038 | 0.018 | 80:32 96:939 128:968 |
| 19:23:09 | 7987 | 125076 | 68664 | 61.6 | 2029.6 | 40.16 | 171.1 | 5.8 | 44.5 | 159.5 | 38.3 | 473.9 | 80.1 | 193.6 | 35.5 | 40.3 | 14.4 | 92.0 | 585.1 | 27.9 | 11.2 | 0.2 | 934.7 | 728.2 | 4.881 | 1.772 | 1.093 | 0.1524 | 0.037 | 0.02 | 64:1 80:67 96:609 128:1225 |
| 19:23:40 | 8137 | 126151 | 71121 | 61.4 | 2038.1 | 39.92 | 164.1 | 5.5 | 40.8 | 154.8 | 31.7 | 485.2 | 78.5 | 193.1 | 64.6 | 36.9 | 13.7 | 93.5 | 566.3 | 26.0 | 10.6 | 0.1 | 934.0 | 709.5 | 4.827 | 1.759 | 1.097 | 0.1524 | 0.036 | 0.016 | 80:17 96:820 128:1057 |
| 19:24:10 | 8249 | 126534 | 72059 | 62.6 | 2034.7 | 39.84 | 176.8 | 6.1 | 44.0 | 167.0 | 33.1 | 461.8 | 83.1 | 194.7 | 54.8 | 39.3 | 13.5 | 95.4 | 560.2 | 28.4 | 9.4 | 0.1 | 940.3 | 705.7 | 4.908 | 1.792 | 1.116 | 0.1573 | 0.036 | 0.023 | 80:82 96:928 128:914 |

parallel_nodes (last row): flights_per_wave 6.51, collisions_per_k 149.6, flight_slots 83500.

## 3. GPU and CPU
- nvidia-smi dmon 30 s (19:21:12–19:21:42): SM 98.4 %, mem 52.7 %.
- top 30 s: 57.7 % us, 7.4 % sy, 1.0 % ni, 33.7 % id, 0.0 % wa.

## 4. schedstat per thread, 30 s (19:21:12–19:21:42), fractions running/runqueue/sleeping
| Thread | TID | running | runqueue | sleeping |
|---|---|---|---|---|
| Inference | 1903992 | 0.839 | 0.036 | 0.126 |
| Trainer | 1903993 | 0.828 | 0.021 | 0.151 |
| Workers (mean of 11) | 1903999–1904009 | 0.475 (0.470–0.478) | 0.079 (0.077–0.081) | 0.446 (0.441–0.451) |
| other (aux labeller/pin?) | 1910547 | 0.042 | 0.013 | 0.945 |
| main | 1903783 | 0.027 | 0.001 | 0.972 |
(Threads unnamed; mapping by start order (selfplay.py:2129) and CPU profile.)

## Notes
- Mean of 6 rows: 8,130 moves/s, 125.9k pos/s. Before aux restart (17:13–18:40, no --aux-fights): ~9.3k moves/s; 18:53 with aux: 8.9k. Drop may partly be --aux-fights; not isolated.
- GPU saturated (SM 98 %); workers sleep ~45 %, mostly waiting for inference.

## Addendum 19:3x CET (metrics.jsonl only)

### A. 10 consecutive steady rows of the aux run (start 18:41:37; rows >= 35 min after)
| time | train_steps | trained_samples | samples_added | aux rows | aux samples | aux driver_rows | aux label_s | kickstart_lambda |
|---|---|---|---|---|---|---|---|---|
| 19:17:01 | 923738 | 945907712 | 187301377 | 4635178 | 604178 | 5102964 | 265.3 | 0.0 |
| 19:17:31 | 923843 | 946015232 | 187355158 | 4700420 | 612673 | 5169600 | 269.6 | 0.0 |
| 19:18:02 | 923965 | 946140160 | 187417596 | 4773666 | 622260 | 5236680 | 273.7 | 0.0 |
| 19:18:32 | 924071 | 946248704 | 187471847 | 4836642 | 630474 | 5307122 | 277.8 | 0.0 |
| 19:19:02 | 924181 | 946361344 | 187528748 | 4904864 | 639397 | 5378700 | 282.0 | 0.0 |
| 19:19:33 | 924296 | 946479104 | 187587799 | 4973762 | 648403 | 5442370 | 286.0 | 0.0 |
| 19:20:04 | 924402 | 946587648 | 187640856 | 5036394 | 656535 | 5507254 | 290.1 | 0.0 |
| 19:20:35 | 924511 | 946699264 | 187697173 | 5103376 | 665261 | 5577294 | 294.2 | 0.0 |
| 19:21:05 | 924622 | 946812928 | 187753519 | 5169172 | 673868 | 5643332 | 298.3 | 0.0 |
| 19:21:36 | 924732 | 946925568 | 187810563 | 5238052 | 682886 | 5706440 | 302.5 | 0.0 |

Deltas (275 s): train_steps 3.61/s, trained_samples 3701/s, samples_added 1852/s, trained/added 2.00; aux rows +602,874, driver_rows +603,476, label_s +37.2 (13.5 % of wall time).

### B. Kickstart state
- kickstart_lambda = 0.0 in every row; amber_scratch/KICKSTART_LAMBDA = 0 (since 09:15 CET).
- selfplay.py:2055-2058 (963ea4bf): teacher forward only if lam > 0 -> skipped every step. Teacher still loaded on GPU at start (selfplay.py:1538-1552): memory only, no per-step compute. KICKSTART_LAMBDA re-read each report (selfplay.py:2182).
- No planned end; dropping --teacher-ckpt/--teacher-net/--kickstart-mix at next restart only saves teacher memory.

### C. 17:13 run (cf2_repo 8e2440b6, no --aux-fights), 6 rows from 17:48 (>= 35 min after start)
| time | moves/s | pos/s | train_steps | trained_samples | samples_added | gpu infer | gpu train | tr.take_add | train_ms_per_s | infer_ms_per_s |
|---|---|---|---|---|---|---|---|---|---|---|
| 17:48:37 | 9772 | 149087 | 903847 | 925539328 | 177116674 | 949.1 | 651.1 | 62.5 | idle 241.1, sample 40.4, h2d 13.8, fwd_bwd 71.2, sync 531.6, opt 26.7, loss_read 8.9, publish 0.1 | wait_pack 195.6, weights 7.0, h2d 36.3, forward 167.8, out 23.3, sync 478.5, submit 92.0 |
| 17:49:08 | 9261 | 142878 | 903973 | 925668352 | 177181594 | 950.4 | 740.8 | 73.6 | idle 146.1, sample 45.1, h2d 15.6, fwd_bwd 83.3, sync 599.9, opt 30.2, loss_read 10.1, publish 0.2 | wait_pack 203.4, weights 6.9, h2d 35.0, forward 165.5, out 22.4, sync 485.5, submit 91.2 |
| 17:49:38 | 9433 | 144260 | 904096 | 925794304 | 177244243 | 932.0 | 722.0 | 79.6 | idle 145.3, sample 45.6, h2d 15.2, fwd_bwd 79.3, sync 589.2, opt 30.2, loss_read 9.9, publish 0.1 | wait_pack 188.7, weights 7.0, h2d 35.5, forward 161.1, out 21.9, sync 481.0, submit 88.4 |
| 17:50:09 | 9420 | 145367 | 904220 | 925921280 | 177307652 | 943.4 | 715.2 | 70.1 | idle 173.9, sample 45.0, h2d 14.3, fwd_bwd 79.5, sync 584.0, opt 28.7, loss_read 10.1, publish 0.2 | wait_pack 196.8, weights 6.9, h2d 34.9, forward 165.4, out 22.7, sync 480.6, submit 89.4 |
| 17:50:40 | 9479 | 145103 | 904344 | 926048256 | 177371207 | 954.5 | 714.1 | 62.1 | idle 176.8, sample 44.8, h2d 13.4, fwd_bwd 80.2, sync 580.2, opt 30.1, loss_read 9.9, publish 0.1 | wait_pack 199.8, weights 7.0, h2d 35.6, forward 166.6, out 23.5, sync 484.8, submit 91.5 |
| 17:51:10 | 9342 | 143917 | 904466 | 926173184 | 177434081 | 926.5 | 720.2 | 75.1 | idle 156.7, sample 45.2, h2d 15.5, fwd_bwd 77.9, sync 590.0, opt 28.7, loss_read 9.9, publish 0.2 | wait_pack 192.8, weights 6.6, h2d 33.7, forward 159.5, out 22.1, sync 478.1, submit 87.9 |

Deltas (153 s): train_steps 4.05/s, trained_samples 4143/s, samples_added 2075/s; mean 9,451 moves/s, 145.1k pos/s. Aux rows (A): mean 8,581 moves/s, 132.8k pos/s, gpu infer/train 935/685, take_add 187 (17:13 run: 943/711, take_add 70).

### Reading
With --aux-fights, take_add ~70 -> ~187 ms/s, label_s = 13.5 % of wall time; train steps/s 4.05 -> 3.61, samples_added/s -11 %, moves/s 9,451 -> 8,581 (-9 %). GPU time about equal. Fits extra aux labelling in the trainer thread (replay ratio 2 ties self-play to it). Not isolated by A/B.
