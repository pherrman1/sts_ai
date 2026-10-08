# Synthetic Silver root prior: 32-pair online screen (ledger §399)

- Rules: [PREREG.md](PREREG.md), copied verbatim from
  `/mnt/project-files/silver-synthetic-prior/screen-51937c6a/PREREG.md`. It was
  written at launch, before any seed result; it was not committed beforehand,
  and its file is timestamped 1 s after arm A started.
- Code 51937c6a (PR #449), one_combat sha256 c3547dc4…; prior
  `prior-natpert.compact.txt` sha256 573305c4… (copy in the project folder).
- Arms (bestbench, seeds 56003000..031, A0, fair, keys skipped, flat exact
  budget): A plain 2k (`A-plain2k.csv`), B prior w=400 + 2k (`B-prior2k.csv`),
  C plain 10k (`C-plain10k.csv`). Sidecars record the executable SHA, exact
  root budgets and (B only) the prior path, SHA-256 and weight.
- Run command: `run.sh` in the project folder.
- Integration checks before the screen: the LightGBM-to-`combat_policy_trees_v1`
  export matched LightGBM margins exactly (maxAbsMarginError 0.0 on 2,000 edge
  rows; 1,997 trees, 708 features). On 300 §397 test roots the native prior
  matched the offline prior to 1.4e-8, and 300/300 replays were identical.
- Independent review: with the option off, the build reproduces main on all 32
  seeds, and the ledger numbers match these CSVs.
