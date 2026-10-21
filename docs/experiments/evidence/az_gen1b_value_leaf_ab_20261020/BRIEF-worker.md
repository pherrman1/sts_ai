# Gen-1b value-leaf A/B: cloud worker brief

YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=__RUN_COMMIT__  CAMPAIGN=docs/experiments/evidence/az_gen1b_value_leaf_ab_20261020

Philipp authorized this run (2026-10-21 06:49Z: "Just update to main, then go 32 workers"; learned stop off at 05:22Z).
- Do not change seeds, scripts, environments, binary, weights or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads exactly wWW.tar and wWW.DONE.json to /mnt/project-files/az-gen1b-value-leaf-ab. Write nothing else to the share.

1. cd /home/user/sts_ai && git fetch origin && git checkout --detach $RUN_COMMIT && git status --short   (must be clean)
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   - Re-arm it each time it returns "still running".
   - "FINISHED": reply with its last line (WORKER_OK ...).
   - "NOT RUNNING": reply with the output and stop.

If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Never kill a unit or one_combat process. A unit that times out ends with rc=124, and the run continues.
Keep the session alive until you are told the tar is verified.
Expect about 6-9 h wall per worker at 32 workers (learned stop off) (16 units, two 4096-sim search runs each).
