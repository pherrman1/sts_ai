# Worker brief: map-sims-sprt (24 workers)

YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=<sha given in the header>  CAMPAIGN=docs/experiments/evidence/map_sims_sprt_20261101
Work in /home/user/sts_ai.
1. git fetch origin && git checkout --detach $RUN_COMMIT && git status --short   (must be clean; if the bare-SHA
   fetch fails: git fetch origin claude/project-thread-ttx3if)
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running", in the same turn, before you reply; never end a turn without the
   wait running. "FINISHED" -> reply with its last line (WORKER_OK ...). "NOT RUNNING" -> reply with the output and stop.
After a container restart, run steps 1-3 at once (start skips done units). Never kill units.
Stay alive until the author thread says your tar is verified.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
