# Active Lizard Tail CTM qualification

**Decision: `INCONCLUSIVE_KEEP_ACTIVE_UNQUALIFIED_LIZARD` after Phase 2 and
`LIZARD_HEAD_REJECTED_PROPER_SCORE` after the bounded Phase 3A fit.** The
production `active_unqualified_lizard` guard remains unchanged. No runtime
integration, parity qualification, promotion, or live seed check was done.

## Frozen setup and data

- Baseline `main`: `aa09f75e6be837f7f39a2e31dde234bfd2c2ef08`; PR #280 reference
  head: `616e9a196b5e96f1dab7f72370e34337134b87c9`.
- Shadow collector implementation: `0fc475fbf4ce96adfe3ce46363fba4d7a427ab3c`;
  collector executable SHA-256:
  `fdc1d5c6e396a9ab1e59eba42ef5088535c2d06f672c7445995cd75a22435015`.
- Fit implementation was independently reviewed and frozen at
  `67479a8381a286319244f6d673c11a716c50da52` before training.
- Corpus: 111 unique source seeds `4200100..4200210`, 2,234 rows, zero
  quarantines, outcomes 2,223 wins / 11 deaths. SHA-256:
  `4d9927ad0f23d7f9e6e1fdb1091c6cf98ff7f5935540a5103746257b550b5504`.
- Manifest SHA-256:
  `457e33d53c7af2f474957d2201da0f7a7c95a1f6be10de71f40782cb14f832f6`.
- Teacher: `silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77`;
  optional Silver prior was unset. The collector manifest binds the producer,
  executable, teacher artifacts/configuration, source fragments, row/log
  hashes, commands, and environment. The reviewer verified the assembled rows
  reproduce the declared fragment membership exactly and that all rows use
  the frozen teacher.

The first 16-seed smoke plus the 111-source decision cohort use 127 unique
local source IDs, under the 128-source cap. Seed `4200161` completed in two
fragments; the duplicate fragment rows were JSON-equivalent and included once.
Three interrupted fragment commands had no final sidecar manifests. Their
identities were recovered from recorded executor arguments and corroborated
against the frozen executable, finalized adjacent fragment, and row teacher
IDs. Per-fragment row and log hashes and command/environment provenance are in
the manifest. No more local seed collection was run.

## Phase 2: existing component exposure

The source-group split is TRAIN 87 sources / 1,767 rows, VALIDATION 15 / 308,
TEST 9 / 159. On fully supported active-Lizard TEST transitions, 127 rows / 9
sources are supported, including 126 wins and one death. Existing-component
exposure gates pass: HP mean composition gap `-0.00180` nat (95% source-bootstrap
CI `[-0.00812, 0.00247]`, 126 rows / 9 sources), potion `+0.00045` nat
(`[-0.00191, 0.00337]`, 126 / 9), and non-Lizard relic `-0.01304` nat
(`[-0.05221, 0.03731]`, only 32 informative rows / 4 sources). The sparse relic
exposure is a limitation despite passing its existing 0.1-nat mean-gap gate.
Supported copy-through had zero mismatches. The diagnostic TRAIN-prior
ancestral sample had zero hard validity failures.

The old, untrained Lizard head failed against the TRAIN-only class prior: its
paired TEST NLL gap was `+0.76590` nat (95% source-bootstrap CI
`[+0.61415, +0.87443]`, 126 winning rows / 9 sources). Only six supported TEST
wins consumed Lizard Tail. These results nominate only the narrow head path;
they do not qualify the head.

## Phase 3A: fixed head-only fit

The frozen recipe trained only `relic_net.heads.lizard.weight` and `.bias` for
10 epochs under each of the fixed seeds `20260912`, `20260913`, and `20260914`.
The shared decoder and all other heads remained frozen. TRAIN contained 1,371
supported winning rows from 87 sources, with 55 consumed / 1,316 retained
labels; VALIDATION contained 248 rows / 15 sources and was descriptive only.
The prior was fit from TRAIN only (consumption rate `0.04012`).

On the source-grouped TEST winners (126 rows / 9 sources, six consumed), the
trained head mean NLL was `0.69889`; the TRAIN-only prior mean NLL was
`0.19213`. The paired trained-minus-prior gap was `+0.50675` nat, with 1,000
source bootstrap repetitions and 95% CI `[+0.37380, +0.61081]`. This is a
strict proper-score rejection, not an inconclusive result. The 32-draw
ancestral diagnostic covered every fully supported TEST pre-state (127 rows /
9 sources, including the observed death): 3,795 sampled victories, 269 deaths,
1,976 retained and 1,819 consumed Lizard outcomes, and zero hard-validity
failures. Ancestral validity does not override the proper-score failure.

## Boundaries and files

No Phase 3B specialist was started. No production artifact or support metadata
changed. The live seed `13027029` check was skipped because offline qualification
failed; it must remain behind the qualification prerequisite. Do not infer
runtime/native parity or gameplay quality from this offline audit and fit.

This packet contains the exact assembled JSONL corpus, its manifest, the Phase
2 audit JSON, and the Phase 3A result JSON. The candidate `.pt` files remain in
the ignored local build directory and are not production artifacts. Their
SHA-256 values are recorded in the fit result.

**Knowledge impact:** this negative targeted qualification and its fail-closed
runtime boundary are recorded here and in the maintained current-research page.
