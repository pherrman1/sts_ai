# §479 Silver leaf-rollout variants at A20 (fight level): cloud worker W (W = 1..8; WW = W zero-padded, e.g. 03)

Philipp started this run (2026-10-15 06:44Z, thread "random rollouts": "Start with 8 workers, and drop the two uniform
rollout arms"). Pre-registration: `docs/experiments/evidence/silver_rollout_policy_2x2_20261014/PREREG.md`. Run
commit **RUN_COMMIT** (branch `claude/project-thread-8vmyta`; the coordinator gives it in your header). Do not change
seeds, scripts, environment, binary or settings. Run nothing from `/mnt/project-files` (noexec). The run writes to your
local disk; at the end `worker.sh` uploads exactly two files: `/mnt/project-files/silver-rollout-2x2/wWW.tar` and then
`wWW.DONE.txt`. Write nothing else on the share. The smoke already passed in the planning thread; workers do not run
it. Do not post to GitHub.

## 1. Check out and set up (~10 min)

```sh
cd /home/user/sts_ai
git fetch origin claude/project-thread-8vmyta
git status --porcelain --untracked-files=no     # must be empty; stop otherwise
git checkout --detach RUN_COMMIT
E=docs/experiments/evidence/silver_rollout_policy_2x2_20261014
bash $E/worker.sh setup W                        # must end with "setup ok: ..."; stop on "STOP: ..."
```
If a permission check blocks any command in this brief (checkout, setup, the launch, the watcher), do not work around
it (no other command, path or copy of the script): reply in your thread with the blocked command and the message, and
wait for an answer there.

## 2. Run (roughly 20–45 min: 4 shards of 2 seeds each, in parallel)

```sh
cd /home/user/sts_ai; setsid nohup bash $E/worker.sh run W > $HOME/x479-wWW.run.log 2>&1 < /dev/null &
```
`worker.sh run` calls `run.sh` for seeds 105000000 + 8(W−1) … + 7 (`ctmsilvergen` through the seed guard, 6 h timeout
per shard). When all 4 shards end with rc=0 it uploads the tar, then the DONE file, and prints `uploaded wWW.tar OK`.

**Mandatory watcher.** Results stay on local disk until the upload, and the container is reclaimed when no background
task runs. Right after starting the run, start this with the Bash tool's `run_in_background: true` and the maximum
timeout (2 h):
```sh
until [ -f /mnt/project-files/silver-rollout-2x2/wWW.DONE.txt ] || grep -q "STOP\|uploaded" $HOME/x479-wWW.run.log; do sleep 60; done
```
Whenever it hits its time limit, start it again at once (the run keeps going). Check progress every 10–15 min:
`bash $E/worker.sh status W`.

If the watcher ends on `STOP`, report the last 20 lines of the run log and `worker.sh status W` and stop (do not rerun
anything).

## 3. Stalls, crashes, restarts

* **Stall:** a shard's `$HOME/x479-wWW/out/shardN.arms.csv` has not grown for 60 min while its `one_combat` runs: take
  a backtrace (`gdb -p <pid> -batch -ex "thread apply all bt" > $HOME/x479-wWW/stall-shardN.txt`; find the pid of the
  `one_combat` process, not `seed_guard`, with `pgrep -af "one_combat ctmsilvergen"` and match `shardN`), report it in
  your thread with the shard's last log lines, and wait. Do not kill anything on your own.
* **Crash or nonzero rc:** do not retry; report `shards.txt` and the shard's last 20 log lines.
* **Container restart** (run gone, no `wWW.DONE.txt` on the share): redo step 1, then step 2 with the same command.
  The interrupted output is moved to `aborted-<ts>` and the worker's seeds rerun whole (results are deterministic).

## 4. Report

Reply once in your thread with the content of `/mnt/project-files/silver-rollout-2x2/wWW.DONE.txt` up to the `.csv`
hash lines plus its `tar_sha256` line. Do not analyze.

## 5. Stay alive until told to stop

Right after the report, start this with `run_in_background: true` and the maximum timeout (2 h), and re-arm it every
time it hits its limit:
```sh
until [ -f $HOME/x479-stop ]; do sleep 60; done
```
Keep doing that until the coordinator or planning thread tells you to create `$HOME/x479-stop` (after they verified
your tar from another container). Then run `touch $HOME/x479-stop`, let the watcher end, and stop.
