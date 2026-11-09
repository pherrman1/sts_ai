# Gumbel 1k in whole runs (G1 = G16 + mb4 at 1,000 simulations, against combat B): cloud worker brief

YOUR WORKER NUMBER: W=<n>   (1..40; pass it unpadded, never 03)
RUN_COMMIT=<RUN_COMMIT>  CODE_COMMIT=<CODE_COMMIT>  CAMPAIGN=docs/experiments/evidence/gumbel_1k_wholerun_20261109

Philipp asked for this test on 2026-11-09 at 23:35 CET ("Kannst du mal schnell gumbel mit 1k sims anstatt 16k sims auf
512 seeds auf 40 workern laufen lassen?") and at 23:41 CET ("baller da jetzt 40 worker durch"), 40 workers.
- Do not change seeds, scripts, environments, binary, weights or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads only to /mnt/project-files/combat-plan/gumbel-1k-wholerun (units/, claims/,
  wWW.DONE.json). Write nothing else to the share.

1. In the FOREGROUND (timeout 10 min):
   cd /home/user/sts_ai && git fetch --depth 1 origin $RUN_COMMIT && git checkout --detach $RUN_COMMIT && git rev-parse HEAD && git status --short
   Then also fetch the code commit the binary is built from: git fetch --depth 1 origin $CODE_COMMIT
   (HEAD must equal RUN_COMMIT; status must be clean for tracked files). If a fetch fails, retry up to 4 times
   (wait 2 s, 4 s, 8 s, 16 s).
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   - When it returns "still running", re-arm it in the same turn, before you reply. Never end a turn without
     the wait running.
   - "FINISHED": reply with its last line (WORKER_OK ...).
   - "NOT RUNNING": reply with the output and stop.

If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Never kill a unit or one_combat process. A unit that times out ends with its rc in the .done line, and the run
continues. If the container restarts, run steps 1-3 again at once (finished units are skipped).
Keep the session alive until you are told the tar is verified.
Expect 10 s to 3 min per unit (two whole A20 runs on one seed at 1,000 simulations), 4 units at a time; 512 units
shared by 40 workers through the queue (the run about 10-20 min).
When your queue is empty and you only wait, that is normal: stay idle with the wait armed.
