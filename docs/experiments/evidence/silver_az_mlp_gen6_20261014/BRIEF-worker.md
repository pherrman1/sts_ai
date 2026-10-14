# Silver AZ MLP loop, generation-6 self-play: cloud worker W (W = 1..8; WW = W zero-padded, e.g. 03)

Philipp requested this run (2026-10-14 11:14Z "Yeh let's do gen 6 with 40k", answering "gen 6 at 40k ... on
8 workers"). Design: `/mnt/project-files/silver-az-mlp/PLAN.md` §2.2-2.3; config `/mnt/project-files/silver-az-mlp/gen6/FROZEN.md`.
Run commit **f73e6ad709439ceb5c39164ae07836339dd20c92** (main). N = 8. Data generation only: do no analysis,
do not post to GitHub, do not change seeds, scripts, environment, binary or settings. Run nothing from
`/mnt/project-files` (noexec). The run writes to your local disk; at the end you upload exactly two files:
`/mnt/project-files/silver-az-mlp/gen6/wWW.tar` and then `/mnt/project-files/silver-az-mlp/gen6/wWW.DONE.txt`. Write nothing else there. The smokes already passed.

## 1. Check out, build, copy the scripts (~10 min)

```sh
cd /home/user/sts_ai
git fetch origin main
git status --porcelain --untracked-files=no     # must be empty; stop otherwise
git checkout --detach f73e6ad709439ceb5c39164ae07836339dd20c92
git submodule update --init --recursive
cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4
cp /mnt/project-files/silver-az-mlp/gen6/worker.sh $HOME/gen6-worker.sh
cp /mnt/project-files/silver-az-mlp/gen6/env.sh $HOME/gen6-env.sh
sha256sum $HOME/gen6-worker.sh   # must be fa24e5e3b234db73c61de4f75f00ff9860963678119a2a850463678e2c30665e; stop otherwise
sha256sum $HOME/gen6-env.sh      # must be b9e62ec5fce56c3b6c1e703d12176ef71b3f25bf1ba3de7aec7eff664bd23370; stop otherwise
```

## 2. Run (about 3.5-4 h with N = 8). Seeds: natural 97000000-97000511, perturbed 97001000-97001511, 256 units of 4; you take 32 units.

```sh
W=<your W>; WW=$(printf %02d $W)
echo "FROZEN commit=f73e6ad709439ceb5c39164ae07836339dd20c92 W=$W N=8 seeds=97000000-511,97001000-511 units=256 per=4 sims=40000 worker=fa24e5e3b234db73c61de4f75f00ff9860963678119a2a850463678e2c30665e" > $HOME/gen6-w$WW.frozen
cd /home/user/sts_ai; setsid nohup bash $HOME/gen6-worker.sh $W 8 $HOME/gen6-out-w$WW $HOME/gen6-env.sh > $HOME/gen6-w$WW.run.log 2>&1 < /dev/null &
```
The script checks the checkout, tracked changes, binary sha256 (`b4586cfc…95e1`), model (gen 5, `5e9f975a…9e8a`)
and env.sh, then runs 4 lanes of `one_combat silverazgen` (40k Silver, gen-5 MLP tree prior K=8, weight 400, root
bonus off; one unit at a time per lane, ~15-40 min per unit). It stops at once on a problem (message in the run log:
"bad W/N", "checkout is not", "tracked changes", "not empty", "sha256 mismatch"); report that message verbatim and
stop. Its last line on success is `WORKER_END units ok K of 32`.

**Mandatory watcher.** Results stay on local disk until the upload, and the container is reclaimed when no background
task runs. Right after starting the run, start this with the Bash tool's `run_in_background: true` and the maximum
timeout (2 h):
```sh
until [ -f /mnt/project-files/silver-az-mlp/gen6/wWW.DONE.txt ] || grep -qE "WORKER_END|bad W/N|checkout is not|tracked changes|not empty|sha256 mismatch" $HOME/gen6-wWW.run.log; do sleep 60; done
```
Whenever it hits its time limit, start it again at once (the run keeps going). Do not end your turn without it
running. Check progress every 15-30 min:
`wc -l < $HOME/gen6-out-wWW/units.txt; grep -v " rc=0 " $HOME/gen6-out-wWW/units.txt; cat $HOME/gen6-out-wWW/stalls.txt 2>/dev/null; pgrep -c one_combat`.

## 3. Upload (when the run log has the `WORKER_END` line)

```sh
tar -C $HOME -cf /mnt/project-files/silver-az-mlp/gen6/wWW.tar gen6-out-wWW
{ cat $HOME/gen6-wWW.frozen; echo "tar_sha256 $(sha256sum /mnt/project-files/silver-az-mlp/gen6/wWW.tar | cut -d' ' -f1)";
  echo "binary_sha256 $(cat $HOME/gen6-out-wWW/BINARY_SHA256)"; cat $HOME/gen6-out-wWW/units.txt;
  cat $HOME/gen6-out-wWW/DONE.txt 2>/dev/null || echo "INCOMPLETE: see rc lines";
  cat $HOME/gen6-out-wWW/stalls.txt 2>/dev/null; tail -n 1 $HOME/gen6-wWW.run.log; } > /tmp/wWW.DONE.txt
cp /tmp/wWW.DONE.txt /mnt/project-files/silver-az-mlp/gen6/wWW.DONE.txt
```

## 4. Stalls, failed units, restarts

* **Stall (automatic):** the script backtraces and kills any unit whose `one_combat` runs over 7,200 s
  (`OUT/<tag>.stall.txt`, a line in `stalls.txt`, rc 137). No rerun, no replacement seed. The known Silver
  `SilverSearcher::rolloutToEnd` endless loop (not covered by the #522 loop guard) is the expected cause.
* **A failed unit does not stop the run.** The other units finish; upload as in step 3 (`DONE.txt` is then absent by
  design) and report the failed unit lines.
* **Container restart** (run gone, no `WORKER_END` in the run log): redo step 1, move `$HOME/gen6-out-wWW` and
  `$HOME/azgen6-wW` to `*.aborted-<UTC>`, then step 2 with the same command (the same seeds rerun whole; results
  are deterministic). If that is not possible, upload what exists as in step 3 with `INCOMPLETE: restart`.

## 5. Report

5a. After the upload, reply once in your thread with the FROZEN line and the content of `wWW.DONE.txt`.

5b. Then keep your session alive with a keep-alive watcher (`run_in_background: true`, 2 h, re-armed every time it
ends) until the coordinator says stop: `until [ -f $HOME/gen6-stop ]; do sleep 60; done`. Do not analyze.
