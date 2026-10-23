# Worker brief: turn-dominance (8 workers)

```
YOUR WORKER NUMBER: W=<n>   (1..8; pass it unpadded, never 03)
RUN_COMMIT=<sha from the launch message>  CAMPAIGN=docs/experiments/evidence/turn_dominance_20261023
Work in /home/user/sts_ai.

1. In the FOREGROUND (never as a background task; timeout 10 min):
     cd /home/user/sts_ai && git fetch origin claude/project-thread-a1phl2 main && git checkout --detach $RUN_COMMIT
     git rev-parse HEAD     -> must print exactly $RUN_COMMIT
     git status --short     -> must print nothing for tracked files
   If the fetch fails or hangs, retry it in the foreground up to 4 times (wait 2 s, 4 s, 8 s, 16 s).
   If HEAD is still not $RUN_COMMIT, reply with the exact output and stop.
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   When it returns "still running", re-arm it in the same turn before you reply; never end a turn without the wait
   running. "FINISHED" -> reply with its last line (WORKER_OK ...). "NOT RUNNING" -> reply with the output and stop.

After a container restart (the checkout or $HOME/cw-turn-dominance-wNN looks reset, or "wait" says NOT RUNNING
right after you were resumed): run steps 1-3 at once, then step 4. "start" skips units already done or uploaded;
never delete the cw- dir or the share files.

Never kill one_combat or a unit. Keep the thread alive (the background wait task) until you are told
"Your tar is verified. You can stop now."
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
```
