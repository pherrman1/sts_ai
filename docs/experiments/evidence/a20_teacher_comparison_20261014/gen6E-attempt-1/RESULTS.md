# Gen6 E teacher pilot: INVALID_OR_INSUFFICIENT

The user-selected gen6 E model loaded and passed the canary. The fixed
four-source comparison did not complete: source `97150713` reached its
180-second CPU limit. No teacher-quality, prior-benefit or simulation-budget
conclusion is supported by this attempt. The three completed sources are
not pooled as a replacement panel.

## Frozen identity and execution

- Producer: `dc9411562c72fb1828229b95aec0bd4c9fffbee6`, including main's
  PR #541 merge `531db3e33d5c38674b123932f0d701b066ef21a7`.
- Binary SHA256: `f065c3be3f6d9e73cebf03beb117e27ef8afb76d5590b244d0e1589d577be4c7`.
- Freeze SHA256: `135f3c11f90528283d385b52c9f603e792bf73bd67b4c232ee40837e3b50bd1f`.
- Prior: completed gen6 **E**, unchanged native v2 export,
  `ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228`.
- CTM: unchanged PR #524 A20 candidate; all three hashes in `freeze.json`.
- Conditions: plain/prior Silver at 2k/10k, four paired futures, K=8,
  weight 400, root bonus on; independent original-future plain10k reference.
- Limits: 180 CPU / 240 wall seconds per source, two concurrent jobs,
  five total attempts including the excluded canary; no retry or extension.

| Source | Role | Return code | CPU seconds | Wall seconds | Status |
| --- | --- | ---: | ---: | ---: | --- |
| 97150701 | Excluded canary | 0 | 95.90 | 95.93 | CANARY_VALID; five matched states |
| 97150710 | Cohort | 0 | 69.68 | 69.69 | Complete; three matched states |
| 97150711 | Cohort | 0 | 57.25 | 57.27 | Complete; four matched states |
| 97150712 | Cohort | 0 | 89.70 | 89.73 | Complete; five matched states |
| 97150713 | Cohort | 137 | 180.10 | 180.18 | CPU-limit kill; incomplete output |

Total measured process CPU including canary: **492.63 seconds**. GNU time
records signal 9 for the failed source; `timedOut: false` means the runner's
wall timeout did not fire. The CPU hard limit did. The failed job produced no
runtime manifest and left buffered/truncated CSV files; these remain intact.
The slight accounting overshoot at termination is reported as measured.

The analyzer emitted exactly `INVALID_OR_INSUFFICIENT` with reason
`Invalid: source process failed or timed out`. Its failure report contains no
comparison metrics. Completed-job coverage is operational accounting only.

## Verification and interpretation

Merged Release builds passed, and all seven focused CTests passed.
Independent v2 compatibility review passed. The frozen binary's actual E
logits matched an independent NumPy reference across eight synthetic roots
and 40 actions, maximum absolute difference **1.16007e-6**. Those fixtures
executed no game seeds. The canary validated model custody, RAW replay
controls and the corrected battle-future initialization; it is excluded from
the comparison.

This demonstrates usable gen6 E inference and a functioning mechanism on the
canary. It also demonstrates that the chosen resource cap was insufficient
for one selected source. It does not establish that E improves A20 fights,
that Silver is a better teacher than CTM, or which simulation budget to use.
Any subsequent attempt needs a separate prospective resource/attempt design;
do not resume the truncated job, add replacement seeds or relax this freeze.

## Evidence

`raw-outputs.tar.gz` preserves every top-level run file except the executable:
freeze, teacher/policy, build and runtime logs, phase/source latches, process
receipts, manifests, complete and partial CSV files, and reports. The original
binary and models remain under `build/a20-teacher-comparison/gen6E-run-1/`;
their identities are recorded in the freeze. They are not duplicated here.
The native E export is tracked in PR #541's evidence directory.

`synthetic-parity.tar.gz` contains the independent helper and frozen-binary
fixtures/reference/native results. `SHA256SUMS` covers this evidence packet.
The runner commands are in the parent README and per-source receipts.

Knowledge impact: §472 and the maintained research page record the failed
bounded attempt. Production defaults and the frozen protocol are unchanged.
