# Act-4 CTM label collection (frozen plan)

**Request.** Philipp, 2026-10-17 16:18Z: "run full act 4 label colleciton". This follows the CTM audit at A20
(`/mnt/project-files/audit-2026-10-17/ctm-a20.md`, finding 1). The deployed A20 CTM predicts 0.28 Heart death where
the teacher dies 0.95 (smoke on seeds 111128002–111128401).

**What it produces.** Act-4 rows (Shield and Spear, then the Heart) from the `act4_fork` forced setup (PR #578,
`docs/knowledge-base/operations/ooc-label-pipeline.md`). Each run is sent into Act 4 at its first Act-3 boss, and only
the Act-4 fights are written. This is a separate slice for a later CTM retrain or calibration; the retrain is a
separate decision. No model, default or ledger change is made here.

**Frozen.**
- Code commit: `79263192` (main after #589). The run commit is the commit that adds this folder. `worker.sh setup`
  refuses a checkout whose code paths differ from the code commit.
- Binary: `one_combat` sha256 `5e88ec0a…`, GCC 13 Release preset. `worker.sh setup` refuses any other binary.
- Teacher: `teacher.json` here. It is the Stage-1 A20 learned-stop Silver teacher (`ctm-a20/stage1/teacher.json`)
  with the git sha and the OOC policy specification updated to the current defaults (exported by
  `one_combat vwinrefreshpolicyspec`). Ascension 20, 10000 sims, `STS_CTM_GEN_DEPLOYED_OOC=1`, keys off; the fork
  grants the keys.
- Seeds: 111160000–111169999 (coordinator block). N workers split them evenly into units of 25 seeds, 4 units at a
  time per worker. Smoke: 111157000–111157003 (W=0).
- Expected yield, from the smoke: about 14 CPU-s per seed, 43% of seeds reach Act 4, 1.75 rows per such seed. That is
  about 38 CPU-h and about 7,500 rows.

**Outputs.**
- `/mnt/project-files/ctm-a20/act4-labels/wWW.tar.gz` plus `wWW.DONE.txt`, which carries the tar sha256.
- Every unit's `.jsonl`, `.manifest.json`, `.provenance.json`, `.log` and `.done` file.
- A unit that crashes (for example the known Silver depth-bound abort) is recorded with its rc and is not rerun.

**Split.** Use the corpus adapter's seed-hash split (`combat-transition-model-v1:{seed}`). `noAct4Seeds` are excluded
like quarantined seeds.
