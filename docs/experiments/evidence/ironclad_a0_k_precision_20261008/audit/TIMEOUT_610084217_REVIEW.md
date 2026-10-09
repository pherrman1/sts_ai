# Source 610084217 timeout diagnosis

The fixed primary remains **EXECUTION_BLOCKED**. Source 610084217 exceeded its
frozen 1,800-second per-source cap. The saved evidence supports a CPU-heavy
continuation-cost tail, with no recorded engine fault or prolonged stall. It
cannot certify the interrupted branch or unavailable buffered records.

The [machine audit](TIMEOUT_610084217_REVIEW.json) binds every saved partial
output to the timeout receipt's exact byte count and SHA256, along with freeze
`fc86c6e538618bf9212ffca58d422bda472954aa00f67a9216c3129c1a0df859`.
The [read-only audit program](audit_timeout_610084217.py) uses metadata,
validity, CPU and profile health fields only. No win labels, action rankings or
evaluation comparisons were interpreted. The game configuration and source
allocation were unchanged. No raw data were modified.

The receipt records start **12:01:42.724** and finish **12:31:42.758** Europe/Berlin,
wall time **1,800.033516 seconds**, status `timeout`, exit code 124. The later
12:32:17 coordinator observation is not the process's recorded finish time.
The source had reached counterfactual continuations for retained BOSS_RELIC
state decision 35, Act 1 floor 17. There are **100 complete persisted branch
records**, all with `valid=1` and empty errors: option indices 0–2 each have
k0–31, and option index 3 has k0–3. Their CPU times sum to **1,747.39344 seconds**,
which is **97.08%** of invocation wall time. Mean recorded branch CPU is
**17.4739344 seconds**. These records alone establish substantial continuing
compute rather than a timeout spent largely waiting.

The final label record is truncated to 11 of 29 columns. Other files were also
buffered: `sources.csv` and stdout/stderr log are empty, the completed manifest
is absent, and option/MAP tails lack terminating newlines. A matching column
count does not certify completeness of a final unterminated field. The frozen
producer writes source and branch CSVs through buffered streams and explicitly
flushes them only after finishing all branches for a source
(`3ed91ab3:apps/one_combat/combat_datasets.cpp`, lines 2635–2716). Thus these
partial files are consistent with timeout before the source-end flush; they
are not independently evidence of simulator corruption. Source CPU and the
source's trajectory-valid flag are unavailable and must not be reconstructed.

All **38,235** saved tree profiles parse, have unique real-decision identities,
use allowed original/redrawn-future seeds, and satisfy the frozen budget and
endpoint-conservation checks. They contain **179,029,250 completed simulations**,
**1,524 singleton skips**, **42 cycle fallbacks**, **14 engine-stop search
endpoints**, and zero turn-limit endpoints. No recorded root error, descent
abort, unresolved nonterminal endpoint or malformed profile was found. The
cycle and engine-stop counts retain their existing diagnostic interpretation;
they do not establish a fatal fault in the actual continuation.

The original source accounts for 666 roots. After it, profile future-seed groups
follow three complete ordered k0–31 cycles and then k0–5. Under the frozen
option-outer/future-inner producer loops, this supports progress into option
index 3, k5; the profile has no explicit branch-ID field, so this attribution
is a source-order inference. The final recorded root is Act 3 floor 46,
Spire Growth, combat ID 1608, decision 4, with 250 completed simulations. The
profile file's final modification was **0.090 seconds** before receipt finish.
The producer flushes each profile row immediately
(`3ed91ab3:src/sim/search/NativeSilverBackend.cpp`, lines 203–205). This is
consistent with recent forward progress, not an observed long stall at the end.
It is filesystem timing evidence rather than a full per-root timestamp series.

At least four options were reached, implying at least 128 allocated branches;
the protocol ceiling is 192. The exact retained count is unavailable because
there is no completed source row or manifest. Additional completed branches
may remain buffered. The **52.640076-second** difference between wall time and
persisted branch CPU includes source work, unflushed/current continuation work
and CPU-versus-wall differences; it is not a measured stall or precise total
process CPU. The in-progress root and eventual validity of the interrupted
branch remain unknown.

No retry, replacement source, cap extension, partial efficacy calculation or
change to the frozen experiment follows from this diagnosis. The remaining
fixed dispatcher may finish under its existing authorization; this failed
source continues to block the clean 32-source primary regardless of those
other completions.
