# swkeyed sibling-label replay (#883 / PR #903): cloud worker brief

YOUR WORKER NUMBER: W=<n>   (pass it unpadded, 1..16)
RUN_COMMIT=__RUN_COMMIT__  (branch claude/project-thread-tt1jc5-run)  CAMPAIGN=docs/experiments/evidence/ooc_swkeyed_labels_20261028

Philipp authorized this run (2026-10-28 15:20Z: "Go with 16 workers").
- Do not change seeds, scripts, environments, binary, weights or timeouts.
- Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec).
- The worker script uploads the finished units and wWW.DONE.json to /mnt/project-files/ooc-swkeyed-labels. Write
  nothing else to the share.

1. cd /home/user/sts_ai && git fetch origin claude/project-thread-tt1jc5-run && git checkout --detach $RUN_COMMIT
   && git rev-parse HEAD && git status --short   (HEAD must equal RUN_COMMIT; status must be clean)
   - This commit is based on an older main (2026-10-22). Run `git submodule update --init --recursive` if setup asks
     for submodules.
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   - Re-arm it each time it returns "still running", in the same turn, before you reply. Never end a turn without the
     wait running.
   - "FINISHED": reply with its last line (WORKER_OK ...).
   - "NOT RUNNING": reply with the output and stop.
   - After a container restart, run steps 1-3 at once (done units are skipped).

If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Never kill a unit or one_combat process. A unit that times out ends with rc=124, and the run continues.
Keep the session alive until you are told the tar is verified.
Expect about 2.5-4 h wall per worker. Units run longest first: a replay of one §644 game plus 32 swkeyed label
rollouts at every searched root's children.
