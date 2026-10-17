# Heart leaf A20 A/B (§522): cloud worker W (W = 1..8)

Pass W UNPADDED to worker.sh (run 3, never 03); WW (zero-padded, e.g. 03) appears only in file names.

Philipp authorized this run (2026-10-17 19:59Z: "yes lets try a parid a20 a/b."; card 20:03Z: 512 pairs on 8 workers). It is the
pre-registered run `docs/experiments/evidence/heart_leaf_ab_20261017/PLAN.md` on branch
`claude/project-thread-3sp8qo`, run commit **__RUN_COMMIT__**.
Do not change seeds, scripts, environments, binary, weights, timeouts or thresholds. Run nothing from
`/mnt/project-files` (it is noexec). Units write to your local disk; at the end the script uploads exactly two files to
the share: `/mnt/project-files/heart-leaf-td/ab/wWW.tar.gz` and then `wWW.DONE.txt`. Write nothing else to the share.

## 1. Check out the run commit and build (~10 min)

```sh
cd /home/user/sts_ai
git fetch origin claude/project-thread-3sp8qo
git status --porcelain --untracked-files=no     # must be empty; stop otherwise
git checkout --detach __RUN_COMMIT__
git submodule update --init --recursive
bash docs/experiments/evidence/heart_leaf_ab_20261017/worker.sh setup W
```
`setup` builds `one_combat`, checks its sha256 (`binary.sha256` in that folder), checks the Heart leaf model files (`heart_leaf.sha256`), copies
`studentc.bin` from `/mnt/project-files/heart-leaf-td/ab-weights/` and checks its sha256 (`weights.txt`), and writes
`$HOME/hlab-wWW/out/FROZEN.txt` and a 128-line `units.txt`. Any `STOP:` line means stop and report it verbatim.
Do not build anything else while the run is going (a parallel build can get the container OOM-restarted).

## 2. Run (about 4 h). THE RUN SCRIPT, started detached:

```sh
cd /home/user/sts_ai; setsid nohup bash docs/experiments/evidence/heart_leaf_ab_20261017/worker.sh run W > $HOME/hlab-wWW.run.log 2>&1 < /dev/null &
```
It runs your 64 seeds of A20 111191000–111191511 (split into 8 contiguous blocks) in the arms `C` and `H`,
4 units at a time, then uploads the tar and the DONE file.

**Mandatory watcher, re-armed until DONE.** Your results stay on local disk until the very end, and the container is
reclaimed when no background task is running, which would lose them. Right after starting the run, start this with
the Bash tool's `run_in_background: true` and the maximum timeout:
```sh
until [ -f /mnt/project-files/heart-leaf-td/ab/wWW.DONE.txt ] || grep -q "STOP:" $HOME/hlab-wWW.run.log; do sleep 60; done
```
Whenever the watcher ends without the DONE file or a `STOP:` line (time limit or killed), start it again at once
with the same command; the run keeps going. Never end your turn without a watcher running, until you have reported
(step 4) and been told you can stop. Check progress every 15–20 min with
`cd /home/user/sts_ai; bash docs/experiments/evidence/heart_leaf_ab_20261017/worker.sh status W`.

## 3. Slow units, stalls, crashes, restarts

* **Never kill a unit, a `one_combat` process or the run script**, however long it takes. Each unit has a 4 h
  timeout; if it fires, the unit ends with `rc=124` in its `.done` line and the run continues. Allowed; the analysis
  drops that seed. Do not rerun or replace it.
* A Silver stall in a live combat is caught per seed by `bestbench` (`[bestbench-seed-failure]`, unit rc=1).
  Allowed; do not rerun or replace the seed.
* Any other nonzero rc, crash, or a `STOP:` line in the run log: do not retry; report the unit's `.done` line or the
  `STOP:` line and the end of the relevant log.
* After a container restart: redo step 1, then step 2 (same commands). Finished local units are skipped; an
  interrupted one is moved to `out/aborted-<UTC>/` and rerun whole.

## 4. Report

Reply in your thread with the first line of `out/FROZEN.txt` and the content of the share's `wWW.DONE.txt` without
the per-CSV sha256 lines (keep `tar_sha256`), plus every `.done` line whose rc is not 0 and any
`[bestbench-seed-failure]` lines. Keep your session alive (the watcher) until the planning thread or coordinator
confirms the tar is readable from another container. Do not analyze.
