# Cloud campaigns

`tools/cloud/worker.sh` is the single entry point for mass cloud runs (several worker threads, each one
container with 4 CPUs). One fixed path lets the project's permission allowlist cover every campaign. It also
stops each campaign from re-implementing setup, upload and verification in its own wrapper.

## Campaign directory

Put a campaign under `docs/experiments/evidence/<campaign>/`, committed at the run commit:

```
campaign.manifest   frozen keys
units.txt           one unit per line; '#' lines and blank lines are ignored
run_unit.sh         bash run_unit.sh REPO RUN UNIT_OUT <unit args...>   (exit 0 = unit done)
```

`campaign.manifest`, one `key value` per line:

```
name          potion-weights            # lowercase [a-z0-9_-]; local dir is $HOME/cw-<name>-wWW
code_commit   <40-char sha>             # build inputs (apps src include extern cmake models ...) must equal it
binary_sha256 <64-char sha256>          # of build/linux-gcc-release/one_combat at code_commit
workers       8                         # unit line i (0-based, after skipping comments) goes to worker i%workers+1
share         /mnt/project-files/<dir>  # where wWW.tar and wWW.DONE.json are uploaded
parallel      4                         # units run at once per worker (default 4)
input studentc.bin /mnt/project-files/student-c-488/studentc.bin <sha256>   # copied into RUN, hash-checked
```

`run_unit.sh` gets the repo checkout, `RUN` (holding `one_combat`, the inputs and `FROZEN.txt`), its own
output dir, and the unit's words as arguments. Unit seeds must go through `tools/seed_guard.sh` as usual.
Everything the analysis needs must be written under the unit output dir. The worker tars `out/` and
`FROZEN.txt`.

## Freeze (author)

1. Merge every PASSED fix that touches the run's code path into main first, then freeze. See
   [agent workflow](../../docs/knowledge-base/operations/agent-context-and-workflow.md#frozen-runs).
2. Commit the campaign dir. Set `code_commit` and, after one build, `binary_sha256`.
3. `bash tools/cloud/worker.sh publish-binary <campaign>` builds at `code_commit`, checks the hash and uploads
   the binary to `/mnt/project-files/bin-cache/one_combat-<sha256>` (plus `commit-<sha>.sha256`). Workers
   then copy it instead of building, which saves 4-9 min per worker. A worker that finds no cached binary,
   or one with the wrong hash, falls back to a local build and the same hash check.
4. The pre-launch reviewer does an independent clean build and checks it against `binary_sha256`. That
   check is what makes the cached binary trustworthy.

## Worker brief (template)

```
YOUR WORKER NUMBER: W=<n>   (pass it unpadded; never 03)
RUN_COMMIT=<sha>  CAMPAIGN=docs/experiments/evidence/<campaign>
1. git fetch origin && git checkout --detach $RUN_COMMIT && git status --short   (must be clean)
2. bash tools/cloud/worker.sh setup $CAMPAIGN <n>      -> must print "setup ok"
3. bash tools/cloud/worker.sh start $CAMPAIGN <n>
4. In a background Bash task (timeout 2 h): bash tools/cloud/worker.sh wait $CAMPAIGN <n> 110
   Re-arm it each time it returns "still running". "FINISHED" -> reply with its last line (WORKER_OK ...).
   "NOT RUNNING" -> reply with the output and stop.
If any step is refused or prints STOP, reply with the exact output and stop. Do not work around it.
```

The worker needs no release message. After FINISHED it has nothing left to do. `stop` makes it start no new
units, and `status` prints progress.

## Verify (lead)

```
python3 tools/cloud/verify_campaign.py docs/experiments/evidence/<campaign>
```

This checks every worker's tar against its `DONE.json` and against the units `units.txt` assigns to it. It
prints `OK:`, `MISSING:` and `BAD:` worker lists, and exits 0 only when every worker is OK. Use those lists,
not the workers' chat, to decide which threads to release and which to relaunch.

## Reviewers: base binaries

`bash tools/cloud/worker.sh cache-get <sha256> $HOME/base/one_combat` fetches a binary someone already
published, for example the base side of a default-off identity check. `cat
/mnt/project-files/bin-cache/commit-<sha>.sha256` gives the sha256 for a commit. The PR side is still built
fresh.
