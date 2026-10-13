# §454 evidence: Silver tree prior cost, batched exact prior scoring

- Baseline binary: `main` `33d03b25` (#508 head), Release preset. New binary: this change on the same
  base, then rebased on `93011ed1` (#508 merge; no Silver code change) and re-checked on 74038000.
- Environment: [env.sh.txt](env.sh.txt) (the §452 `env.sh` with `$RUN` for the run directory;
  74038001–74038002 used `STS_CTMSILVER_ARMSET=treeprior452`). Prior:
  `/mnt/project-files/silver-tree-prior-452/inputs/prior-natpert.compact.txt`
  (sha256 573305c48076c135f791d0712efb03be7e620aeeb961e962700ce2c60188c6ee). Teacher as in §452
  `worker.sh` (`tools/silver_synth_teacher.py` + `vwinrefreshpolicyspec`), one per binary.
- Run: `tools/seed_guard.sh $BIN ctmsilvergen 1 0 $OUT $SEED $TEACHER 1` for seeds 74038000,
  74038001, 74038002; old and new binaries side by side on one 4-core cloud container.
- Parity: `arms.csv` without `cpuSeconds`, `states.csv` columns 1–18 (the rest are CPU), `samples.csv`
  whole; identical for every seed and binary.
- [timing.csv](timing.csv): per run and arm, decisions, CPU and CPU per decision relative to plain 2k.
- Raw outputs: `/mnt/project-files/silver-tree-prior-speedup-454/raw.tar.gz` (sha256 1d78c9325deb2843659e2903871ecd9bf62a0f3f0eaa84ea038b26e89ca3d157).
  File prefixes: `base`/`p_base`/`m_base_*` baseline, `new1` first batched version, `v2`/`v3`/`p_v3`/`m_v3_*`
  later versions (`v3` is this change), `p_v4` the dropped tree-block variant, `final` the rebased binary,
  `prof_*` and `count` profiling builds with one arm only.
