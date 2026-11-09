# Gumbel tuning, hallway test (c2 against the control on hallway fights): cloud worker brief

YOUR WORKER NUMBER: W=<n>   (1..14; pass it unpadded, never 03)
RUN_COMMIT=<RUN_COMMIT>  CODE_COMMIT=<CODE_COMMIT>  CAMPAIGN=docs/experiments/evidence/gumbel_tuning_20261109/hallway

Philipp chose this test on 2026-11-09 at 23:30 CET; launch only after his typed go (<GO>), 14 workers.
- Do not change seeds, scripts, environments, binary, weights or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads only to /mnt/project-files/combat-plan/gumbel-tuning-hallway (units/, claims/,
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
Expect 15 to 60 min per unit (one production A20 run through act 3 with both arms on every hallway fight),
4 units at a time; 56 units shared by 14 workers through the queue (the run about 1 h).
When your queue is empty and you only wait, that is normal: stay idle with the wait armed.
