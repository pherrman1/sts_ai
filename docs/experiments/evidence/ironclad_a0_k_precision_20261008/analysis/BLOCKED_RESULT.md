# K4/K16 collection: execution blocked

**Primary status: `EXECUTION_BLOCKED`.** All 32 fixed source invocations were
attempted: 31 completed with exit 0, and source **610084217** reached its frozen
1,800-second timeout (receipt exit 124; observed process wall 1,800.034 seconds).
The dispatcher finished with exit 123 after the remaining fixed jobs ended.
The bound process closeout reports no active game processes. No source was
replaced or retried, and the per-source cap was not changed.

The timeout fails the complete-allocation gate. The completed 31 sources are
not a replacement primary sample, and the failed source is not a valid
no-state source with zero gain. Selection and efficacy evaluation remain
blocked; no action ranking, paired effect, confidence interval or K16-versus-K4
verdict is reported. The earlier RemoveLow confirmation remains outside this
experiment.

| Preserved metadata | 31 completed invocations | Timed-out invocation |
|---|---:|---:|
| Finalized source-state rows | 31 | 0; source CSV is empty |
| Complete option metadata rows | 124 | 1; final record excluded |
| Complete branch-label records, efficacy uninterpreted | 3,968 | 100 |
| Complete MAP records | 3,968 | 97; final record excluded |
| Source CPU seconds present in cost fields | 412.584270 | Unavailable |
| Branch CPU seconds present in cost fields | 30,903.192223 | 1,747.393440; censored |

Only newline-terminated, full-width CSV records enter these counts. Source
610084217 has no final manifest; its source CSV and log are empty, and its
options, labels and MAP CSVs end in partial records. All bytes remain
preserved. The partial option table cannot establish its complete expected
branch set: 68 readable branch identities and 65 MAP identities lack matching
complete option metadata. The helper's mechanical 4,000-branch projection
from available option rows is therefore **not** a complete allocation count.
None of these partial records is accepted as a clean source contract.

The emitted cost fields sum to **33,063.169933 CPU seconds (9.184214 core
hours)**: 412.584270 source CPU seconds plus 32,650.585663 branch CPU seconds.
This is censored accounting of saved cost fields. It omits the timeout's
unavailable source cost and any work whose final cost record was not emitted;
missing cost is not imputed as zero. The 4,068 complete branch-label records
have no flagged invalid/error metadata, which does not cure the missing
source/manifest or establish full runtime health.

The **sum of invocation process-wall times is 33,290.747188 seconds (9.247430
hours)**. Separately, **dispatcher elapsed time is 6,024.881753 seconds
(1 hour 40 minutes 24.882 seconds)**; the first-start-to-last-finish receipt
span is 6,024.790304 seconds. Process-wall sums describe concurrent resource
occupancy and must not be presented as elapsed time or CPU time.

There are **255 preserved per-source files**: eight each for the 31 completed
invocations and seven for the timeout, whose manifest is absent. The dispatch
log is preserved separately. The machine receipt hashes every present source
artifact, the dispatch log, freeze, authorization, completion and process
closeout, reviewed accounting helper, producer/teacher/model files and frozen
tooling. Its field allowlists retain only identity, validity, count and cost
metadata; `finalWon` and other efficacy fields were not interpreted.

The saved corpus can support metadata/runtime diagnosis within its limits.
Any future efficacy use requires a separately authorized protocol disclosing
this failed fixed allocation and incomplete source. It cannot retroactively
rescue this primary experiment through deletion, replacement, cap relaxation
or analysis of only the completed sources.

## Reproduction and custody

The reviewed helper ran once after both closure receipts were available:

```sh
.venv/bin/python docs/experiments/evidence/ironclad_a0_k_precision_20261008/analysis/account_blocked_collection.py \
  --dispatcher-completion docs/experiments/evidence/ironclad_a0_k_precision_20261008/dispatch_completion.json \
  --dispatcher-completion-sha 656034d8bfdb8e43e7805bdfe9288b3e401f4efdfcbd11baf5f18637d27b22bd \
  --process-closeout docs/experiments/evidence/ironclad_a0_k_precision_20261008/process_closeout.json \
  --process-closeout-sha 8aa5e35ba1fe226237c99996fbe8805eb32badf54e9619436e5a68ab78e2780c \
  --output docs/experiments/evidence/ironclad_a0_k_precision_20261008/analysis/blocked_accounting.json
```

- [Machine accounting](blocked_accounting.json): SHA256
  `f1bd088ec0c1c7fb6cf09b4fffc9926494ecd9861fb0bb70d4eb27a8165c9c39`.
- [Reviewed helper](account_blocked_collection.py): SHA256
  `d041c018e1bc77a6a2243120836723eb8db5cbdce3a08b9669294e9c9eea1f7e`;
  ten independent synthetic tests passed before this invocation.
- [Implementation review](../design/BLOCKED_ACCOUNTING_IMPLEMENTATION_REVIEW.json):
  SHA256 `59913796ee45f0280f614068c55ecd866e26777fe13013ab0c2e59856a9c41d1`.

The output refuses overwrite. A later reproduction must choose a new output
filename; this document does not authorize rerunning games or either frozen
efficacy-analysis stage. Runtime-health and frozen contract verification are
separate coordinator/integrity receipts; this metadata report does not replace
them.
