# §469 Collector prior online check: cloud worker W (W = 1..N; WW = W zero-padded, e.g. 03)

Philipp requested this run (2026-10-14 12:27Z decision card "Online check"; worker count N from his reply).
Pre-registration: `/mnt/project-files/silver-prior-fight-specific/eval469/PREREG.md`. Run commit
**0ce7bc4ee47fb7c87518a44c4dd9778a65b5cbf5** (branch `claude/project-thread-byhf2a`, draft PR #531).
Do not change seeds, scripts, environment, binary or settings. Run nothing from `/mnt/project-files` (noexec).
The run writes to your local disk; at the end you upload exactly two files to the share:
`/mnt/project-files/silver-prior-fight-specific/eval469/wWW.tar` and then `wWW.DONE.txt`. Write nothing else there.
The smokes already passed; workers do not run them. Do not post to GitHub. Do no analysis.

## 1. Check out, build, copy the scripts (~10 min)

```sh
cd /home/user/sts_ai
git fetch origin claude/project-thread-byhf2a
git status --porcelain --untracked-files=no     # must be empty; stop otherwise
git checkout --detach 0ce7bc4ee47fb7c87518a44c4dd9778a65b5cbf5
git submodule update --init --recursive
cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4
cp /mnt/project-files/silver-prior-fight-specific/eval469/worker.sh $HOME/eval469-worker.sh
cp /mnt/project-files/silver-prior-fight-specific/eval469/env.sh $HOME/eval469-env.sh
sha256sum $HOME/eval469-worker.sh   # must be a24096a3e661716943aff9e7964a1a1ebbc4633c75ee7400ce4642c46d4c9351; stop otherwise
sha256sum $HOME/eval469-env.sh      # must be a92be23874af1a69b1bb884b59025755c9a0296989014dd76f3743a72dac349a; stop otherwise
```

## 2. Run. Seeds 99000000-99000999 in 250 units of 4; with N workers you take about 250/N units.

```sh
W=<your W>; N=<N>; WW=$(printf %02d $W)
echo "FROZEN commit=0ce7bc4ee47fb7c87518a44c4dd9778a65b5cbf5 W=$W N=$N seeds=99000000-99000999 units=250 per=4 worker=a24096a3e661716943aff9e7964a1a1ebbc4633c75ee7400ce4642c46d4c9351" > $HOME/eval469-w$WW.frozen
cd /home/user/sts_ai; setsid nohup bash $HOME/eval469-worker.sh $W $N $HOME/eval469-out-w$WW $HOME/eval469-env.sh > $HOME/eval469-w$WW.run.log 2>&1 < /dev/null &
```
The script checks the checkout, tracked changes, binary sha256 (`755be7be…02a7`), both priors (`3ebeab9d…52d6`,
`d78f80c9…c881`) and env.sh, then runs 4 lanes of `one_combat silverfocusevalgen` (one unit at a time per lane,
~1-5 min per unit). It stops at once on a problem (message in the run log: "bad W/N", "checkout is not",
"tracked changes", "not empty", "sha256 mismatch"); report that message verbatim and stop. Its last line on
success is `WORKER_END units ok K of M`. Expected wall time: about 3 h with N = 1, 45 min with N = 4.

**Mandatory watcher.** Results stay on local disk until the upload, and the container is reclaimed when no background
task runs. Right after starting the run, start this with the Bash tool's `run_in_background: true` and the maximum
timeout (2 h):
```sh
until [ -f /mnt/project-files/silver-prior-fight-specific/eval469/wWW.DONE.txt ] || grep -qE "WORKER_END|bad W/N|checkout is not|tracked changes|not empty|sha256 mismatch" $HOME/eval469-wWW.run.log; do sleep 60; done
```
Whenever it hits its time limit, start it again at once (the run keeps going). Check progress every 10-15 min:
`wc -l < $HOME/eval469-out-wWW/units.txt; grep -v " rc=0 " $HOME/eval469-out-wWW/units.txt; cat $HOME/eval469-out-wWW/stalls.txt 2>/dev/null; pgrep -c one_combat`.

## 3. Upload (when the run log has the `WORKER_END` line)

```sh
tar -C $HOME -cf /mnt/project-files/silver-prior-fight-specific/eval469/wWW.tar eval469-out-wWW
{ cat $HOME/eval469-wWW.frozen; echo "tar_sha256 $(sha256sum /mnt/project-files/silver-prior-fight-specific/eval469/wWW.tar | cut -d' ' -f1)";
  echo "binary_sha256 $(cat $HOME/eval469-out-wWW/BINARY_SHA256)"; cat $HOME/eval469-out-wWW/units.txt;
  cat $HOME/eval469-out-wWW/DONE.txt 2>/dev/null || echo "INCOMPLETE: see rc lines";
  cat $HOME/eval469-out-wWW/stalls.txt 2>/dev/null; tail -n 1 $HOME/eval469-wWW.run.log; } > /tmp/wWW.DONE.txt
cp /tmp/wWW.DONE.txt /mnt/project-files/silver-prior-fight-specific/eval469/wWW.DONE.txt
```
Then start a keep-alive watcher (`run_in_background: true`, 2 h, re-armed until told to stop):
`until [ -f $HOME/eval469-stop ]; do sleep 60; done`.

## 4. Stalls, failed units, restarts

* **Stall (automatic):** the script backtraces and kills any unit whose `one_combat` runs over 1,800 s
  (`OUT/<tag>.stall.txt`, a line in `stalls.txt`, rc 137); its csv/manifest become `*.failed`. No rerun, no
  replacement seed. The known Silver `SilverSearcher::rolloutToEnd` endless loop is the expected cause.
* **A failed unit does not stop the run.** The other units finish; upload as in step 3 (`DONE.txt` is then absent by
  design) and report the failed unit lines.
* **Container restart** (run gone, no `WORKER_END` in the run log): redo step 1, move `$HOME/eval469-out-wWW` and
  `$HOME/eval469-wW` to `*.aborted-<UTC>`, then step 2 with the same command (the same seeds rerun whole; results
  are deterministic). If that is not possible, upload what exists as in step 3 with `INCOMPLETE: restart`.

## 5. Report

Reply once in your thread with the FROZEN line and the content of `wWW.DONE.txt`. Keep your session alive (the
watcher) until the planning thread or coordinator confirms the tar is readable from another container and tells
you to stop; then `touch $HOME/eval469-stop`. Do not analyze.
