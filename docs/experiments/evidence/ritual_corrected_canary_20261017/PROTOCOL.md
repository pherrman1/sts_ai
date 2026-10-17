# One-source corrected RAW producer canary — prepared, not run

Purpose: exercise the existing corrected native producer once, measuring RAW
capture integrity, observed Ritual Dagger growth and throughput. The four
deterministic lethal-card RAW serialization tests already prove positive
transfer semantics. This run asks whether the ordinary teacher encounters
growth during one retained trajectory. It is not training or qualification.

## Fixed source and teacher profile

- Source **52000001**, count **1**, ascension **0**, caller budget **10,000**.
- Selection is the smallest seed in `52000000..52000399` listed in the
  original `p1/split_manifest.json` TRAIN members. Only membership chose it;
  no historical outcome was inspected for selection. `selection.json` pins
  the split and original manifest. This is reused TRAIN development evidence.
- Existing producer: `combattransitionforcedgen`, setup `ritual_writhing`.
  It adds the Dagger before the first fight and forces ordinary Act-3 monster
  rooms to Writhing Mass. No new producer, intervention or policy is added.
- Native Silver, `project_fair`, plain learned stopping, stop model
  `gbt-770201c31f7b`, threshold `0.0323`, allocated reuse cap 32,768,
  adaptive/exact-root budgets/sequential halving/pruning/root prior off.
- Preserve the historical Path B OOC chain, rather than enabling OOC MCTS.
  No Arm C, CTM model, rollout student or GPU is enabled.
- Preserve historical rollout/leaf semantics explicitly: legacy greedy
  rollout table (`STS_SILVER_ROLLOUT_CARD_TABLE=0`), one rollout per leaf,
  uniform rollout off, and final-fight/no-loss-potion-credit/relic-heal leaf
  terms all **0**. Those leaf terms and the current default G6 rollout table
  did not exist in the old producer source. Leaving them at modern defaults
  would silently change the teacher.

`teacher-template.json` copies the old manifest's teacher, models and search
profile. After all source fixes are committed and the reviewed live PR branch
is merged, the parent supplies the exact clean source SHA, merged reviewed
live SHA, and freshly built `one_combat` executable. `freeze` fills the new
teacher ID/source/executable SHA and pins its model hashes. It refuses changed
historical model files or an incompatible compiled learned-stop model.

The source deliberately differs from the original producer through corrected
Ritual persistent transfer, half-dead eligibility, corrected native event
closure, and the reviewed live branch's absolute 1,000-action Silver playout
cap. No claim of bitwise old-teacher replay is made. Record the complete final
source identity and executable build receipt before running.

## Exact command and flag truth

The only seed-driving child command is constructed without optional extra
arguments:

```sh
bash tools/seed_guard.sh "$EXE" combattransitionforcedgen \
  1 10000 0 "$OUT/rows.jsonl" 52000001 "$OUT/teacher.json" ritual_writhing
```

The child receives a newly constructed environment containing the complete
teacher environment plus CPU/resource variables. No caller `STS_*` settings
are inherited. CPU affinity is one allowed CPU; OMP thread count and limit,
OpenBLAS and MKL threads are one; `CUDA_VISIBLE_DEVICES` is empty.

The producer's `loadWholeCombatTeacher` checks source/executable/model hashes,
all declared environment strings, compiled learned-stop model/threshold,
effective plain learned stopping, singleton-root behavior, reuse cap, and
the three explicitly recorded leaf terms before any source trajectory.
Rollout settings are explicitly fixed in the declared environment and parsed
by the reviewed source. A mismatch must stop; do not edit the teacher or
relax provenance to obtain a run.

After completion, verify the output manifest's exact new teacher, source and
executable identity, seed specification, forced setup and `pathb_chain` OOC
policy. Run the existing RAW corpus contract on the complete output. Record
startup stdout/stderr and producer provenance; declared flags alone are not
proof that incompatible source honored them.

## Budget, retention and decision rule

One source, one CPU, **300 seconds** wall time, **8,000,000,000-byte virtual
address-space ceiling**, no GPU. A timeout sends TERM to only this run's new
process group, waits at most five seconds for cleanup, then KILLs that same
group if needed. The 300-second collection budget is not extended by cleanup.
There is no resume, retry, replacement seed or seed extension.

Retain every row and every victory, death, escape, quarantine and incomplete
outcome. Do not discard a trajectory because it dies before Act 3. The
existing producer buffers a source's rows until it finishes: a timeout can
therefore leave an empty partial JSONL, which is an incomplete result rather
than evidence of zero fights.

Report:

- Process exit/timeout, elapsed seconds, total RAW rows and rows/second.
- Capture counts, all outcome counts, quarantine/integrity results.
- Any positive Ritual growth and its pre/post card identity/damage values.
- Writhing-intersection rows and positive intersection growth separately.

A valid capture requires process exit 0 without timeout, more than zero rows,
exactly one RAW capture on every row, exactly one requested/source/completed
seed, zero quarantined seeds, zero quarantined rows, and zero UNDECIDED
outcomes. A full transition with `runValid=false` remains quarantined and
cannot pass. Parsing or corpus-contract exceptions produce a terminal
`result.json` with the error and invalid classification, retaining the raw
output and logs.

If complete RAW capture is valid and growth is observed, classify
`CORRECTED_PRODUCER_CANARY_GROWTH_OBSERVED`. This establishes only this source's
producer behavior. If no eligible growth occurs, report
`COVERAGE_INCONCLUSIVE_NO_RETRY`; do not extend automatically. If the run or
contract is incomplete/invalid, report
`CANARY_INCOMPLETE_OR_INVALID_NO_RETRY`. Intersection growth remains
`INCONCLUSIVE` if no positive intersection example occurs, even when earlier
non-Writhing fights show growth.

The full JSONL, manifest, producer provenance, teacher, frozen command/env,
logs, exit receipt and metrics remain saved. No fitting, model selection,
TEST opening, support edit or production promotion follows this canary.
A larger collection requires a separately authorized frozen campaign.

## Review and later execution

The parent first completes source review/commit and merges the reviewed live
branch into the task branch, then builds the final executable. Freeze source,
binary and model hashes only at that point. A mandatory input build receipt
binds the clean source and executable to the successful build. Its schema is
`reviewed_source_build_v1`, with fields:

- `sourceSha`, `reviewedLivePrSha`, absolute `workingDirectory` and `executable`,
  and `executableSha256` matching the final source identity.
- `sourceCleanBeforeBuild: true`, `sourceCleanAfterBuild: true`, `returnCode: 0`.
- `command`: the exact build argv beginning `cmake --build` and explicitly
  targeting `one_combat` with `--target one_combat`.
- Absolute `logPath` and matching `logSha256` for retained build output.

The parent also records exact configure argv/outcome/log identity, source tree,
and clean Git-status evidence in the same receipt. Freeze hashes the complete
receipt and copies it into the output directory; execution rechecks the
original receipt, retained build log, copied receipt, source and executable.
The packet identity includes the packet's synthetic safety tests. The reviewer approves this fixed
packet at the final source SHA with JSON containing `verdict: PASS`,
`sourceSha`, and `packetIdentity` from the script's `identity` command.

```sh
# Read-only packet hashes for review; no source collection.
python3 build/ritual-corrected-canary-plan/canary.py identity

# Parent fills these identities only after final commit/merge/build/review.
python3 build/ritual-corrected-canary-plan/canary.py freeze \
  --source-sha "$FINAL_SHA" --live-sha "$REVIEWED_LIVE_SHA" --exe "$EXE" \
  --build-receipt "$BUILD_RECEIPT" --review "$REVIEW" --out "$OUT"

# Only after the frozen packet is approved for this one execution.
python3 build/ritual-corrected-canary-plan/canary.py run --review "$REVIEW" --out "$OUT"
```

The output directory must be new. An exclusive `run-started.json` latch
prevents reruns, including after failure. `freeze` does not run the producer.
This prepared packet has not frozen final source/binary identities and has
not launched collection.

Knowledge impact: temporary canary protocol only; executed evidence and any
new durable interpretation are recorded by the parent after the run.
