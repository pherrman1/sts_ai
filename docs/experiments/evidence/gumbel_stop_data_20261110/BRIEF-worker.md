# Worker brief: gumbel-stop-data (40 workers)

Authorization: Philipp 2026-11-10 08:36 CET "Go auf 40 worker" (learned-stop thread of this project) for the
Gumbel stop-trace data run (SMOKE.md of gumbel_stop_trace_20261110).
RUN_COMMIT=<filled after push>

YOUR WORKER NUMBER: W=<n>   (pass it unpadded, 1..40; never 03)
CAMPAIGN=docs/experiments/evidence/gumbel_stop_data_20261110
Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec). Do not change seeds, scripts, environments,
binary, models or timeouts. The worker script uploads only to /mnt/project-files/gumbel-stop/data (units/, claims/,
wWW.DONE.json); write nothing else to the share.
1. In the FOREGROUND (timeout 10 min):
   cd /home/user/sts_ai && git fetch --depth 1 origin $RUN_COMMIT && git checkout --detach $RUN_COMMIT && git rev-parse HEAD && git status --short
   (HEAD must equal RUN_COMMIT; status must be clean for tracked files). If the fetch fails, retry up to 4 times
   (wait 2 s, 4 s, 8 s, 16 s).
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must end with "setup ok" (binary comes from the cache)
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running", in the same turn, before you reply; never end a turn without the
   wait running. "FINISHED" -> reply with its last line (WORKER_OK ...). Anything else -> reply with the output and stop.
After a container restart, run steps 1-3 at once (start skips done units). Never kill a unit or one_combat process.
If you worked on an earlier campaign, its files are finished; leave them alone, this is a new job.
Stay alive until the author thread says your tar is verified. If the author asks for an early stop, run
bash tools/cloud/worker.sh stop $CAMPAIGN <n> (no new units; running ones finish), then keep the wait running.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Expect 1-30 min per unit (one seed, one G16 game with the trace), 4 units at a time; 1,024 units shared by
40 workers through the queue, about 1-2 h in all.
