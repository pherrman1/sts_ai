# Expert-anchored student_sel A/B (experiment 7): cloud worker brief

YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=__RUN_COMMIT__  CAMPAIGN=docs/experiments/evidence/expert_anchored_student_ab_20261026

Philipp authorized this run (2026-10-26 22:56Z, "go on 16 workers after the boss relic workers are done").
- Do not change seeds, scripts, environments, binary, weights or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads only to /mnt/project-files/expert-anchored-ab (units/, claims/, wWW.DONE.json). Write
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
If the container restarts, run steps 1-3 again at once (finished units are skipped). Remove a stale local lock only
if ps shows no worker or _qlane process.
Keep the session alive until you are told the tar is verified.
Expect about __UNIT_MIN__ min per unit (two games: A and B), 4 units at a time.
