# Native Arm C preflight review and corrections

Baseline preparation commit: `c5154c1bdd503643bca56a2731b8a4effc78a694`.
Pinned scientific producer source remains `9d83adbbbcc0fabf2c8bcd8c6a87f9782d0acbc3`.
Draft stacked PR: https://github.com/pherrman1/sts_ai/pull/567 (base PR566).

Independent `heart_review` found preparation behavior correct but requested a
stale ledger status correction, rejection of non-integer seed arguments, and a
test assertion for the actual `STS_OOC_MCTS_CPU_SECONDS` variable. Those narrow
repairs preserve the scientific environment, assignments and dispatch boundary.
The original cloud packet, including REPORT.md and SHA256.json, is unchanged.

Independent audit verified exact regeneration of the prepared assignment,
all36 scientific environment keys against the original producer, all11 evidence
hashes and complete packet inventory,53 tracked-model hashes, the checkpoint
hash, and finite synthetic-score output. Preparation PASS does not qualify a
producer or authorize scientific dispatch. Nine focused checks are repeated
locally with exact command/test IDs and raw output in focused-checks.json/log.
No real game seeds, canaries, fits, or TEST openings occurred in this review.

The local coordinator checked the preserved old campaign receipts (copied
byte-for-byte here). Source110163000 returned124 after1200.064086s. Campaign
stop verdict is INCOMPLETE, with three interrupted sources005..007; receipts
exist for000..004, of which001..004 succeeded. No corpus manifest, fit-started
or TEST-opening latch is present. The original campaign-stop SHA256 is
1503b5fbc408adcc8e20e879ed28787887a9cb50e59e4f607ce5054836cb659c;
failed-source receipt SHA256 is
1e4aa71fff778d426843353c85618aa81964b1b33ae1273e2ddf847ff1721c24.
The original canary/result review hashes remain
8a8134b7843fec53d05fdc84805aa6e299c2285b8fbb6fe1a00996bdf22d2003 /
e899d6209b857dc23ab6fe534b4cd909062ce105a10310460260bc95517b251a.
Prior scientific verdicts remain unchanged; no retry/pooling of that attempt.

A subsequent capability check in the same cloud chat confirmed runtime identity
and current observed revision6. No documented arbitrary-file publication,
download-link creation or UI-attachment tool is exposed; `download_file` is
inbound only. A native download/export roundtrip therefore remains unavailable.
Session lifetime, idle timeout and retention guarantees remain unknown. These
are observed interface limitations, not a universal claim about Codex Cloud.
The four CPU-equivalent quota does not establish64-worker capacity. No new
service, credential or branch was created by that capability check.

Dispatch remains BLOCKED on reviewed execution/lease/deadline implementation,
frozen runtime/model/producer identity, original-hash-bound independent canary
qualification, verified durable corpus delivery and supported worker capacity.
There is no scientific result, CI pass, merge or default promotion claim here.

Knowledge impact: correct the old local attempt status and retain the native
cloud preparation/delivery limitation in current research and review evidence.
