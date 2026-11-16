# Prior data factory (issue #1053 next prior: G16 roots, tree nodes and playout states, silverazgen): cloud worker brief

YOUR WORKER NUMBER: W=<n>   (1..32; pass it unpadded, never 03)
RUN_COMMIT=<RUN_COMMIT>  CODE_COMMIT=<CODE_COMMIT>  CAMPAIGN=docs/experiments/evidence/prior_factory_20261116

Philipp authorized this data run on 2026-11-16 00:46 CET in the thread "Retrain playout prior on G16 targets"
("Go auf 32 workers sobald verfügbar ... lass die worker so lange laufen wie ich sage, cap auf 24h"), and again at
01:09 CET ("du hast mein go für 32 workers später").
- Do not change seeds, scripts, environments, binary, weights or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads only to /mnt/project-files/prior-factory (units/, claims/, wWW.DONE.json). Write
  nothing else to the share.

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
Keep the session alive until you are told the data is verified.
This campaign is open-ended: it has more units than it will run. The author ends it for all workers at once (the
share's STOP / STOP_AT files, at the latest 24 h after launch). Your worker then lets its running units finish
and prints "WORKER_OK wWW queue units_uploaded=N central_stop". That is the normal end, not an error.
Expect about 20-60 min per unit (2 A20 runs of silverazgen: the whole-run Gumbel root at 16,000 simulations, plus
short 2,000-simulation label searches of tree nodes and playout states), 4 units at a time.
