# Worker brief: learned-price-head-e1r (4 workers)

Authorization: Philipp 2026-11-08 00:58 CET in the price-head thread, "Jo nutz fürs Logging später 4 workers, wenn die
anderen 4 workers dann sind, hast meine Erlaubnis" (E1-R: E1's runs again with the potion rolls logged, about
47 core-h; start only once the other 4 workers are done).
RUN_COMMIT=<RUN_COMMIT>   (set in the share copy of this brief after the prelaunch review)

YOUR WORKER NUMBER: W=<n>   (pass it unpadded, 1..4)
CAMPAIGN=docs/experiments/evidence/learned_price_head_e1r_20261108
Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec). Do not change seeds, scripts, environments,
binary, models or timeouts. The worker script uploads only to /mnt/project-files/learned-price-head/e1r (units/,
claims/, wWW.DONE.json); write nothing else to the share.
1. cd /home/user/sts_ai && git fetch --depth 10 origin claude/project-thread-ps95qp && git checkout --detach $RUN_COMMIT
   && git status --short   (must be clean); then: git rev-parse HEAD -> must print $RUN_COMMIT, else STOP
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running", in the same turn, before you reply; never end a turn without the
   wait running. "FINISHED" -> reply with its last line (WORKER_OK ...). "NOT RUNNING" -> reply with the output and stop.
After a container restart, run steps 1-3 at once (start skips done units). Never kill a unit or one_combat process.
When the author or the coordinator says "stop now": run `bash tools/cloud/worker.sh stop $CAMPAIGN <n>` (no new
units; running units finish and upload), keep the wait running until it returns, then reply with its output.
If you worked on an earlier campaign, its files are finished; leave them alone, this is a new job.
Stay alive until the author thread says your units are verified.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Expect about 6 min per unit (1-20 min; 16 A20 runs, no replays), 4 units at a time; 512 units shared by 4 workers
through the queue, so about 3 h in all.
