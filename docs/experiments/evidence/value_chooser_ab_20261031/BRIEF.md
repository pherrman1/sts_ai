# Worker brief: value-chooser-ab (32 workers)

YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=<sha given in the header>  CAMPAIGN=docs/experiments/evidence/value_chooser_ab_20261031
Work in /home/user/sts_ai.
1. git fetch origin && git checkout --detach $RUN_COMMIT && git status --short   (must be clean; if the bare-SHA
   fetch fails: git fetch origin pull/921/head)
2. python3 -c "import xgboost, scipy, numpy" || pip install -q xgboost==3.0.5 scipy numpy
   then python3 -c "import xgboost, scipy, numpy; print('py ok', xgboost.__version__)"   -> must print "py ok"
3. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
4. bash tools/cloud/worker.sh start $CAMPAIGN <n>
5. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running", in the same turn, before you reply; never end a turn without the
   wait running. "FINISHED" -> reply with its last line (WORKER_OK ...). "NOT RUNNING" -> reply with the output and stop.
After a container restart, run steps 1-4 at once (start skips done units). Never kill units.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
