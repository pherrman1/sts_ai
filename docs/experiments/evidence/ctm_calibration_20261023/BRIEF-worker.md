# CTM-calibration A/B: cloud worker brief

YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=__RUN_COMMIT__  CAMPAIGN=docs/experiments/evidence/ctm_calibration_20261023

Philipp authorized this run (__AUTHORIZATION__).
- Do not change seeds, scripts, environments, binary, weights or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads only to /mnt/project-files/ctm-calibration-ab (units/, claims/, wWW.DONE.json). Write nothing
  else to the share.

1. cd /home/user/sts_ai && git fetch origin && git checkout --detach $RUN_COMMIT && git status --short   (must be clean)
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   - Re-arm it each time it returns "still running".
   - "FINISHED": reply with its last line (WORKER_OK ...).
   - "NOT RUNNING": reply with the output and stop.

If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Never kill a unit or one_combat process. A unit that times out ends with rc=124, and the run continues.
If the container restarts, run steps 1-3 again (finished units are skipped).
Keep the session alive until you are told the tar is verified.
Expect about 26 min per unit (two 4096-sim search runs, about 13 min each), 4 units at a time: about 2 h wall per
worker for stage 1 (512 seeds on 32 workers), plus a straggler tail.
