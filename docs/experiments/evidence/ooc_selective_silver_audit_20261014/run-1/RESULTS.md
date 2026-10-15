# Selective gen6 E Silver OOC audit: invalid canary

**Verdict:INVALID_OR_INSUFFICIENT.** The excluded canary completed its source
run and all selected-root computations, but the frozen analyzer rejected child
CPU settlement. The eight-source cohort was never dispatched. No comparison
of teacher quality, decision utility, training suitability or run wins follows.

Frozen producer:695e95a590125218d244c884a48c74b96bde228c (reviewed implementation).
Binary:b3e89dca6bc15fbec3a9faa156366a58122800d47b42e8e71392fcb8df6c7bd5.
Freeze:d2ce0084d7f885f49f1a549461c693d3ec9f1dcc912aff663cf52bdfd16467a8.
Original protocol:6286948bc355cd6932690ddab05c6aa2c7006339729452a57c7b2a7b34ec6634.
Exact gen6 E priorca9bd7f2… and calibrated A20 CTM manifest00bb4da6… are
unchanged. Original files and latches remain at
`build/ooc-selective-silver-audit/run-1/`; all16 frozen dependencies were copied
and hash-verified before the accounting repair. The current protocol/tooling
contains that repair; the archive preserves the actual frozen originals.

## Executed scope and diagnosis

Only excluded seed97151001 launched, including its prescribed source-only
control. Parent returncode0, no timeout:219.82 process CPU seconds,
223.505686 wall seconds. Source ended at Act2/floor33, with20 real battles and
117 recorded actions. Two eligible roots were retained (Act1/floor3,
Act2/floor19); no Act3 root existed. Source/control action, RAW battle and end
traces match exactly; both repeated baseline searches match, including full
4096 work. Each root retained16 CTM8 evaluations,16 Silver8 evaluations,
32 independent plain10k reference evaluations and its matched-CTM records.
These are integrity checks, not cohort quality evidence.

Retained child costs sum204.717603s, while the producer's scoped final
RUSAGE_CHILDREN total is204.729388s:unassigned0.011785s. Header construction
calls fileSha256(plan) and effective-policy provenance hashes after its clock
starts. fileSha256 uses popen/pclose to invoke sha256sum, creating reaped
utility subprocesses outside the retained evaluator-child wrapper. The omitted
subprocess category is confirmed by code; exact attribution of every residual
microsecond is an inference because individual utility timings were not saved.
The analyzer correctly fails closed instead of widening tolerance.

The first matched-CTM arm also hit its4096-pair ceiling at only0.474× the
Silver8 CPU, so this attempt could not support a matched-CPU benefit even if
its integrity gate had passed. Act2 reached3693 pairs with ratio1.015. No
favorable subset, survivor pooling, primary effect or confidence interval is
reported from the excluded failed canary.

## Repair and completion boundary

The narrow repair measures pre-game startup/provenance utility-child CPU in a
separate header field, includes it in the existing1200s child allocation,
uses whole-process parent/child accounting, and reconciles that measured bucket
plus all retained evaluator/control forks at the unchanged tolerance. A
seed-free regression exercises the actual fileSha256 subprocess; synthetic
analysis rejects a missing measured bucket. This repairs tooling only.

Run-1's report remains invalid. No retry, changed cap, replacement seed or
cohort launch was performed. A separately authorized new freeze/canary is
needed before future expensive execution. The current source remains stacked
on unmerged PR539; no runtime default or model was promoted.

Knowledge impact:failed experiment in §475/current research; explicit opt-in
CPU-accounting contract in maintained architecture. Original attempt preserved.

Repair verification:final Release rebuildPASS,15 synthetic testsPASS,
5/5 affected guarded CTestsPASS2.84s, including the real provenance-child hash
utility check. Independent repair reviewPASS; independent invalid-outcome
custody auditPASS. [EVIDENCE.json](EVIDENCE.json) hashes the raw/check/source
tool archives; local binary/full source archive are explicitly listed.
