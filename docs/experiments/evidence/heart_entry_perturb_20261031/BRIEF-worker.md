# Heart-entry perturbation labels: cloud worker brief

YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=<RUN_COMMIT>  CAMPAIGN=docs/experiments/evidence/heart_entry_perturb_20261031

Philipp authorized this run on 2026-10-31 at 19:14Z ("Yes go" to 16 workers).
- Do not change seeds, scripts, environments, binary, weights or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads only to /mnt/project-files/heart-entry-perturb (units/, claims/, wWW.DONE.json). Write
  nothing else to the share.

1. cd /home/user/sts_ai && git fetch origin claude/project-thread-19vi4s && git checkout --detach $RUN_COMMIT && git rev-parse HEAD && git status --short
   (HEAD must equal RUN_COMMIT; status must be clean)
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   - When it returns "still running", re-arm it in the same turn, before you reply. Never end a turn without
     the wait running.
   - "FINISHED": reply with its last line (WORKER_OK ...).
   - "NOT RUNNING": reply with the output and stop.

If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Never kill a unit or one_combat process. A unit that times out ends with rc=124, and the run continues.
If the container restarts, run steps 1-3 again at once (finished units are skipped).
Keep the session alive until you are told the tar is verified.
Expect 3 to 60 min per unit (one Heart-entry state played 16 times, once per variant), 4 units at a time;
1,000 units shared by 16 workers through the queue.
