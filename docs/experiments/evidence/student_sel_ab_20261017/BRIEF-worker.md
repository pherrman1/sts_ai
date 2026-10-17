# Worker brief: card-select student A/B (§524)

YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=<sha>  CAMPAIGN=docs/experiments/evidence/student_sel_ab_20261017

Authorization: Philipp 2026-10-17 21:45Z ("64 seeds" card; "use 8 workers for that"). This worker runs 16 units (8 seeds x
arms A/B) from units.txt, seeds 111193400-111193463, A20, full runs. Uploads go to /mnt/project-files/student-sel-ab/.

1. git fetch origin && git checkout --detach $RUN_COMMIT && git submodule update --init --recursive && git status --short
   (must be clean)
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running". "FINISHED" -> reply with its last line (WORKER_OK ...).
   "NOT RUNNING" -> reply with the output and stop.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
