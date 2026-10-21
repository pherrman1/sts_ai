## Notes
- Shuffle-noise floor: the same recipe with only the shuffle RNG stream shifted moved selection KL by ~0.002 (bench_base vs
  bench_c_valend); seed reruns of the pick differ by ±0.0002.
- Wall times of runs that shared the GPU (ktest K_* runs ran alongside grid points) are inflated.
- bench_b_bs1024 (unpacked bs 1024) hit CUDA OOM and has no summary.
- Weights: d64 students (`student.pt` + native export `student.bin`, `--n-heads 4 --trim-map`) in `weights/`, sha256 in
  `weights/SHA256SUMS`. Not pushed (24 MB each): the T1 teacher, kept on the PC at
  `~/h1distill/gen2/sweep/T1_heart1_lr1e-4_a1_v1_bs256_s0/student.pt` (sha256 `610b509b…`; export `--n-heads 8`, untrimmed,
  sha256 `d42b1c99…` at `~/h1distill/gen2/export/T1_heart1.bin`), and the teacher-labeled rows (`~/h1distill/gen2/teacher_rows`, 2,816 files).

## Native parity (bar ≤ 1e-4)
`one_combat` Release built in the sweep clone at `41e3a2ac` (json/pybind11 pointed at the pinned 2222d386 / 63d627c5 checkouts,
since main commits them as dangling symlinks); 400 records = gen 1's `parity/records.jsonl` (sha256 `f8ff5778…`).
torch: `student_inputs.py score SILVERBOT student.pt records.jsonl torch.jsonl --trim-map`; native:
`STS_OOC_HEART1_WING_BOOTS_COUNTER=1 one_combat heart1score student.bin records.jsonl native.jsonl`. Files in `parity/`.

| net | .bin sha256 | records | logits | max abs Δ logit | max abs Δ value | argmax mismatches |
|---|---|---|---|---|---|---|
| pick S_d64L2_lr1e-4_a0.3_v0.3_s0 | `fc32d8f4…` | 400 | 1,652 | 9.54e-6 | 1.31e-6 | 0 |
| backup (value-leaf) S_d64L2_lr1e-4_a1_v1_s0 | `624951eb…` | 400 | 1,652 | 1.24e-5 | 1.88e-6 | 0 |
| T3_distill_d64L2_lr3e-4_a0_v1_s0 | `3088ccd0…` | 400 | 1,652 | 8.58e-6 | 1.49e-6 | 0 |
