# Gen6 E2500 selective OOC audit: valid canary, invalid cohort

**Cohort verdict:INVALID_OR_INSUFFICIENT**, reason`failed source process`.
The renewed canary is CANARY_VALID, but both initially dispatched sources
failed and the remaining six never launched. No quality effect, interval,
training suitability or run-win result is inferred from the partial capture.

Philipp authorized the fresh canary/comparison and cited
[PR547](https://github.com/pherrman1/sts_ai/pull/547). Its1080 paired A20 fights
motivate gen6 E at2500 simulations:versus plain2500 fight score+3.85
[+1.23,+6.52]; versus plain10k+1.04[−1.43,+3.46], inconclusive.
Those nominal legacy fight-level scores do not establish OOC ranking, equal-CPU
benefit, equivalence or whole-run wins. Same full gen6 E model hash verified
from PR547 head80687eb4b4392f41e9b91d9e0c01f527ad4a7a00 before launch.
No code/new terminal objective from that PR is imported.

## Freeze and execution

Clean independently reviewed producer:d3e33b46856155d65d382db5ae4351a9f00e8d45.
Binary:ca14a43ce7f9f86ba39e7647304f4ada14c8539d71e61e5cc5ca63fc60c91e1e.
Freeze:9ec9b834589f7fedbd717f4ce74176af4783a841e01a461cbd9a3e9fdcb4913c.
All16 dependencies copied/hash-verified, all111051 streams independently
rederived before launch. Excluded fresh canary97151101; original unopened
cohort97151010–97151017 retained with their identical old stream arrays.
Run-1 remains separately invalid/excluded, without pooling or reclassification.
CTM4096, gen6 E2500/K8/weight400, plain10k source/reference, V4/X2-B,
requested-three-combat first-MAP checkpoint, candidate selection, caps and
4096 matched-CTM pair ceiling fixed before launch.

Canary:exit0/no timeout,193.25CPU/195.102446wall seconds. Source/control25
captured actions,7 RAW battles and summary match exactly; baseline repeat,
64 fixed draws and8 CTM prefix pairs pass. Itemized child CPU including
0.016525s provenance equals184.297805s total, zero residual. Independent
report reproduction is exact. The matched CTM arm reaches4096 pairs at
ratio0.176025, correctly leaving matched compute unresolved.

| Cohort source | Completed roots | Failure location | CPU seconds | Wall seconds |
| --- | ---: | --- | ---: | ---: |
|97151011|1|Act2/floor19, decision65, Silver8 future1/candidate1|97.05|99.399528|
|97151010|2|Act3, decision122, plain10k reference future1/candidate0|316.47|321.281032|

Both source returncodes1, without timeout or source_complete. Each ends with
replay_child_failed_status_32000, which decodes normal child exit125 rather
than a terminating signal. Source11 has84 starts/83 completions, source10
163/162. Corresponding failed future seeds:4817961396640544830 and
13681190408072724534. The frozen generic fork helper catches exceptions around
evaluate().dump(), suppresses child stderr and exits125, erasing the underlying
message/type/stage. The records establish where an exception escaped but do
not identify an unsupported encounter, native simulator defect or CPU-limit
kill. The failure in the plain10k reference prevents attribution solely to the
gen6 prior or2500 budget. Actual failed-root candidate keys/combat index were
not retained because those root_complete records never emitted.

Dispatch stopped after source11 failed; source10 was already active and drained.
Seeds97151012–97151017 have no latch/output files. Total process CPU including
canary606.77s. Independent GNU-time/custody/report/no-further-dispatch auditPASS.
No process currently references the frozen run-2 executable; this is absence
evidence, not a PID-specific cleanup receipt. No scientific retry, seed
replacement, survivor quality analysis or model/default promotion.

## Scoped diagnostic repair and next boundary

The separate repair wraps only the audit callback in a strict success/error
envelope. It transports bounded printable standard messages/nonstandard
categories, retains failed-child CPU, and rejects errors before aggregation.
Fixed evaluation-start records now retain candidate key/bits and future seed.
Ordinary replay-fork behavior, models, RNG, budgets and scientific failure
rules remain unchanged. Real seed-free fork tests cover success passthrough,
standard/nonstandard exceptions, oversized/non-UTF8 text and malformed errors.
Serialization/transport errors outside the envelope can still have generic
status. It cannot recover the old lost messages or reclassify this cohort.

Next useful evidence is one separately authorized diagnostic replay of a
failed source with this error transport, stopping at its first failure. A
new full cohort is premature until the actual exception is identified.

Knowledge impact:failed evidence in §479/current research; maintained opt-in
error-transport interface. Original protocol/tools/data/receipts/latches and
reports are preserved in the packet and local build/ooc-selective-silver-audit/run-2.

Verification:pre-freeze ReleasePASS,16 synthetic testsPASS and5/5 focused
CTestsPASS2.80s. Diagnostic repair ReleasePASS and5/5 affected CTestsPASS3.00s,
including real seed-free exception transport. Independent prospective delta,
prelaunch custody, exact canary/report reproduction, invalid-cohort preservation
and narrow repair reviewsPASS. EVIDENCE.json binds preserved archives/checks.
