# Heart-outcome round 2 worker W (§503; W = 0..31, unpadded: 3, never 03; WW = two digits: 03)

Philipp authorized this collection (2026-10-17 08:23Z: "Do A+S on 32 workers") with Haiku workers. Worker W runs its 64 fixed sources
(the plan assigns them; seeds from 111101000), four at a time, under one shared deadline. The coordinator's header
gives you W, ACT (the approved activation SHA256) and, only for a lost-worker rerun, H (0 or 1). Everything (build,
hash checks, timeouts, receipts, sealed archives, export to the share) is done by the script. Do not change seeds,
scripts, environment variables, the binary, timeouts or thresholds. Do not edit repository files. Do not open,
unpack or analyze any result file or archive. Write nothing to the share yourself. Never rerun a source or the worker.

## Step 1a. Check out the run commit (local repository only). Foreground Bash:
```sh
cd /home/user/sts_ai
git fetch origin claude/project-thread-72g9pa
git status --porcelain --untracked-files=no
git checkout --detach __RUN_COMMIT__
git rev-parse HEAD
```
`git status` must print nothing and `git rev-parse HEAD` must print `__RUN_COMMIT__`.

## Step 1b. Local build (about 10 min). Separate foreground Bash call, timeout 1800000 ms:
```sh
cd /home/user/sts_ai; bash docs/experiments/evidence/heart_outcome_round2_20261017/cloud_worker.sh setup W
```
Setup is local-only: it clones and builds the frozen producer under $HOME and checks the binary hash. It does not
read or write the project share; its only network use is fetching the pinned public submodules (json, pybind11).
The last line must start with `setup ok: W=`. If any line starts with `STOP:` or a command fails: reply with the
full output verbatim, then go to step 5's keep-alive (do not run step 2).

## Step 2. Start (foreground Bash call, returns at once):
This is the only step that writes to the project share, and only into this worker's own new delivery folder
/mnt/project-files/heart-outcome-round2/deliveries/wWW (rWW-H for a rerun half), which is how the plan has workers
hand results to the lead. It reads the approved activation files and the frozen model weights (read-only copy
/mnt/project-files/student-c-488/studentc.bin) from the share and checks their hashes.
```sh
cd /home/user/sts_ai; setsid nohup bash docs/experiments/evidence/heart_outcome_round2_20261017/cloud_worker.sh run W ACT > $HOME/heart2-run.log 2>&1 < /dev/null &
```
(Rerun half only: append ` H` after `ACT`.)

## Step 3. Mandatory watcher, re-armed until finished
The container is reclaimed when no background task runs, which would kill the sources. Right after step 2, start
this with `run_in_background: true` and `timeout: 7200000`:
```sh
until grep -qE "WORKER_OK|STOP:" $HOME/heart2-wWW/worker.log $HOME/heart2-run.log 2>/dev/null; do sleep 60; done; echo WATCHER_END; tail -3 $HOME/heart2-wWW/worker.log; tail -3 $HOME/heart2-run.log
```
If it ends any other way (time limit, killed): start the same watcher again at once. Never kill one_combat, python
or the script, however long it runs (each source stops itself after at most 1 h; the whole worker typically takes
3-4 h). Progress: `cd /home/user/sts_ai; bash docs/experiments/evidence/heart_outcome_round2_20261017/cloud_worker.sh status W`.

## Step 4. Container restart
If `$HOME/heart2-wWW` is missing or the run processes are gone without WORKER_OK/STOP: do NOT redo any step. Reply
with `ls -la $HOME; cat $HOME/heart2-run.log` output and go to step 5's keep-alive. Lost work is never rerun here.

## Step 5. Report and keep alive
Reply in your thread with the watcher output verbatim (also the `setup ok` line from step 1). Then keep this running
with `run_in_background: true` and `timeout: 7200000`, re-armed whenever it ends, until the lead thread or the
coordinator tells you that you can stop:
```sh
until [ -f $HOME/heart2-wWW.release ]; do sleep 60; done
```
