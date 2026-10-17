# heart1 card-select capture: cloud worker W (W = 1..8; WW = W zero-padded, e.g. 07)

Philipp authorized this run on 2026-10-17 17:28Z ("64 seeds"). It collects OOC MCTS prior-call states, and the card
selects their sources open, labelled by heart1, for re-distilling student C. It is not a gameplay A/B; workers do
not analyze anything.

Frozen provenance (see `PLAN.md`): code commit = `CODE_COMMIT`, `one_combat` sha256 = `binary.sha256` (checked by
`setup`), weights in `weights.txt` (copied from the share and checked), env = `arm_env.sh` mode `cap`, seeds =
`COHORTS` (A20 111156100–111156163; worker W runs 8 contiguous seeds).

Do not change seeds, scripts, environments, binary, weights or timeouts. Run nothing from `/mnt/project-files` (it is
noexec). Units write to local disk. At the end the script uploads exactly two files:
`/mnt/project-files/heart1-select-capture/wWW.tar.gz`, then `wWW.DONE.txt`. Write nothing else to the share.

## 1. Check out the run commit and build (~10 min)

```sh
cd /home/user/sts_ai
git fetch origin claude/project-thread-x8e25h
git status --porcelain --untracked-files=no     # must be empty; stop otherwise
git checkout --detach RUN_COMMIT                # given in your brief header
git submodule update --init --recursive
bash docs/experiments/evidence/heart1_select_capture_20261017/worker.sh setup W
```
If any `STOP:` line appears, stop and report it verbatim.

## 2. Run (expected ~1–1.5 h). Start detached:

```sh
cd /home/user/sts_ai; setsid nohup bash docs/experiments/evidence/heart1_select_capture_20261017/worker.sh run W > $HOME/h1sel-wWW.run.log 2>&1 < /dev/null &
```
**The watcher is mandatory and must be re-armed until DONE** (the container is reclaimed when no background task
runs). Right after starting, run with the Bash tool's `run_in_background: true` and the maximum timeout:
```sh
until [ -f /mnt/project-files/heart1-select-capture/wWW.DONE.txt ] || grep -q "STOP:" $HOME/h1sel-wWW.run.log; do sleep 60; done
```
Whenever it ends without the DONE file or a `STOP:` line, start it again at once. Check progress every 15–20 min with
`bash docs/experiments/evidence/heart1_select_capture_20261017/worker.sh status W`.

## 3. Slow units, stalls, crashes, restarts

- Never kill a unit, a `one_combat` process or the run script. A unit's 4 h timeout ends it with `rc=124`; that is
  allowed, do not rerun it. A `[bestbench-seed-failure]` (rc=1) is allowed too.
- Any other nonzero rc, a crash or a `STOP:` line: do not retry; report the `.done` or `STOP:` line and the log tail.
- After a container restart, redo step 1, then step 2. Finished units are skipped; an interrupted unit is moved to
  `out/aborted-<UTC>/` and rerun whole.

## 4. Report

Reply in your thread with: the first line of `out/FROZEN.txt`; the share's `wWW.DONE.txt` without the per-file sha256
lines (keep `tar_sha256`); every `.done` line whose rc is not 0; any `[bestbench-seed-failure]` lines. Keep the
watcher alive until told the tar was verified and you can stop.
