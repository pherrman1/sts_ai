# Per-type Silver potion weights A/B, whole A20 runs: cloud worker W (W = 1..N; WW = W zero-padded, e.g. 03)

Philipp requested this test (2026-10-17, thread "Silver leaf evaluation": "yes set that up"; 16:31Z: "ooc should be
studnet C. lets do 128 seeds on 4 workers"). N = the number in
`docs/experiments/evidence/silver_potion_weights_20261017/NWORKERS` at the run commit (4).
Pre-registration: `PREREG.md` in that folder. Run commit **RUN_COMMIT** (branch `claude/silver-potion-type-weights`;
the coordinator gives it in your header). Do not change seeds, scripts, environment, binary or settings. Run nothing from
`/mnt/project-files` (noexec). The run writes to your local disk; at the end `worker.sh` uploads exactly two files:
`/mnt/project-files/silver-potion-weights/wWW.tar` and then `wWW.DONE.txt`. Write nothing else on the share.
The smoke already passed in the planning thread; workers do not run it. Do not post to GitHub.

## 1. Check out and set up (~10 min)

```sh
cd /home/user/sts_ai
git fetch origin claude/silver-potion-type-weights
git status --porcelain --untracked-files=no     # must be empty; stop otherwise
git checkout --detach RUN_COMMIT
D=docs/experiments/evidence/silver_potion_weights_20261017
bash $D/worker.sh setup W                        # must end with "setup ok: ..."; stop on "STOP: ..."
```
If a permission check blocks any command in this brief (checkout, setup, the launch, the watcher), do not work around
it (no other command, path or copy of the script): reply in your thread with the blocked command and the message, and
wait for an answer there.
`setup` builds `one_combat`, refuses a binary whose sha256 differs from `$D/binary.sha256`, copies the student C
weights from `/mnt/project-files/rollout-student-494/studentc.bin` (data only; refused unless the sha256 equals
`$D/weights.txt`), and writes
`$HOME/xpw-wWW/out/FROZEN.txt`.

## 2. Run (roughly 40-60 min; 4 units at a time)

```sh
cd /home/user/sts_ai; setsid nohup bash $D/worker.sh run W > $HOME/xpw-wWW.run.log 2>&1 < /dev/null &
```
Each unit is one seed in one arm (`base`, `level` or `type`), a guarded one-seed `bestbench` with a 4 h timeout. When every
unit has a `.done` file, the script uploads the tar and then the DONE file and prints `units done: n/n`.

**Mandatory watcher.** Results stay on local disk until the upload, and the container is reclaimed when no background
task runs. Right after starting the run, start this with the Bash tool's `run_in_background: true` and the maximum
timeout (2 h):
```sh
until [ -f /mnt/project-files/silver-potion-weights/wWW.DONE.txt ] || grep -q "STOP\|units done" $HOME/xpw-wWW.run.log; do sleep 60; done
```
Whenever it hits its time limit, start it again at once (the run keeps going). Check progress every 10–15 min:
`bash $D/worker.sh status W; ls -la --time-style=+%T $HOME/xpw-wWW/out | tail -n 8`.

If the watcher ends on `units done: n/m` with n < m, or on `STOP`, report the last 20 lines of the run log and
`worker.sh status W` and stop (do not rerun anything).

## 3. Stalls, crashes, restarts

* **Stall:** a unit's `.log` has not grown for 60 min while its `one_combat` runs: take a backtrace
  (`gdb -p <pid> -batch -ex "thread apply all bt" > $HOME/xpw-wWW/out/stall-<unit>.txt`, where `<unit>` is the
  unit's file stem, e.g. `type-111152007`; this file is how the analysis drops the seed; find the pid of the
  `one_combat` process, not `seed_guard`, with `pgrep -af "one_combat.*bestbench"` and match the seed), then kill that
  one `one_combat`. No rerun, no replacement seed. The unit then gets a `.done` with its rc and the run finishes normally.
* **Crash or nonzero rc:** do not retry. The unit's rc is in its `.done` and in `DONE.txt`; report it.
* **Container restart** (run gone, no `wWW.DONE.txt` on the share): redo step 1 (setup refuses nothing that already
  exists), then step 2 with the same command. Finished units are kept (`.done`); an interrupted unit is moved to
  `aborted-<ts>` and rerun whole (results are deterministic). If that is not possible, report what exists.

## 4. Report

Reply once in your thread with the first line of `FROZEN.txt` and the content of
`/mnt/project-files/silver-potion-weights/wWW.DONE.txt` up to the `.csv` hash lines plus its `tar_sha256` line. Do not
analyze.

## 5. Stay alive until told to stop

Right after the report, start this with `run_in_background: true` and the maximum timeout (2 h), and re-arm it every
time it hits its limit:
```sh
until [ -f $HOME/xpw-stop ]; do sleep 60; done
```
Keep doing that until the coordinator or planning thread tells you to create `$HOME/xpw-stop` (after they verified
your tar from another container). Then run `touch $HOME/xpw-stop`, let the watcher end, and stop.
