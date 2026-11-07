# Worker brief: silver-leaf-price-gate (4 workers)

Authorization: Philipp 2026-11-08 00:48 CET "Na gut lass doch p1 messen, die 3 vorgeschlagenen arms von dir." and
00:50 CET "Glaube 4 workers reichen" (leaf-estimator thread of this project).
RUN_COMMIT=<RUN_COMMIT>   (set in the share copy of this brief after the prelaunch review)

YOUR WORKER NUMBER: W=<n>   (pass it unpadded, 1..4; never 03)
CAMPAIGN=docs/experiments/evidence/silver_leaf_price_gate_20261108
Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec). Do not change seeds, scripts, environments,
binary, models or timeouts. The worker script uploads only to /mnt/project-files/silver-leaf-price-gate (units/,
claims/, wWW.DONE.json); write nothing else to the share.
1. cd /home/user/sts_ai && git fetch --depth 10 origin claude/project-thread-ynb6vs-main && git checkout --detach $RUN_COMMIT
   && git status --short   (must be clean); then: git rev-parse HEAD -> must print $RUN_COMMIT, else STOP
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must end with "setup ok" (binary comes from the cache)
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running", in the same turn, before you reply; never end a turn without the
   wait running. "FINISHED" -> reply with its last line (WORKER_OK ...). Anything else -> reply with the output and stop.
After a container restart, run steps 1-3 at once (start skips done units). Never kill a unit or one_combat process.
If you worked on an earlier campaign, its files are finished; leave them alone, this is a new job.
Stay alive until the author thread says your tar is verified.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Expect about 1-2 min per unit (one seed, three A20 runs at ~21 s each), 4 units at a time; 2,048 units shared by 4
workers through the queue, about 2-2.5 h in all.
