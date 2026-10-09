# Silver root prior at low sim budgets (ledger §406)

- Rules: four pre-registrations, copied verbatim from
  `/mnt/project-files/silver-synthetic-prior/screen-lowsim-51937c6a/`. None was
  committed before its arms ran.
  - [PREREG.md](PREREG.md): 32-seed screen.
  - [PREREG-confirm128.md](PREREG-confirm128.md): 128-seed confirmation.
  - [PREREG-sweep128.md](PREREG-sweep128.md): budget sweep vs plain 10k.
  - [PREREG-tiny128.md](PREREG-tiny128.md): 128/64/32 sims.
- Pre-registration order: only the screen's file (10:18:03 UTC) clearly
  predates its arms. The other three are stamped 5 s after their first arm
  started:
  - confirm128 10:21:47 vs arm 10:21:42;
  - sweep 10:39:09 vs 10:39:04;
  - low budgets 11:53:26 vs 11:53:21.

  The stamps are probably copy times in the shared folder, so they cannot prove
  the order either way. Those three rules were written in the same command that
  launched their arms, before any of their results existed.
- Binary and prior are the same as §399. Code 51937c6a, one_combat sha256
  c3547dc4…, prior `prior-natpert.compact.txt` sha256 573305c4…, weight 400.
  The binary's identity rests on `sha256.txt`, hashed at 10:18 before the
  screen.
- Sidecar `executableGitSha` is not the binary's commit. It records the
  checkout's git HEAD at run time: d4ca7515 for the screen, confirmation and
  sweep, and 0f5adc4e for the low budgets. The binary reads `models/` from that
  checkout. The review checked that `models/v_win_trees.txt` and
  `models/v_rich_trees.txt` are identical at 51937c6a, d4ca7515 and 0f5adc4e,
  so the results are unaffected. The sidecars also record exact root budgets
  and, for the prior arms, the prior path, SHA and weight.
- Run settings: bestbench, A0, fair play, keys skipped, flat exact budgets, 4
  CPUs. Seeds 61000000..031 for the screen and 61001000..127 for the rest.
- Run commands:
  - `run.sh`: screen.
  - `run128.sh`: confirmation, plain/prior 256 and plain 2k.
  - `sweep.sh`: prior 512/1k/2k/4k and plain 10k.
  - `tiny.sh`: 32/64/128.
- CPU s/run is the mean of each CSV's per-run `sec` column, with 4 runs going
  at once (OMP outer parallelism).
- Timing: `wall.txt` and `c128-wall.txt` hold wall seconds per arm.
- Analysis: `python3 analyze.py` prints `analysis.txt`. It gives paired
  differences with seed-bootstrap 95% CIs (10,000 resamples, seed 0).
