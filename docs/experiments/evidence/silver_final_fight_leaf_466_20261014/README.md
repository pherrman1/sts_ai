# §466 evidence: final-fight Silver leaf, fight-level replay (2026-10-14)

- Pre-registration: [PREREG.md](PREREG.md) (frozen before any 96M seed; approved by Philipp
  2026-10-14 08:57Z, 8 workers; pre-launch delta review PASS on brief `95dc9901`).
- Run commit `8d8eeb3ceff6ad23399eabfb6d5b8ef34d987146`, Release `one_combat` sha256
  `c92c029705a231a14655266d8815bbc5bbc941590e1b4f4eade32a4bd8a8a5f9` (all 8 workers identical).
- Seeds 96000000-96000255, R = 8, exact 10k, A0, `STS_CTMSILVER_ARMSET=finalleaf`
  ([worker.sh](worker.sh), [BRIEF-worker.md](BRIEF-worker.md)).
- 32/32 shards rc 0; 256/256 sources valid; 236 act-3 boss states; control replay 236/236.
- Raw tars on the project share `/mnt/project-files/silver-leaf-situational/w466-0{1..8}.tar`,
  hashes in [SHA256SUMS](SHA256SUMS), worker DONE files in [DONE-all.txt](DONE-all.txt).
- Frozen analysis [analyze.py](analyze.py) (sha256 `2b98db5f…6629`), output
  [analysis-output.txt](analysis-output.txt).
