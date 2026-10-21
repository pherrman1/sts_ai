## Notes
- Shuffle-noise floor: the same recipe with only the shuffle RNG stream shifted moved selection KL by ~0.002 (bench_base vs
  bench_c_valend); seed reruns of the pick differ by ±0.0002.
- Wall times of runs that shared the GPU (ktest K_* runs ran alongside grid points) are inflated.
- bench_b_bs1024 (unpacked bs 1024) hit CUDA OOM and has no summary.
- Weights: d64 students (`student.pt` + native export `student.bin`, `--n-heads 4 --trim-map`) in `weights/`, sha256 in
  `weights/SHA256SUMS`. Not pushed (24 MB each): the T1 teacher, kept on the PC at
  `~/h1distill/gen2/sweep/T1_heart1_lr1e-4_a1_v1_bs256_s0/student.pt` (sha256 `610b509b…`; export `--n-heads 8`, untrimmed,
  sha256 `d42b1c99…` at `~/h1distill/gen2/export/T1_heart1.bin`), and the teacher-labeled rows (`~/h1distill/gen2/teacher_rows`, 2,816 files).
