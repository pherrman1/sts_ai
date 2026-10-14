# §467 Collector-only Silver prior data: cloud worker W (W = 1..4; WW = W zero-padded, e.g. 03)

Philipp requested this run (2026-10-14 08:58Z decision card "Collector data"; 09:23Z "Do 4 workers").
Pre-registration: `/mnt/project-files/silver-prior-fight-specific/collector-data/PREREG.md`. Run commit
**1518989bded26cff6692373d367424c2ebd16845** (branch `claude/project-thread-byhf2a`, draft PR #531). N = 4.
Do not change seeds, scripts, environment, binary or settings. Run nothing from `/mnt/project-files` (noexec).
The run writes to your local disk; at the end you upload exactly two files to the share:
`/mnt/project-files/silver-prior-fight-specific/collector-data/wWW.tar` and then `wWW.DONE.txt`. Write nothing else there.
The smokes already passed; workers do not run them. Do not post to GitHub. Do no analysis.

## 1. Check out, build, copy the scripts (~10 min)

```sh
cd /home/user/sts_ai
git fetch origin claude/project-thread-byhf2a
git status --porcelain --untracked-files=no     # must be empty; stop otherwise
git checkout --detach 1518989bded26cff6692373d367424c2ebd16845
git submodule update --init --recursive
cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4
cp /mnt/project-files/silver-prior-fight-specific/collector-data/worker.sh $HOME/collector-worker.sh
cp /mnt/project-files/silver-prior-fight-specific/collector-data/env.sh $HOME/collector-env.sh
sha256sum $HOME/collector-worker.sh   # must be cbec174db0cd8f14bbe96f66250d98751553b2581a494da14087c6fe5a2cfd00; stop otherwise
sha256sum $HOME/collector-env.sh      # must be 63ff2137a299ee93c0e32fd723d06721fac3295af7a95e94ac7ea28b310db030; stop otherwise
```

## 2. Run (about 75 min with N = 4). Seeds 95000000-95002559 in 640 units of 4; you take 160 units.

```sh
W=<your W>; WW=$(printf %02d $W)
echo "FROZEN commit=1518989bded26cff6692373d367424c2ebd16845 W=$W N=4 seeds=95000000-95002559 units=640 per=4 worker=cbec174db0cd8f14bbe96f66250d98751553b2581a494da14087c6fe5a2cfd00" > $HOME/collector-w$WW.frozen
cd /home/user/sts_ai; setsid nohup bash $HOME/collector-worker.sh $W 4 $HOME/collector-out-w$WW $HOME/collector-env.sh > $HOME/collector-w$WW.run.log 2>&1 < /dev/null &
```
The script checks the checkout, tracked changes, binary sha256 (`ad90e698…5493`), model (`3ebeab9d…52d6`) and
env.sh, then runs 4 lanes of `one_combat silverazfocusgen` (one unit at a time per lane, ~60-130 s per unit). It
stops at once on a problem (message in the run log: "bad W/N", "checkout is not", "tracked changes", "not empty",
"sha256 mismatch"); report that message verbatim and stop. Its last line on success is `WORKER_END units ok K of 160`.

**Mandatory watcher.** Results stay on local disk until the upload, and the container is reclaimed when no background
task runs. Right after starting the run, start this with the Bash tool's `run_in_background: true` and the maximum
timeout (2 h):
```sh
until [ -f /mnt/project-files/silver-prior-fight-specific/collector-data/wWW.DONE.txt ] || grep -qE "WORKER_END|bad W/N|checkout is not|tracked changes|not empty|sha256 mismatch" $HOME/collector-wWW.run.log; do sleep 60; done
```
Whenever it hits its time limit, start it again at once (the run keeps going). Check progress every 10–15 min:
`wc -l < $HOME/collector-out-wWW/units.txt; grep -v " rc=0 " $HOME/collector-out-wWW/units.txt; cat $HOME/collector-out-wWW/stalls.txt 2>/dev/null; pgrep -c one_combat`.

## 3. Upload (when the run log has the `WORKER_END` line)

```sh
tar -C $HOME -cf /mnt/project-files/silver-prior-fight-specific/collector-data/wWW.tar collector-out-wWW
{ cat $HOME/collector-wWW.frozen; echo "tar_sha256 $(sha256sum /mnt/project-files/silver-prior-fight-specific/collector-data/wWW.tar | cut -d' ' -f1)";
  echo "binary_sha256 $(cat $HOME/collector-out-wWW/BINARY_SHA256)"; cat $HOME/collector-out-wWW/units.txt;
  cat $HOME/collector-out-wWW/DONE.txt 2>/dev/null || echo "INCOMPLETE: see rc lines";
  cat $HOME/collector-out-wWW/stalls.txt 2>/dev/null; tail -n 1 $HOME/collector-wWW.run.log; } > /tmp/wWW.DONE.txt
cp /tmp/wWW.DONE.txt /mnt/project-files/silver-prior-fight-specific/collector-data/wWW.DONE.txt
```
Then start a keep-alive watcher (`run_in_background: true`, 2 h, re-armed until the coordinator says stop):
`until [ -f $HOME/collector-stop ]; do sleep 60; done`.

## 4. Stalls, failed units, restarts

* **Stall (automatic):** the script backtraces and kills any unit whose `one_combat` runs over 900 s
  (`OUT/<tag>.stall.txt`, a line in `stalls.txt`, rc 137). No rerun, no replacement seed. The known Silver
  `SilverSearcher::rolloutToEnd` endless loop (not covered by the #522 loop guard) is the expected cause.
* **A failed unit does not stop the run.** The other units finish; upload as in step 3 (`DONE.txt` is then absent by
  design) and report the failed unit lines.
* **Container restart** (run gone, no `WORKER_END` in the run log): redo step 1, move `$HOME/collector-out-wWW` and
  `$HOME/collector-wW` to `*.aborted-<UTC>`, then step 2 with the same command (the same seeds rerun whole; results
  are deterministic). If that is not possible, upload what exists as in step 3 with `INCOMPLETE: restart`.

## 5. Report

Reply once in your thread with the FROZEN line and the content of `wWW.DONE.txt`. Keep your session alive (the
watcher) until the planning thread or coordinator confirms the tar is readable from another container. Do not analyze.
