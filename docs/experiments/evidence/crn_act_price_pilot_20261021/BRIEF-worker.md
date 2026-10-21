# Worker brief: CRN act-end price pilot

YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=<sha>  CAMPAIGN=docs/experiments/evidence/crn_act_price_pilot_20261021

Authorization: Philipp 2026-10-21 13:44Z ("Let's do 4 workers to speed it up after the smoke finishes"). This worker
runs 16 units from units.txt (one A20 potionpriceprobe source run each, seeds 111146000-111146063 over 4 workers),
4 at a time, about 1-2 h. Uploads go to /mnt/project-files/silver-leaf-eval/crn-act-pilot/.
Work in /home/user/sts_ai.

1. git fetch origin && git checkout --detach $RUN_COMMIT && git submodule update --init --recursive && git status --short
   (must be clean)
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running". "FINISHED" -> reply with its last line (WORKER_OK ...).
   "NOT RUNNING" -> reply with the output and stop.
Never kill units. If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
