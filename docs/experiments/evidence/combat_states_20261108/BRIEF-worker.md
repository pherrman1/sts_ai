# Combat states (combat plan stage 0): cloud worker brief

YOUR WORKER NUMBER: W=<n>   (1..18; pass it unpadded, never 03)
RUN_COMMIT=<RUN_COMMIT>  CAMPAIGN=docs/experiments/evidence/combat_states_20261108

Philipp authorized this run on 2026-11-08 at 00:57 CET ("du hast für beide phasen je 18 worker zur Verfügung,
starte die wenn nötig ... Frag nicht nach Erlaubnis, starte einfach").
- Do not change seeds, scripts, environments, binary, weights or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads only to /mnt/project-files/combat-plan/states (units/, claims/, wWW.DONE.json). Write nothing else to the share.

1. In the FOREGROUND (timeout 10 min):
   cd /home/user/sts_ai && git fetch --depth 1 origin $RUN_COMMIT && git checkout --detach $RUN_COMMIT && git rev-parse HEAD && git status --short
   (HEAD must equal RUN_COMMIT; status must be clean for tracked files). If the fetch fails, retry up to 4 times
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
Keep the session alive until you are told the tar is verified.
Expect 20-60 min per unit (8 A20 runs of silverazgen at flat 10,000 simulations), 4 units at a time; 384 units shared by 18 workers through the queue (about 3 h).
