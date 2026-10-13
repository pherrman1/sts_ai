# §443 Stage 4 fresh A20 gate corpus: cloud worker W (W = 1..8; WW = W zero-padded, e.g. 07)

Philipp approved this run with 8 workers on 2026-10-13 15:00Z ("Approve 8 workers", in the "lizard tail support for
a0" thread, which owns §443). Pre-registration: `/mnt/project-files/ctm-a20/regate/PREREG-REGATE.md`. Same generator as
the Stage 1 corpus; only the seeds differ. Run commit **90f6df64c87ad9b298e06d1a19bb4e69fc577296** (main after
#498). Do not change seeds, scripts, environment, binary or teacher. Run nothing in place from `/mnt/project-files`
(it is noexec): copy the scripts first. Units write to your local disk; at the end the script uploads exactly two files
to the share: `/mnt/project-files/ctm-a20/stage4/wWW.tar.gz` and then `wWW.DONE.txt`. Write nothing else to the share.
The smoke already passed in the planning thread; workers do not run it.

## 1. Check out the run commit, copy scripts, build (~10 min)

```sh
cd /home/user/sts_ai
git fetch origin main
git status --porcelain --untracked-files=no     # must be empty; stop otherwise
git checkout --detach 90f6df64c87ad9b298e06d1a19bb4e69fc577296
mkdir -p $HOME/ctm443s4 && cp /mnt/project-files/ctm-a20/stage4/{run_unit.sh,worker.sh,teacher.json} $HOME/ctm443s4/
cd $HOME/ctm443s4 && sha256sum run_unit.sh worker.sh teacher.json
```
The three hashes must be exactly:
```
76fb856fe2c82b51f63e511ee366387927c840c507b3b5720900479bab43a167  run_unit.sh
38f70e02d002cb6f991ca31b9cb138e03809acc63672327c89df2debd8aca370  worker.sh
01e96a9f1e2fcfdf5df7f5d1465c130b9f173e055b5f103264b667e37530d834  teacher.json
```
Stop and report if any differs. Then:
```sh
bash $HOME/ctm443s4/worker.sh setup W
```
`setup` checks the checkout, builds `one_combat`, checks its sha256 (`12e881be…`) and the teacher, and writes
`$HOME/ctm443s4-wWW/out/FROZEN.txt`. Any `STOP:` line means stop and report it verbatim.

## 2. Run (about 45 min). Start it detached:

```sh
setsid nohup bash $HOME/ctm443s4/worker.sh run W > $HOME/ctm443s4-wWW.run.log 2>&1 < /dev/null &
```
It runs 11 units of 50 seeds, 4 at a time: 10 main units (seeds 78600000+500(W−1) .. +499, ascension 20,
`combattransitiongen` with the deployed OOC step) and one Lizard unit (odd W: lizard_fairy 78610000+50·(W−1)/2; even W:
lizard_brew 78611000+50·(W/2−1)). Then it uploads the tar and the DONE file.

**Mandatory watcher.** Results stay on local disk until the end, and the container is reclaimed when no background
task is running, which would lose them. Right after starting the run, start this with the Bash tool's
`run_in_background: true` and the maximum timeout (2 h):
```sh
until [ -f /mnt/project-files/ctm-a20/stage4/wWW.DONE.txt ] || grep -q "STOP:" $HOME/ctm443s4-wWW.run.log; do sleep 60; done
```
Whenever the watcher hits its time limit, start it again at once (the run keeps going). Check progress every
15–20 min with `bash $HOME/ctm443s4/worker.sh status W` (it lists any unit whose rc is not 0).

## 3. Crashes and restarts

* A unit with nonzero rc, a crash, or a `STOP:` line: do not retry; report the unit's `.done` line or the `STOP:` line
  and the end of the unit's log (`$HOME/ctm443s4-wWW/out/NAME-LO.log`).
* After a container restart: redo step 1 (same commands), then step 2. Finished units are skipped; an interrupted
  one is moved to `out/aborted-…/` and rerun whole.

## 4. Report

Reply in your thread with the first line of `out/FROZEN.txt` and the share's `wWW.DONE.txt` first two lines, the
sum of rows, any line without `rc=0`, and the `tar_sha256` line. Keep your session alive (the watcher) until the
planning thread or coordinator confirms the tar is readable from another container. Do not analyze.
