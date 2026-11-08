# Silver leaf price gate (campaign)

PREREG.md has the design; RESULT.md the result (`result.json`, `analyze.log`, `pairs_P1.csv`, `pairs_PF.csv`). Files: `campaign.manifest`, `units.txt` (2,048 seeds), `run_unit.sh` (arms D, P1, PF per
seed), `analyze.py` (gate, `--self-test`). Share `/mnt/project-files/silver-leaf-price-gate`. Workers:
`bash tools/cloud/worker.sh setup|start docs/experiments/evidence/silver_leaf_price_gate_20261108 W` at RUN_COMMIT.

The offline analysis that chose P1 (leaf plan stage 4 on the §763 pilot) is `../leaf_stage4_offline_fit_20261108/`.

Binary: `worker.sh publish-binary` at code_commit ccc53a48 (preset linux-gcc-release-x86-64-v3) built
c201818cb248cef2… (4 min, incremental) and put it in the bin cache. The run commit must keep ccc53a48's build inputs
(worker.sh checks this), so main is merged into the branch only after the run commit.

Smoke (author container, 2026-11-08 00:39 CET, `run_unit.sh` at ccc53a48 plus these files, binary from the cache):
seed 111829990: D, P1 and PF rc 0 with all checks (losses on floors 23, 29 and 25, about 6 s each); seed 111829991:
D rc 0 (loss on floor 55, 49 s), P1 a Heart kill (66 s), PF a Heart kill (49 s). P1 and PF print the research-leaf
banner `gold=0.12 maxhp=2.4 victoryTurnPenalty=0.4 concave=0 potionWeights=on`, D prints none. `analyze.py
--self-test` OK. Logs: `/mnt/project-files/leaf-plan/stage4/gate-draft/smoke-111829990-991.tgz`.
