# Worker brief: Silver victory-leaf combination A/B

YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=<sha>  CAMPAIGN=docs/experiments/evidence/silver_leaf_combo_20261018

Authorization: Philipp 2026-10-18 17:38Z ("can you try all these things? ... on a20") and his size pick in the
"end-state formula" thread. This worker runs its share of units.txt (seven arms of each of its seeds; A20 seeds
111198434-111198945 over all workers), 4 at a time, A20 full runs without OOC MCTS. Uploads go to
/mnt/project-files/silver-leaf-eval/combo-ab/.
Work in /home/user/sts_ai.

1. git fetch origin && git checkout --detach $RUN_COMMIT && git submodule update --init --recursive && git status --short
   (must be clean)
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running". "FINISHED" -> reply with its last line (WORKER_OK ...).
   "NOT RUNNING" -> reply with the output and stop.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
