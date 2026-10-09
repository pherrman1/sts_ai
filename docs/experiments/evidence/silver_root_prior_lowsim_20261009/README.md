# Silver root prior at low sim budgets (ledger §406)

- Rules: four pre-registrations, copied verbatim from
  `/mnt/project-files/silver-synthetic-prior/screen-lowsim-51937c6a/`. Each was
  written before its arms ran (file times 10:18, 10:21, 10:39 and 11:53 UTC on
  2026-10-09), but none was committed beforehand.
  - [PREREG.md](PREREG.md): 32-seed screen.
  - [PREREG-confirm128.md](PREREG-confirm128.md): 128-seed confirmation.
  - [PREREG-sweep128.md](PREREG-sweep128.md): budget sweep vs plain 10k.
  - [PREREG-tiny128.md](PREREG-tiny128.md): 128/64/32 sims.
- Binary and prior are the same as §399. Code 51937c6a, one_combat sha256
  c3547dc4…, prior `prior-natpert.compact.txt` sha256 573305c4…, weight 400
  (`sha256.txt`). The sidecars record the executable SHA, exact root budgets
  and, for the prior arms, the prior path, SHA and weight.
- Run settings: bestbench, A0, fair play, keys skipped, flat exact budgets, 4
  CPUs. Seeds 61000000..031 for the screen and 61001000..127 for the rest.
- Run commands:
  - `run.sh`: screen.
  - `run128.sh`: confirmation, plain/prior 256 and plain 2k.
  - `sweep.sh`: prior 512/1k/2k/4k and plain 10k.
  - `tiny.sh`: 32/64/128.
- Timing: `wall.txt` and `c128-wall.txt` hold wall seconds per arm.
- Analysis: `python3 analyze.py` prints `analysis.txt`. It gives paired
  differences with seed-bootstrap 95% CIs (10,000 resamples, seed 0).
