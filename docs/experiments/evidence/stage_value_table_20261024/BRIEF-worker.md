# Stage-value table, Stage A (Heart): cloud worker brief

YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=<frozen sha, given in the header>  CAMPAIGN=docs/experiments/evidence/stage_value_table_20261024

Philipp authorized this run (2026-10-24 23:00Z, "go stufe A"; 8 workers chosen 22:58Z).
- Do not change seeds, scripts, environments, binary or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads only to /mnt/project-files/stage-value-table/stage-a (units/, claims/, wWW.DONE.json). Write
  nothing else to the share.

1. cd /home/user/sts_ai && git fetch origin && git checkout --detach $RUN_COMMIT && git status --short   (must be clean)
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   - Re-arm it each time it returns "still running", in the same turn, before you reply. Never end a turn without
     the wait running.
   - "FINISHED": reply with its last line (WORKER_OK ...).
   - "NOT RUNNING": reply with the output and stop.

If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Never kill a unit or one_combat process. A unit that times out ends with rc=124, and the run continues.
If the container restarts, run steps 1-3 again at once (finished units are skipped).
Keep the session alive until you are told the tar is verified.
Units: 96 (one Heart entry deck: base + 24 variants x 4 copies = 100 fights of about 5-9 s each), 4 at a time.
Each unit takes about 10-15 min. Expect about 40-60 min per worker.
