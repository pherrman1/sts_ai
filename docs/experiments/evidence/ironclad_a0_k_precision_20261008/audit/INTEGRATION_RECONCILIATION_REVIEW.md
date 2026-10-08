# Merge integration reconciliation review

**PASS_STATIC_INTEGRATION_RECONCILIATION** for merge
`61b9616ab2137d9c950f414fb8e162290d83ae5c`, joining task parent `f88cbbd2`
and main parent `70f7dfe5` over base `a4b3df35`.
The [machine receipt](INTEGRATION_RECONCILIATION_REVIEW.json) records exact
parent and merged blob identities and checks. This is read-only source review;
focused merged build/test verification is recorded separately.

All **410 task-only changed files** and **34 main-only changed files** match
their originating parent exactly. For the three overlapping code/build files—
`CMakeLists.txt`, `apps/one_combat.cpp` and `apps/one_combat/driver_shared.h`—
the added/removed-line changes in each direction exactly preserve the changes
from the other branch. No executable-source conflict was manually resolved.
The merged CMake inventory contains the exact union of both parents' tests and
executables: **183 named tests and 27 executable targets**, with no duplicate
names. Both new CTM feature-extraction CLI modes retain matching declarations;
the task's targeted GEN2 arguments, startup guards and research targets remain
intact. The Crypto-link helper is defined before the standalone probe uses it.

The incoming `ooc_mcts_adapter.cpp` changes preserve main's conditional
Smoke Bomb masking for escape-capable CTM samplers and its selftest. They do
not modify the public encounter sampler. Other incoming CTM runtime/tool
files match main exactly; this review does not independently re-qualify their
scientific results or every internal implementation path.

Manual resolution touched only `EXPERIMENTS.md`, `ledger-06.md` and
`ooc-label-pipeline.md`. The merge preserves the task's §395 and main's §396
verbatim, retains both index entries, and preserves both the targeted-REST
GEN2 documentation and incoming E3 analysis documentation. A separate E3
heading keeps that older corpus tool's invalid-sibling handling distinct from
the fixed K32 experiment's complete-allocation gate. No conflict markers remain.
Subsequent maintained-doc closeout edits are outside this merge snapshot and
receive separate final claim inspection.

All **21 frozen K-precision artifact entries** still match their hashes. Both
immutable executable hashes also match: K-precision used source `3ed91ab3`,
binary `27a78efd…027c7`; the closed confirmation used source `d35b42b1`, binary
`1dcc7916…0a8f5`. The merged source is a new runtime identity. Neither historical
result becomes a gameplay qualification of `61b9616a`, and historical test
receipts must not be relabeled as tests of this merge. This review ran no build,
test, game or numerical analysis and changed no source files.
