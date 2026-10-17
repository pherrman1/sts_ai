# Silver prior gen 7, Act-4 self-play: cloud worker W (W = 1..N, unpadded; WW = W zero-padded, e.g. 03)

Philipp requested this run (2026-10-17 19:01Z "lets do the next prior generation"; worker count __N__ from him).
Plan: `docs/experiments/evidence/silver_gen7_act4_20261017/PLAN.md` at the run commit.
Run commit **__RUN_COMMIT__**. N = __N__. Data generation only: do no analysis, do not post to GitHub, do not change
seeds, scripts, environment, binary or settings. Run nothing from `/mnt/project-files` (only copy the states data
file from there). At the end you upload exactly two files: `/mnt/project-files/silver-az-mlp/gen7-act4/wWW.tar`
and then `/mnt/project-files/silver-az-mlp/gen7-act4/wWW.DONE.txt`. Write nothing else there.

## 1. Check out, build (~10 min)
```sh
cd /home/user/sts_ai
git fetch origin claude/silver-gen7-act4
git status --porcelain --untracked-files=no     # must be empty; stop otherwise
git checkout --detach __RUN_COMMIT__
git submodule update --init --recursive
cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4
cp /mnt/project-files/silver-az-mlp/gen7-act4/act4-states.jsonl $HOME/act4-states.jsonl
sha256sum $HOME/act4-states.jsonl   # must be __STATES_SHA__; stop otherwise
```

## 2. Run
Pass W unpadded to worker.sh (3, never 03); WW only in file names.
```sh
W=<your W>; WW=$(printf %02d $W)
echo "FROZEN commit=__RUN_COMMIT__ W=$W N=__N__ seeds=111170200+state sims=40000 copies=2" > $HOME/gen7a4-w$WW.frozen
cd /home/user/sts_ai; setsid nohup bash docs/experiments/evidence/silver_gen7_act4_20261017/worker.sh $W __N__ $HOME/gen7a4-out-w$WW $HOME/act4-states.jsonl > $HOME/gen7a4-w$WW.run.log 2>&1 < /dev/null &
```
The script checks the checkout, tracked changes, binary sha256, prior and states file, then runs 4 lanes of
`one_combat silverazact4gen` (units of 25 fight starts, 2 copies each, ~35-40 min per unit). It stops at once on a
problem ("bad W/N", "checkout is not", "tracked changes", "not empty", "sha256 mismatch", "bad state count",
"no units"); report that message verbatim and stop. Its last line on success is `WORKER_END units ok K of M`.

**Mandatory watcher.** Results stay on local disk until the upload, and the container is reclaimed when no
background task runs. Right after starting the run, start this with the Bash tool's `run_in_background: true` and
the maximum timeout:
```sh
until grep -qE "WORKER_END|bad W/N|checkout is not|tracked changes|not empty|sha256 mismatch|bad state count|no units" $HOME/gen7a4-wWW.run.log; do sleep 60; done
```
Whenever it hits its time limit, start it again at once. Do not end your turn without it running. Check progress
every 15-30 min: `wc -l < $HOME/gen7a4-out-wWW/units.txt; grep -v " rc=0 " $HOME/gen7a4-out-wWW/units.txt; cat $HOME/gen7a4-out-wWW/stalls.txt 2>/dev/null; pgrep -c one_combat`.

## 3. Upload (after `WORKER_END`)
```sh
tar -C $HOME -cf /mnt/project-files/silver-az-mlp/gen7-act4/wWW.tar gen7a4-out-wWW
{ cat $HOME/gen7a4-wWW.frozen; echo "tar_sha256 $(sha256sum /mnt/project-files/silver-az-mlp/gen7-act4/wWW.tar | cut -d' ' -f1)";
  echo "binary_sha256 $(cat $HOME/gen7a4-out-wWW/BINARY_SHA256)"; cat $HOME/gen7a4-out-wWW/units.txt;
  cat $HOME/gen7a4-out-wWW/DONE.txt 2>/dev/null || echo "INCOMPLETE: see rc lines";
  cat $HOME/gen7a4-out-wWW/stalls.txt 2>/dev/null; tail -n 1 $HOME/gen7a4-wWW.run.log; } > /tmp/wWW.DONE.txt
cp /tmp/wWW.DONE.txt /mnt/project-files/silver-az-mlp/gen7-act4/wWW.DONE.txt
```
Then reply in your thread with the DONE file contents and stay idle (keep the container alive) until told the tar
is verified. Do not rerun failed units, do not restart the worker; report and wait.
