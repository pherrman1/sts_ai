# Learned-stop retrain traces: cloud worker brief

YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=__RUN_COMMIT__  CAMPAIGN=docs/experiments/evidence/silver_stoptrace_a20_20261018

Philipp authorized this run (__AUTH__). Do not change seeds, scripts, environments, binary, weights or timeouts.
Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec). The worker script uploads exactly wWW.tar
and wWW.DONE.json to /mnt/project-files/silver-stoptrace-a20; write nothing else to the share.

1. cd /home/user/sts_ai && git fetch origin && git checkout --detach $RUN_COMMIT && git status --short   (must be clean)
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running". "FINISHED" -> reply with its last line (WORKER_OK ...).
   "NOT RUNNING" -> reply with the output and stop.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Never kill a unit or one_combat process; a unit that times out ends rc=124 and the run continues.
Keep the session alive until you are told the tar is verified.
