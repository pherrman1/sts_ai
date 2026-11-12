# Plan commitment (PCH, PCS against §792's A4P): cloud worker brief

YOUR WORKER NUMBER: W=<n>   (1..40; pass it unpadded, never 03)
RUN_COMMIT=<RUN_COMMIT>  CODE_COMMIT=<CODE_COMMIT>  CAMPAIGN=docs/experiments/evidence/plan_commit_wholerun_20261112

Philipp authorized this gate on 2026-11-12 10:39 CET in the cheap-combat roadmap thread (decision card "Plan-
Weiterspielen als Ganzlauf-Gate gegen A4P testen?", option "Ja, hart + weich (0,9)": two arms against A4P on §775's
seeds with 40 workers).
- Do not change seeds, scripts, environments, binary, weights or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads only to /mnt/project-files/plan-commit (units/, claims/,
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
Expect 1 to 30 min per unit (one whole A20 run on one seed), 4 units at a time; 2,080 units shared by the workers
through the queue (about 95-130 lane-hours, so about 40-55 min on 40 workers plus the slowest game).
When your queue is empty and you only wait, that is normal: stay idle with the wait armed.
