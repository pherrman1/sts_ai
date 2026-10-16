# Arm C native campaign: platform qualification (synthetic data only), 2026-10-16

No game seed, canary, fit or TEST was run. Lead container = this thread's cloud session.

## Producer
- Source checkout 16a081c9 (PR567 head); C++/CMake diff vs scientific source 9d83adbb is empty.
- Ubuntu GCC 13.3.0, CMake 3.28.3, preset linux-gcc-release, `--target one_combat --parallel 4`, rc 0, 237 s.
- one_combat sha256 86a7569fe56cfdd2f635018147f005b16870598c53c7c164a5d1edd994ecbacf
  = the ORIGINAL local producer hash from the handoff (byte-identical rebuild, verified by bytes).
- studentc.bin: share copy /mnt/project-files/student-c-488/studentc.bin, sha256 eff2f74f…6509 (= required native hash).
  Not re-exported from the git checkpoint (Philipp 10:28Z: use the share copy).
- `one_combat heart1score` on the PR567 synthetic record: output byte-identical to Codex's AMD EPYC/GCC14 binary
  (argmax 1, logits -4.291018962860107, 2.057094097137451, -12.844468116760254; value -0.0002696537412703037).

## Capacity (per cloud thread)
- 4 vCPU (KVM), 1 thread/core, affinity 0-3, 15 GiB RAM, no swap, no cgroup cpu/memory limit visible (cgroup v1),
  ~24 GB free local disk. CPU types differ between threads: lead Intel Xeon @2.1GHz (model 207), coordinator worker
  Intel Xeon @2.8GHz, Codex preflight AMD EPYC 9V74.
- Synthetic single-thread CPU spin (same work each): 1 process 7.40 s; 2 concurrent 7.83/8.63 s; 4 concurrent
  8.44-8.78 s (+14-19%). Sources are single-threaded (OMP_NUM_THREADS=1).
- Project limit ~49 running sessions -> 64 one-source workers impossible; 32 workers x 2 concurrent sources fits.

## Export
- Wrote synthetic 1 KB / 50 MiB / 300 MiB random files + a sealed tar to arm-c-native-qual/synthetic-20261016/
  (300 MiB upload 3.6 s). A separate container (coordinator's Agent worker, 10:11:06Z) read all four back with
  matching sha256.
- Share usage before test: 6.2 GB of the 10 GB quota (≈3.8 GB free; full quota drops uploads silently).
- O_EXCL create is exclusive within one container; cross-container atomicity on rclone is NOT guaranteed.

## Lifetime
- Containers are reclaimed when a turn ends with no background task (seen 2026-10-10). Background Bash tasks are
  capped at ~2 h -> worker brief must keep a re-armed watcher and a keep-alive until a release file exists.
- Not measured: a guaranteed maximum session lifetime. Each unit is <=3600 s + ~5 min build, inside one watcher.

## Decisions and execution design (pending independent review)
- Interruption rule (Philipp, decision card 10:33Z): a source whose attempt ends without a share receipt
  (process or container lost) is rerun whole once inside the same deadline, after any orphaned producer group of
  the earlier attempt is killed. Partial outputs move to `interrupted-attemptN/` and enter the rerun's archive only
  when the local disk survived; a lost container loses them. A source with a share receipt (any rc, including 124)
  is never rerun.
- Execution: `tools/heart_distill_native_worker.py` (bundle / deadline / unit / canary / worker). Plan uses
  contiguous split-pure blocks; proposed 32 workers x 2 concurrent sources. Each source's outputs are exported as
  `sources/seed-N.attemptA[-SEALED].tar.gz` (sealed for TEST, names/hashes only) BEFORE its share receipt, so a
  receipt implies its data. One `deadline.json` is created once (O_EXCL) by the lead and only if `canary.json`
  has `gatePass: true`.
- Workers are launched by the project coordinator as Haiku threads (Philipp, 10:33Z).
