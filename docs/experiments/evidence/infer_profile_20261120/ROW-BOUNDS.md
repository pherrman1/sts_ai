# `--attn-row-bounds` on the PC: output equality, GPU time per batch, live rows (2026-11-20)

`tools/az_bench/infer_profile.py --batches 3` on main 15887f9a (RTX 3060 Ti, torch 2.5.1+cu121, triton 3.1.0), checkpoint
`amber_scratch/ckpt_677517.pt`, rows from the run's saved 10M window, 30 batches per timing. Each variant is timed with
the switch off and on, and the outputs of both settings are compared on the live rows. `tests/test_varlen_attn.py` on
the GPU before it: 4 tests OK. The kernel table that the tool printed in this run is for the switch OFF (the tool
profiles after resetting it), so it is not reproduced here.

| batch | variant | row bucket | token bucket | action bucket | rows | ms / batch, off | ms / batch, on | outputs equal | max abs diff |
|---|---|---|---|---|---|---|---|---|---|
| 0 | real | 2048 | 80 | 32 | 1314 | 4.646 | 3.136 | True | 0.0 |
| 0 | real_Rtight | 1344 | 80 | 32 | 1314 | 3.439 | 2.764 | True | 0.0 |
| 0 | short_T64 | 2048 | 64 | 32 | 1301 | 2.938 | 3.055 | True | 0.0 |
| 0 | short_Tbig | 2048 | 80 | 32 | 1301 | 4.258 | 3.17 | True | 0.0 |
| 0 | uniform | 2048 | 40 | 32 | 1304 | 3.106 | 3.143 | True | 0.0 |
| 1 | real | 2048 | 96 | 32 | 1314 | 4.332 | 3.261 | True | 0.0 |
| 1 | real_Rtight | 1344 | 96 | 32 | 1314 | 3.453 | 2.777 | True | 0.0 |
| 1 | short_T64 | 2048 | 64 | 32 | 1287 | 2.956 | 3.05 | True | 0.0 |
| 1 | short_Tbig | 2048 | 96 | 32 | 1287 | 4.281 | 3.183 | True | 0.0 |
| 1 | uniform | 2048 | 40 | 32 | 1314 | 2.944 | 3.036 | True | 0.0 |
| 2 | real | 2048 | 96 | 96 | 1314 | 5.412 | 4.289 | True | 0.0 |
| 2 | real_Rtight | 1344 | 96 | 96 | 1314 | 3.987 | 3.288 | True | 0.0 |
| 2 | short_T64 | 2048 | 64 | 96 | 1286 | 3.664 | 3.766 | True | 0.0 |
| 2 | short_Tbig | 2048 | 96 | 96 | 1286 | 5.005 | 3.877 | True | 0.0 |
| 2 | uniform | 2048 | 40 | 96 | 1299 | 3.716 | 3.797 | True | 0.0 |

Means over the three batches: real 4.797 -> 3.562 ms; real without empty rows 3.626 -> 2.943; short rows in bucket 64
3.186 -> 3.290; the same rows in the batch's bucket 4.515 -> 3.410; uniform 3.255 -> 3.325.

## Live run after the restart with the switch (relayed by the run's thread)

# #1135 --attn-row-bounds live check, amber_scratch 2026-11-20

PID 2457476 since 17:37:57 CET, c4_repo @15887f9a, ckpt_677517, all previous flags + --attn-row-bounds (also wd envs). Replay 10M, A0, savescum off, pin [5,11].
Tests: test_varlen_attn.py 4/4 OK (Ran 4 tests in 3.014s). infer_profile --batches 3: row_bounds_equal true in all rows, max_diff 0.0; real 4.80 -> 3.56 ms/batch (-26 %), no gain on T64/uniform.
Health: stalls 0, invalid 0, kf 0, nonfinite 0; loss policy 1.00 / outcome 1.17; grad_norm mean 8.0 / max 36.9; trained/added 1.998.
Throughput 17:43-17:50: moves/s 11,355, pos/s 221,201 (c6225d67: ~10,100 / ~196k => +12-13 %). infer forward ~298 ms/s.
dmon -s u -c 30 (17:50-17:51): SM mean 80.0 % (min 2, max 96), mem 58.0 %.
Real winrate since 17:43: 29.5 % (7,716 runs); floor 52.0; MemAvail 4.0 GB.

## 6 rows (17:47:43-17:50:14)
```
{"time":"17:47:43","moves_per_s":10972,"positions_per_s":215488,"infer_batches_per_s":168.4,"infer_rows_per_batch":1278.7,"infer_tokens_per_row":36.82,"infer_tok_bucket_batches":{"48":1,"56":1,"64":4,"80":3217,"96":1872},"infer_ms_per_s":{"wait_pack":478.5,"weights":8.7,"h2d":40.4,"forward":285.3,"out":33.7,"sync":103.1,"submit":47.3},"train_ms_per_s":{"take_add":58.6,"idle":417.5,"sample":40.8,"h2d":48.7,"fwd_bwd":115.5,"sync":288.1,"opt":29.7,"loss_read":1.3,"publish":0.3},"gpu_ms_per_s":{"infer":785.3,"train":482.4},"worker_cpu_s_per_s":{"search":6.37,"step":2.699,"encode":1.487},"trained_samples":695669760,"samples_added":62181910}
{"time":"17:48:13","moves_per_s":10965,"positions_per_s":214809,"infer_batches_per_s":167.9,"infer_rows_per_batch":1280.0,"infer_tokens_per_row":35.93,"infer_tok_bucket_batches":{"56":1,"64":1,"80":2488,"96":2587},"infer_ms_per_s":{"wait_pack":459.0,"weights":8.7,"h2d":41.3,"forward":287.8,"out":34.5,"sync":119.0,"submit":47.5},"train_ms_per_s":{"take_add":65.6,"idle":327.2,"sample":47.4,"h2d":53.4,"fwd_bwd":136.6,"sync":333.2,"opt":33.9,"loss_read":1.4,"publish":0.4},"gpu_ms_per_s":{"infer":792.6,"train":557.5},"worker_cpu_s_per_s":{"search":6.215,"step":2.646,"encode":1.456},"trained_samples":695840768,"samples_added":62267706}
{"time":"17:48:44","moves_per_s":10593,"positions_per_s":207678,"infer_batches_per_s":162.7,"infer_rows_per_batch":1278.5,"infer_tokens_per_row":34.78,"infer_tok_bucket_batches":{"48":1,"64":7,"80":2521,"96":2159,"128":234},"infer_ms_per_s":{"wait_pack":466.0,"weights":8.8,"h2d":41.2,"forward":287.8,"out":34.5,"sync":113.9,"submit":47.0},"train_ms_per_s":{"take_add":67.9,"idle":287.9,"sample":50.9,"h2d":62.1,"fwd_bwd":144.6,"sync":350.9,"opt":36.0,"loss_read":1.5,"publish":0.5},"gpu_ms_per_s":{"infer":775.1,"train":595.0},"worker_cpu_s_per_s":{"search":5.974,"step":2.554,"encode":1.369},"trained_samples":696024064,"samples_added":62359621}
{"time":"17:49:14","moves_per_s":10938,"positions_per_s":212700,"infer_batches_per_s":166.1,"infer_rows_per_batch":1281.8,"infer_tokens_per_row":33.74,"infer_tok_bucket_batches":{"48":2,"56":2,"64":7,"80":1319,"96":3033,"128":668},"infer_ms_per_s":{"wait_pack":461.2,"weights":8.9,"h2d":42.2,"forward":292.5,"out":34.7,"sync":110.3,"submit":48.1},"train_ms_per_s":{"take_add":64.0,"idle":292.7,"sample":50.6,"h2d":57.3,"fwd_bwd":147.6,"sync":349.4,"opt":36.2,"loss_read":1.2,"publish":0.3},"gpu_ms_per_s":{"infer":775.8,"train":589.4},"worker_cpu_s_per_s":{"search":6.008,"step":2.591,"encode":1.373},"trained_samples":696210432,"samples_added":62452676}
{"time":"17:49:44","moves_per_s":11146,"positions_per_s":216506,"infer_batches_per_s":169.1,"infer_rows_per_batch":1280.2,"infer_tokens_per_row":32.81,"infer_tok_bucket_batches":{"64":5,"80":1853,"96":2866,"128":399},"infer_ms_per_s":{"wait_pack":463.9,"weights":8.8,"h2d":41.8,"forward":292.1,"out":34.9,"sync":108.7,"submit":47.7},"train_ms_per_s":{"take_add":64.5,"idle":317.5,"sample":49.3,"h2d":54.1,"fwd_bwd":146.5,"sync":332.5,"opt":35.1,"loss_read":1.2,"publish":0.6},"gpu_ms_per_s":{"infer":776.1,"train":569.6},"worker_cpu_s_per_s":{"search":6.143,"step":2.673,"encode":1.372},"trained_samples":696388608,"samples_added":62541893}
{"time":"17:50:14","moves_per_s":11518,"positions_per_s":224847,"infer_batches_per_s":176.7,"infer_rows_per_batch":1271.3,"infer_tokens_per_row":32.6,"infer_tok_bucket_batches":{"64":3,"80":3069,"96":2286},"infer_ms_per_s":{"wait_pack":476.6,"weights":9.1,"h2d":43.0,"forward":299.3,"out":36.0,"sync":84.7,"submit":48.3},"train_ms_per_s":{"take_add":52.8,"idle":448.2,"sample":39.3,"h2d":50.0,"fwd_bwd":115.6,"sync":264.0,"opt":28.5,"loss_read":1.0,"publish":0.4},"gpu_ms_per_s":{"infer":756.9,"train":456.3},"worker_cpu_s_per_s":{"search":6.362,"step":2.767,"encode":1.423},"trained_samples":696531968,"samples_added":62613496}
```
Profile JSON/log (infer_profile_rb_20261120.*) follow when received.
