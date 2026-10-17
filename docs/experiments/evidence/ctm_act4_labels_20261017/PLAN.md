# Act-4 CTM label collection (frozen plan)

**Request.** Philipp, 2026-10-17 16:18Z: "run full act 4 label colleciton". This follows the CTM audit at A20
(`/mnt/project-files/audit-2026-10-17/ctm-a20.md`, finding 1). The deployed A20 CTM predicts 0.28 Heart death where
the teacher dies 0.95 (smoke on seeds 111128002–111128401).

**What it produces.** Act-4 rows (Shield and Spear, then the Heart) from the `act4_fork` forced setup (PR #578,
`docs/knowledge-base/operations/ooc-label-pipeline.md`). Each run is sent into Act 4 at its first Act-3 boss, and only
the Act-4 fights are written. This is a separate slice for a later CTM retrain or calibration; the retrain is a
separate decision. No model, default or ledger change is made here.

**Frozen.**
- Code commit: `d4787812` (main `818d3331` merged into this branch, which carries the student C shop-index fix #579,
  the key filter #611 and student C Match and Keep with the curse fix #616, plus the generator fix that lets
  `STS_OOC_HEART1` play deployed-OOC screens and the default-off #609 options). The run commit is the commit that adds this folder. `worker.sh setup`
  refuses a checkout whose code paths differ from the code commit.
- Binary: `one_combat` sha256 `9fd50586…`, GCC 13 Release preset. `worker.sh setup` refuses any other binary.
- Teacher: `teacher.json` here. It is the Stage-1 A20 learned-stop Silver teacher (`ctm-a20/stage1/teacher.json`)
  with the git sha and the OOC policy specification updated to the current defaults (exported by
  `one_combat vwinrefreshpolicyspec`). Out of combat, student C (`STS_OOC_HEART1=build/studentc.bin`, sha256
  `eff2f74f…`, copied from `/mnt/project-files/student-c-488/` and checked by `worker.sh setup`) takes every screen it
  encodes; the deployed step plays the rest. Re-frozen 2026-10-17 after the pre-launch review: Philipp chose student C
  over the V4 chain at 17:11Z (his 16:05Z rule: OOC = student C in A20 harnesses). Ascension 20, 10000 sims, `STS_CTM_GEN_DEPLOYED_OOC=1`, keys off; the fork
  grants the keys. Student C may still take keys before the fork (the #611 mask applies only with keys on); the fork at
  the Act-3 boss re-grants all three (idempotent) either way, so only the cost of that key play shows in the Act-4 entry
  state.
- Seeds: 111160000–111169999 (coordinator block). N workers split them evenly into units of 25 seeds, 4 units at a
  time per worker; production workers are W=1..N. W=0 is only the smoke: 111157000–111157003.
- Student C smoke at the earlier code `25270409` (111157000–003): 26 CPU-s per seed, 2 of 4 seeds reach Act 4, 4 rows,
  484 student C steps and 0 deployed-step screens. Cost at that rate: about 72 CPU-h. Earlier V4-chain smoke: about 14 CPU-s per seed, 43% of seeds reach Act 4, 1.75 rows per such seed. That is
  about 38 CPU-h and about 7,500 rows.

**Outputs.**
- `/mnt/project-files/ctm-a20/act4-labels/wWW.tar.gz` plus `wWW.DONE.txt`, which carries the tar sha256.
- Every unit's `.jsonl`, `.manifest.json`, `.provenance.json`, `.log` and `.done` file.
- A unit that crashes (for example the known Silver depth-bound abort) is recorded with its rc and is not rerun.

**Split.** Use the corpus adapter's seed-hash split (`combat-transition-model-v1:{seed}`). `noAct4Seeds` are excluded
like quarantined seeds.
