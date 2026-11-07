# Worker brief: price-table-stagec (40 workers)

Authorization: Philipp 2026-11-05 20:05 CET "go auf 40 workern" (thread "Build Silver price-table leaf").
RUN_COMMIT=<RUN_COMMIT>   (set in the share copy of this brief after the prelaunch review)

YOUR WORKER NUMBER: W=<n>   (pass it unpadded, 1..40; never 03)
CAMPAIGN=docs/experiments/evidence/silver_price_table_leaf_20261105/stagec
Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec). Do not change seeds, scripts, environments,
binary, models or timeouts. The worker script uploads only to /mnt/project-files/price-table-stagec (units/,
claims/, wWW.DONE.json); write nothing else to the share.
1. cd /home/user/sts_ai && git fetch --depth 10 origin claude/project-thread-xiyc1s && git checkout --detach $RUN_COMMIT
   && git status --short   (must be clean); then: git rev-parse HEAD -> must print $RUN_COMMIT, else STOP
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running", in the same turn, before you reply; never end a turn without the
   wait running. "FINISHED" -> reply with its last line (WORKER_OK ...). "NOT RUNNING" -> reply with the output and stop.
After a container restart, run steps 1-3 at once (start skips done units). Never kill a unit or one_combat process;
a run that times out ends with rc=124 and the unit continues.
If you worked on an earlier campaign, its files are finished; leave them alone, this is a new job.
Stay alive until the author thread says your tar is verified.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Expect 10-30 min per unit (one Shield & Spear state, S&S then the Heart, 12 or 20 runs), 4 units at a time;
1,024 units shared by 40 workers through the queue.
