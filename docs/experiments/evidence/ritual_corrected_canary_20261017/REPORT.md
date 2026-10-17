# Corrected Ritual RAW producer canary

The single frozen TRAIN source **52000001** completed successfully at clean
source `b94da9bc13f868f39e5814c5c1a7d66fd20ec793`, executable SHA-256
`74b95ff524a1743772b98ad55007d758222d3675b4bee731cc9c5a19a29ba330`.
The reviewed one-use packet fixed one CPU, no GPU, 10,000 caller simulations,
a 300-second wall ceiling and an 8 GB address-space limit. The run completed
in **16.34412451798562 seconds** without timeout or retry.

All **24** RAW rows have exactly one capture, a valid victorious transition,
and the matching teacher. Source accounting is 1/1 complete, with zero
quarantined seeds/rows and no unresolved outcomes. Acts contain 9/9/6 rows
for Acts 1/2/3; none is Act 4. The original Dagger grows **15→18** in fight 12
and **18→21** against Writhing Mass in fight 18. Three fights are Writhing
intersections; one has positive growth. An independent reviewer recomputed
all counts, growth, source accounting, manifests and custody from the full
RAW file.

Classification: `CORRECTED_PRODUCER_CANARY_GROWTH_OBSERVED`.
This proves source-bound producer behavior and provides one throughput
observation. It does not qualify a model, establish representative frequency,
justify a fit objective, or remove a support exclusion.

## Effective teacher and limitations

This is the **current-source Path-B teacher with key collection ON**. The
frozen environment did not explicitly set `STS_COLLECT_KEYS`; startup stdout
and source confirm the compiled default ON. The producer provenance records
that option as null. The original protocol's historical leaf/rollout controls
were explicit, but it does not establish exact reproduction of an older
teacher or a paired comparison. Future collection must freeze key collection
explicitly. The reviewed packet was not changed or rerun after this finding.

No Arm C, CTM rollout, student, model fitting, TEST numerical access, support
promotion or deployment occurred. This source was selected by original TRAIN
membership alone. It cannot supply upgraded/multicopy/Brew/Smoke coverage;
the existing setup guarantees only one ordinary Dagger and forced Act-3
Writhing rooms. A controlled producer extension and a separately authorized
collection campaign are prerequisites for adequate corrected data.

## Evidence and verification

- [Frozen protocol](PROTOCOL.md), [pre-run review](pre-run-review.json),
  [freeze](freeze.json), [build receipt](build-receipt.json),
  [teacher](teacher.json), [producer manifest](rows.jsonl.manifest.json),
  [producer provenance](rows.jsonl.provenance.json).
- [Result](result.json), [independent result review](result-review.json),
  [exit](exit.json), [one-use latch](run-started.json),
  [stdout](stdout.log), [stderr](stderr.log).
- Merged Debug selected build passed. [Initial CTests](merged-debug-tests.log)
  passed 12/13; the remaining test used a stale unit-test command registry.
  Rebuilding that target passed the [rollout check](merged-rollout-retest.log)
  and [seven affected unit checks](merged-unit-retests.log). All 13 affected
  checks therefore pass on rebuilt targets. [Release protocol](release-protocol.log)
  passed 1/1 in 1.99 s, and [Python checks](merged-python-tests.log) passed
  45/45 in 0.173 s. Exact raw configure/build logs remain bound by the build
  receipt.

The complete RAW file remains preserved at
`build/ritual-corrected-canary-20261017/rows.jsonl`, SHA-256
`fd4727e0072757b067ad13fcab128d091af7da9d18c60a1a11a8e46777300d6a`.
The original reviewed five-file packet and build logs remain in the ignored
`build/ritual-corrected-canary-plan/` and `build/ritual-corrected-build/`.
These evidence copies preserve their original paths and hashes; do not treat
the copied historical protocol as a new execution authorization.

Knowledge impact: corrected producer has one source-bound positive Writhing
example; corrected training/qualification coverage remains open.
