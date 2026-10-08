# Synthetic Silver root prior: 32-pair online screen (ledger §399)

- Rules: [PREREG.md](PREREG.md), copied verbatim from
  `/mnt/project-files/silver-synthetic-prior/screen-51937c6a/PREREG.md`, written
  before any screen seed ran.
- Code 51937c6a (PR #449), one_combat sha256 c3547dc4…; prior
  `prior-natpert.compact.txt` sha256 573305c4… (copy in the project folder).
- Arms (bestbench, seeds 56003000..031, A0, fair, keys skipped, flat exact
  budget): A plain 2k (`A-plain2k.csv`), B prior w=400 + 2k (`B-prior2k.csv`),
  C plain 10k (`C-plain10k.csv`). Sidecars record the executable SHA, exact
  root budgets and (B only) the prior path, SHA-256 and weight.
- Run command: `run.sh` in the project folder.
