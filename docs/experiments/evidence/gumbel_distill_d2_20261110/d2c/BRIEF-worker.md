# Gumbel distillation D2c (D2 continued on fresh seeds, after D2b; teacher factory, G16 + max backup, whole runs): cloud worker brief

YOUR WORKER NUMBER: W=<n>   (1..40; pass it unpadded, never 03)
RUN_COMMIT=<RUN_COMMIT>  CAMPAIGN=docs/experiments/evidence/gumbel_distill_d2_20261110/d2c

Philipp authorized this continuation on 2026-11-10 at 23:15 CET ("Kannst du auch einfach die Worjer bis morgen um 8 uhr laufen lassen für mehr Daten?"); D2 itself was authorized at 21:49 CET. Start it only after your D2b wait printed FINISHED (WORKER_OK).
- Do not change seeds, scripts, environments, binary, weights or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads only to /mnt/project-files/gumbel-distill/d2c (units/, claims/, wWW.DONE.json). Write nothing else to the share.

1. In the FOREGROUND (timeout 10 min):
   cd /home/user/sts_ai && git fetch --depth 1 origin $RUN_COMMIT && git checkout --detach $RUN_COMMIT && git rev-parse HEAD && git status --short
   Then also fetch the code commit the binary is built from: git fetch --depth 1 origin 823bbad0b07b6a719c0b186541a84384860d29ef
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
Expect 30 min to 3 h per unit (8 A20 runs of silverazgen with the whole-run Gumbel root at flat 16,000 simulations
and max backup), 4 units at a time; 320 units (2,560 runs) shared by 40 workers through the queue (about 2.5 h after D2b).
