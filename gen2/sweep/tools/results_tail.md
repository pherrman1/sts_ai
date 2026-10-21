## Notes
- Shuffle-noise floor: the same recipe with only the shuffle RNG stream shifted moved selection KL by ~0.002 (bench_base vs
  bench_c_valend); seed reruns of the pick differ by ±0.0002.
- Wall times of runs that shared the GPU (ktest K_* runs ran alongside grid points) are inflated.
- bench_b_bs1024 (unpacked bs 1024) hit CUDA OOM and has no summary.
