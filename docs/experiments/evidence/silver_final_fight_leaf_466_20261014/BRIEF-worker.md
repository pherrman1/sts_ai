# §466 final-fight Silver leaf, fight-level replay: cloud worker W (W = 1..8; WW = W zero-padded, e.g. 03)

Philipp requested this run (2026-10-14 08:57Z, decision card in the thread "Situational Silver leaf evaluation":
"Run the §466 final-fight leaf replay on act-3 boss fights?" → "8 workers"). Pre-registration:
`/mnt/project-files/silver-leaf-situational/PREREG-final-fight-leaf.md`. Run commit
**8d8eeb3ceff6ad23399eabfb6d5b8ef34d987146** (branch `claude/project-thread-raxk1g`). N = 8.
Do not change seeds, scripts, environment, binary or settings. Run nothing from `/mnt/project-files` (noexec).
The run writes to your local disk; at the end you upload exactly two files to the share:
`/mnt/project-files/silver-leaf-situational/w466-WW.tar` and then `w466-WW.DONE.txt`. Write nothing else there.
The smoke already passed in the planning thread; workers do not run it. Do not post to GitHub.

## 1. Check out, build, copy the script (~10 min)

```sh
cd /home/user/sts_ai
git fetch origin claude/project-thread-raxk1g
git status --porcelain --untracked-files=no     # must be empty; stop otherwise
git checkout --detach 8d8eeb3ceff6ad23399eabfb6d5b8ef34d987146
git submodule update --init --recursive
cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4
cp /mnt/project-files/silver-leaf-situational/worker.sh $HOME/leaf466-worker.sh
sha256sum $HOME/leaf466-worker.sh   # must be b00ebeaa7fa54b95dc941da1e31539c59d6538c6abfad16800c387818111dfff; stop otherwise
```

## 2. Run (about 40 min). Your seeds: BASE = 96000000 + 32·(W−1), 4 shards of 8 seeds each.

```sh
W=<your W>; WW=$(printf %02d $W); BASE=$((96000000 + 32*(W-1)))
echo "FROZEN commit=8d8eeb3ceff6ad23399eabfb6d5b8ef34d987146 W=$W N=8 base=$BASE per=8 shards=4 R=8" > $HOME/leaf466-w$WW.frozen
cd /home/user/sts_ai; setsid nohup bash $HOME/leaf466-worker.sh 8d8eeb3ceff6ad23399eabfb6d5b8ef34d987146 $BASE 8 4 8 $HOME/leaf466-w$WW > $HOME/leaf466-w$WW.run.log 2>&1 < /dev/null &
```
The script stops at once (message in the run log) on a wrong checkout, tracked changes, a non-empty output
directory or a prior sha mismatch (those messages do not contain "STOP", so the watcher does not end on
them: if a progress check finds such a message in the run log and no `shards.txt`, report it verbatim and stop). It writes `$HOME/leaf466-wWW/BINARY_SHA256`.

**Mandatory watcher.** Results stay on local disk until the upload, and the container is reclaimed when no background
task runs. Right after starting the run, start this with the Bash tool's `run_in_background: true` and the maximum
timeout (2 h):
```sh
until [ -f /mnt/project-files/silver-leaf-situational/w466-WW.DONE.txt ] || grep -q "STOP" $HOME/leaf466-wWW.run.log; do sleep 60; done
```
Whenever it hits its time limit, start it again at once (the run keeps going). Check progress every 10–15 min:
`cat $HOME/leaf466-wWW/shards.txt 2>/dev/null; wc -l $HOME/leaf466-wWW/shard*.arms.csv; ls -la --time-style=+%T $HOME/leaf466-wWW/`.

## 3. Upload (when `$HOME/leaf466-wWW/shards.txt` has 4 lines)

```sh
tar -C $HOME -cf /mnt/project-files/silver-leaf-situational/w466-WW.tar leaf466-wWW
{ cat $HOME/leaf466-wWW.frozen; echo "tar_sha256 $(sha256sum /mnt/project-files/silver-leaf-situational/w466-WW.tar | cut -d' ' -f1)";
  echo "binary_sha256 $(cat $HOME/leaf466-wWW/BINARY_SHA256)"; cat $HOME/leaf466-wWW/shards.txt;
  for f in $HOME/leaf466-wWW/shard*.log; do echo "$(basename $f): $(tail -n 1 $f)"; done; } > /tmp/w466-WW.DONE.txt
cp /tmp/w466-WW.DONE.txt /mnt/project-files/silver-leaf-situational/w466-WW.DONE.txt
```
If a shard ended with rc != 0, still upload as above (finished seeds count) and add the line `INCOMPLETE: <shard> rc=<rc>`.

## 4. Stalls, crashes, restarts

* **Stall:** if one shard's `.log` and all its `.csv` files have not grown for 60 min, take a backtrace
  (`gdb -p <pid> -batch -ex "thread apply all bt" > $HOME/leaf466-wWW/stall-shardI.txt`; find the pid with
  `pgrep -af "ctmsilvergen.*shardI"`), then kill that one `one_combat`. No rerun, no replacement seed. Its rc line
  appears in `shards.txt`; upload as in step 3 with `INCOMPLETE: shardI stalled`. (The known Silver `rolloutToEnd`
  loop is not covered by the #522 guard.)
* **Crash or nonzero rc otherwise:** do not retry; upload as in step 3 and report the shard's rc line and the end of
  its log.
* **Container restart** (run gone, `$HOME/leaf466-wWW/DONE.txt` missing): redo step 1, move the partial output to
  `$HOME/leaf466-wWW.aborted-<UTC>`, then step 2 with the same command (the same seeds rerun whole; results are
  deterministic). If that is not possible, upload what exists as in step 3 with `INCOMPLETE: restart`.

## 5. Report

Reply once in your thread with the FROZEN line and the content of `w466-WW.DONE.txt`. Keep your session alive (the
watcher) until the planning thread or coordinator confirms the tar is readable from another container. Do not analyze.
