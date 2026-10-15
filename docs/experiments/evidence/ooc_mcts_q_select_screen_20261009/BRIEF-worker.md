# OOC MCTS root-selection × cpuct screen: cloud worker W (W = 1..32; WW = W zero-padded, e.g. 07)

Philipp authorized this run (2026-10-09 17:42Z): 128 paired seeds, 8 arms (pick by visits vs pick by Q, each at
cpuct 0.5 / 1.0 / 1.5 / 3.0), on 32 cloud workers × 4 CPU. It is the pre-registered screen
`/mnt/project-files/ooc-mcts-q-select-screen/PREREG.md`. Do not change seeds, scripts, environments, binary or arms.
Write only to `/mnt/project-files/ooc-mcts-q-select-screen/wWW/` (the script does this). The smoke already ran on
worker 1's setup; every worker's `run` waits for `SMOKE_PASS` and stops on `SMOKE_FAIL`.

## 1. Check out the build commit, copy and verify the script, set up (~5–10 min; the LTO link is serial)

```sh
cd /home/user/sts_ai
git status --porcelain --untracked-files=no     # must be empty; stop otherwise
git fetch origin claude/new-ctm-stack-8h7edy   # holds the build commit
git checkout --detach 648334e38dc5c92bc57a9b531f2f9f3308a732ff
git submodule update --init --recursive
cp /mnt/project-files/ooc-mcts-q-select-screen/worker.sh $HOME/qscreen-worker.sh
sha256sum $HOME/qscreen-worker.sh /mnt/project-files/ooc-mcts-q-select-screen/{PREREG.md,analyze.py}
#   54763c3dbc4e92cb25f4fafdf90da304906d4e97fe5ff231729113fa942679e7  worker.sh
#   39bb4ec34a118ae3f6394e48c4666d45fca97726e8942ba0252a82a4cb6ca103  PREREG.md
#   a3f6ccd5fd9f6d31767df6b1863979ac7e2d7730f2e31db377f83b8485c46240  analyze.py
bash $HOME/qscreen-worker.sh setup W
```
`setup` builds `one_combat`, checks
its sha256 `dddb09f0…`, the model and candidate-CTM hashes, and writes `wWW/FROZEN.txt`. Any `STOP:` line means stop
and report it verbatim.

## 2. Run (detached, ~20–30 min)

```sh
setsid nohup bash $HOME/qscreen-worker.sh run W > $HOME/qscreen-wWW.run.log 2>&1 < /dev/null &
```
It runs your 16 units (2 seeds × one arm each), 4 at a time, and writes `wWW/DONE.txt` when all are done. Check every
10 minutes with `bash $HOME/qscreen-worker.sh status W` (keep the session alive until DONE.txt exists).

## 3. Stalls, crashes, restarts

* A Silver stall caught by bestbench (`[bestbench-seed-failure]`, unit rc=1) or a unit timeout is allowed; do not rerun
  or replace seeds.
* Any other nonzero rc or crash: do not retry; report the unit's `.done` line and the end of its `.log`.
* After a container restart: redo step 1, then step 2. Finished units are skipped; an unfinished unit reruns whole.
  Never delete anything in `wWW/`.

## 4. Report

Reply in your thread with the first line of `wWW/FROZEN.txt` and the content of `wWW/DONE.txt`. Do not analyze; the
"New CTM stack" thread runs the analysis.
