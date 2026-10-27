# P300 clairvoyance 2x2: cloud worker brief

YOUR WORKER NUMBER: W=<n>   (pass it unpadded: 1 or 2, never 01)
RUN_COMMIT=<frozen sha, given in the header>  CAMPAIGN=docs/experiments/evidence/p300_clairvoyance_20261026

Philipp authorized this run (2026-10-26 22:31Z, "lets do it on this on 2 workers").
- Do not change seeds, scripts, environments, binary or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads only to /mnt/project-files/p300-clairvoyance/run-2x2 (units/, claims/, wWW.DONE.json).
  Write nothing else to the share.

1. cd /home/user/sts_ai && git fetch origin && git checkout --detach $RUN_COMMIT && git status --short   (must be clean)
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   - Re-arm it each time it returns "still running", in the same turn, before you reply. Never end a turn without
     the wait running.
   - "FINISHED": reply with its last line (WORKER_OK ...).
   - "NOT RUNNING": reply with the output and stop.

If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Never kill a unit or one_combat process. A unit that times out ends with rc=124, and the run continues.
If the container restarts, run steps 1-3 again at once (finished units are skipped).
Keep the session alive until you are told the tar is verified.
Units: 384 (one cell x one Heart deck: 12 variants x 4 copies = 48 fights), 4 at a time. Fair units take about
7-15 min, known units about 3-5 min. Expect about 4 hours per worker.
