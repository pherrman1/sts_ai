# Worker brief: obvious-mistakes-probes (8 workers)

Authorization: Philipp 2026-11-15 21:31 CET "oke für jedes muster jetzt eine gepaarte probe" (#1056 thread) and his
choice "40 Worker, 128 Zustände je Muster": 512 paired probes, about 150 core-hours; later the same evening he split
the workers with #1053 Stage 3, which leaves 8 workers for this campaign.
RUN_COMMIT=<RUN_COMMIT>   (set in the share copy of this brief after the prelaunch review)
CODE_COMMIT=6de313e5b55c218dbda28e7d31d732e4a595de18

YOUR WORKER NUMBER: W=<n>   (pass it unpadded, 1..8; never 03)
CAMPAIGN=docs/experiments/evidence/obvious_mistakes_probes_20261115
Work in /home/user/sts_ai. Run nothing from /mnt/project-files (noexec). Do not change seeds, scripts, environments,
binary, models or timeouts. The worker script uploads only to /mnt/project-files/obvious-mistakes-probes (units/,
claims/, wWW.DONE.json); write nothing else to the share.
1. In the FOREGROUND (timeout 10 min):
   cd /home/user/sts_ai && git fetch --depth 1 origin $RUN_COMMIT && git fetch --depth 1 origin $CODE_COMMIT && git checkout --detach $RUN_COMMIT && git rev-parse HEAD && git status --short
   (HEAD must equal RUN_COMMIT; status must be clean for tracked files). If a fetch fails, retry up to 4 times
   (wait 2 s, 4 s, 8 s, 16 s).
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must end with "setup ok" (binary comes from the cache)
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running", in the same turn, before you reply; never end a turn without the
   wait running. "FINISHED" -> reply with its last line (WORKER_OK ...). Anything else -> reply with the output and stop.
After a container restart, run steps 1-3 at once (start skips done units). Never kill a unit or one_combat process.
If you worked on an earlier campaign, its files are finished; leave them alone, this is a new job.
Stay alive until the author thread says your tar is verified. If the author asks for an early stop, run
bash tools/cloud/worker.sh stop $CAMPAIGN <n> (no new units; running ones finish), then keep the wait running.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
Expect 5-40 min per unit (two games of one seed), 4 units at a time; 512 units shared by the workers through the
queue, about 5 h in all on 8 workers. Share footprint about 2,200 files and 100 MB.
