# Worker brief: gumbel-wholerun (40 workers)

Authorization: Philipp 2026-11-08 23:23 CET "gepaarte bestätigung bitte mit dem ppo 420 net. und versuch mal default
vs 16k gumbal, 32k gumbel und 64k gumbel mit max backup 4. erst nachdem der momenate test gumbel run fertig ist, auf
40 worker dann." (planning thread of this project).
RUN_COMMIT=<RUN_COMMIT>   (set in the share copy of this brief after the prelaunch review)

YOUR WORKER NUMBER: W=<n>   (pass it unpadded, 1..40; never 03)
CAMPAIGN=docs/experiments/evidence/gumbel_wholerun_20261108
Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec). Do not change seeds, scripts, environments,
binary, models or timeouts. The worker script uploads only to /mnt/project-files/gumbel-wholerun (units/, claims/,
wWW.DONE.json); write nothing else to the share.
1. In the FOREGROUND (timeout 10 min):
   cd /home/user/sts_ai && git fetch --depth 1 origin $RUN_COMMIT && git checkout --detach $RUN_COMMIT && git rev-parse HEAD && git status --short
   (HEAD must equal RUN_COMMIT; status must be clean for tracked files). If the fetch fails, retry up to 4 times
   (wait 2 s, 4 s, 8 s, 16 s).
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must end with "setup ok" (binary comes from the cache)
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running", in the same turn, before you reply; never end a turn without the
   wait running. "FINISHED" -> reply with its last line (WORKER_OK ...). Anything else -> reply with the output and stop.
After a container restart, run steps 1-3 at once (start skips done units). Never kill a unit or one_combat process.
If you worked on an earlier campaign, its files are finished; leave them alone, this is a new job.
Stay alive until the author thread says your tar is verified.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Expect 1-60 min per unit (one seed: arms D, G16, G32 in one unit, G64 in another), 4 units at a time; 2,048 units
shared by 40 workers through the queue, about 3 h in all.
