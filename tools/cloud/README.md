# Cloud campaigns

`tools/cloud/worker.sh` is the single entry point for mass cloud runs (several worker threads, each one
container with 4 CPUs). One fixed path lets the project's permission allowlist cover every campaign. It also
stops each campaign from re-implementing setup, upload and verification in its own wrapper.

## Campaign directory

Put a campaign under `docs/experiments/evidence/<campaign>/`, committed at the run commit. The worker refuses a
campaign dir outside the checkout, or campaign files that are untracked or modified, because it executes
`run_unit.sh`. Unit lines must map to distinct ids (non `[A-Za-z0-9._-]` characters become `_`).

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
workers       8                         # the worker count Philipp authorized; unit line i goes to worker i%workers+1
share         /mnt/project-files/<dir>  # where wWW.tar and wWW.DONE.json are uploaded
parallel      4                         # units run at once per worker (default 4)
schedule      queue                     # optional, default static; see "Queue schedule" below
lease_minutes 30                        # queue only: a claim without heartbeat for this long may be taken over
claim_settle_seconds 600                # queue only: how long a non-owner claimer waits before its owner check
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
units, and `status` prints progress. `setup` refuses a `$HOME/cw-...` dir left by a different freeze (another
commit, binary or campaign files), and `run` holds a lock so the same worker cannot run twice. A failed unit is
retried from an empty unit dir. WORKER_OK is not proof of delivery: the byte compare after upload may be served
from the share's local cache. The lead's `verify_campaign.py` run is the proof.

## Verify (lead)

```
python3 tools/cloud/verify_campaign.py docs/experiments/evidence/<campaign>
```

This checks every worker's tar against its `DONE.json` and against the units `units.txt` assigns to it (no
missing, extra or failed units). It also checks the tar's `FROZEN.txt` against the manifest's code commit and
binary and against the lead's copies of the campaign files, and checks that all workers ran the same commit. It
prints `OK:`, `MISSING:` and `BAD:` worker lists, and exits 0 only when every worker is OK. Use those lists,
not the workers' chat, to decide which threads to release and which to relaunch.

## Queue schedule (opt-in)

With `schedule static` (the default, and every campaign frozen before this option) unit line i belongs to worker
i % workers + 1. One slow or stalled worker then holds up the whole campaign: in the gen-1b A/B one worker sat
idle 6.8 h waiting for a resume, and the campaign took 11.1 h instead of about 4 h.

With `schedule queue` every lane of every worker takes the first pending unit (neither uploaded nor claimed): first
its static units (line i -> worker i % workers + 1) in order, then other workers' units from the end of
`units.txt`. The units spread over whatever workers are alive, and workers rarely compete for one unit:

- **Claim:** a claim is the dir `SHARE/claims/<id>.a<n>`. The share's `mkdir` is atomic only within one container;
  other containers see a new dir late; in the value-leaf A/B up to 4 workers ran one unit, 34 of the first 143 tars. So every
  claimer also writes `cand.<KEY>.wWW.<pid>` into the dir. The static owner's first attempt has KEY 0 and starts
  at once. Any other claimer (stealing another worker's unit, or taking over an expired claim) uses KEY = epoch,
  waits `claim_settle_seconds` (default 600), and runs the unit only if its candidate sorts first. While the unit
  runs, its owner rewrites `hb` (`wWW EPOCH`) every minute. A claim whose heartbeat is older than
  `lease_minutes`, or that holds `failed`, may be taken over as attempt n+1, at most 4 attempts per unit.
  Lanes start 3 s apart. The settle time is long because other containers can miss a claim for minutes: in the
  value-leaf A/B (old code), copies of one unit finished up to about 10 min apart. Waiting only costs stealing
  lanes, which run near the end.
- **Upload:** a finished unit goes to the share at once as `SHARE/units/<id>.wWW.tar` (unit dir, `.done`,
  `.log`, `FROZEN.txt`, `SETUP.txt`). A worker that dies later loses nothing, and a restarted worker uploads
  units it finished locally but had not uploaded.
- **End:** a worker finishes when no unit is left without an upload. Until then idle lanes poll every 2 min and
  take over expired claims, so they also cover a worker that stalls near the end. It then writes
  `wWW.DONE.json` (the unit ids it uploaded) and prints `WORKER_OK wWW queue units_uploaded=N`. A unit that
  failed 4 times makes `run` stop with the unit count; report it, do not rerun.
- **Timeouts:** `run_unit.sh` keeps its own per-unit timeouts (e.g. `timeout 7h` per arm, rc 124 in the unit's
  record). The heartbeat runs for the whole unit, so a long unit on a live worker is never taken over; the lease
  only matters once a worker or its container is gone. Pick `lease_minutes` well above the heartbeat interval
  (1 min) and clock skew; 30 is the default.
- **Duplicates:** if a candidate file stays invisible to another container for longer than the settle time, or a
  live worker's heartbeat stalls past the lease, two workers can still run the same unit. Units are seed-deterministic, so both results are valid;
  the verifier uses the first tar in name order and reports the duplicate.

The worker brief and commands are the same in both modes. The worker count is still Philipp's choice; it sets
the valid W values and the FROZEN identity, not the unit split. The share holds one tar per unit plus one
claim dir per attempt (about 2 files per unit).

Verify and unpack a queue campaign:

```
python3 tools/cloud/verify_campaign.py docs/experiments/evidence/<campaign> --extract $HOME/<campaign>-units
```

It checks that every unit has a tar with its `.done` marker, no `.failed` marker, and a `FROZEN.txt` matching
the manifest, the lead's campaign files and the worker named in the tar name, and that all tars name one run
commit. Worker `DONE.json` files are listed, not required. `--extract` (only when every unit is OK) unpacks
`out/units/...` in the layout of a static worker tar, for the campaign's analysis script. Release workers when
every unit is OK.

## Reviewers: base binaries

`bash tools/cloud/worker.sh cache-get <sha256> $HOME/base/one_combat` fetches a binary someone already
published, for example the base side of a default-off identity check. `cat
/mnt/project-files/bin-cache/commit-<sha>.sha256` gives the sha256 for a commit. The PR side is still built
fresh.
