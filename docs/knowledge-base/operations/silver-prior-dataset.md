# Silver policy-prior dataset

This page documents the offline, policy-only dataset contract and its separate
trainer. Training does not change Silver search or qualify a gameplay
improvement. The original
[forced-action audit](../../experiments/evidence/silver_forced_action_target_2026-09-19/README.md)
has a promising fresh-population result and an unresolved historical regression.
That regression remains unresolved.

## Boundaries and versions

`tools/silver_prior_dataset.py` freezes plans, selects public roots, validates
labels, and exposes the training loader. `tools/silver_prior_projection.py`
contains the explicit model field whitelist. `silver_prior_label` is a separate
manifest-driven executable using `runSilverForcedActionReferences()`; it never
changes the historical 32-root A/L/J audit contract or runs Teacher A.

The record schemas are `silver_prior_plan_v1`, `silver_prior_cards_v1`,
`silver_prior_selection_v1`, `silver_prior_label_job_v1`,
`silver_prior_raw_root_v1`, `silver_prior_observation_v1`,
`silver_prior_shard_v1`, and `silver_prior_release_v1`. The replay envelope is
the existing `silver_root_mechanism_v1` / `silver_leaf_wire_v1`, wire version 2.
Schema changes require new versions and recollection/reprojection decisions;
silently reinterpreting existing successful artifacts is forbidden.

Each compressed root shard contains the full validated public replay snapshot,
exact native semantic actions and fingerprints, job/provenance, every raw
replicate, original-root evaluator scalars, model projection, and native-order
mean corrected action values. It contains no softmax target or chosen
temperature. The training-facing interface is **K candidate records and K raw
mean values**, with no fixed action vocabulary or value output. Labels and
provenance are separated from the observation returned to a future model.

## Field map

All counts, HP, costs, and amounts remain typed raw numbers. Identity enums,
status kinds, bit positions, relic counter kinds, zones, and entity references
are categorical fields, never normalized magnitudes. Booleans remain booleans.

| Wire component | Model projection | Replay/provenance only |
| --- | --- | --- |
| Player | Raw HP/max HP, energy, block, gold, resources, stance, scalar powers, public per-turn/combat counters; explicit status presence/amounts/just-applied timing; relic presence/counters; bomb timing | No additional player fields discarded |
| Global | Act, ascension, floor, encounter, turn, draw/energy counters, card-count counters, potion capacity, monster counts, public boundary/visibility flags; decoded misc and per-monster roll/skip flags | `loopCount` execution safety bookkeeping, isolated search seed, observed generation, next UID |
| Cards | One occurrence per card, compact ID, upgrade/special data, base/current cost, retain/free flags, zone/knowledge segment, local reference, observed position | Original UID used only to resolve a semantic action to its unique hand occurrence |
| Piles | Separate known-bottom, unordered-unknown, known-top lists and full-order flag; multiplicity preserved; unknown records sorted by observable card fields and have null position | No unknown storage position; original canonical replay representation retained |
| Limbo/stasis | Slot references and explicit null absence; occupied instances use the same card schema | Sentinel card 0 is absence only in these fixed storage slots, never an unknown card token |
| Monsters | Slot/reference, explicit presence, life-state/escape flags, raw HP/max HP/block, power presence/amounts, identity-specific counters, visible move history | Pending move-roll/direct-choice distributions and pending roll-input snapshots |
| Potions | All five storage slots, capacity availability, actual identity and explicit empty flag (`EMPTY_POTION_SLOT=1`) | None |
| Selection/queue | Initial roots are `PLAYER_NORMAL`; card-select task/skip semantics remain explicit on candidates | Full selection and current/last queue-item context, including card relationships, remain replay-only in v1 |
| Evaluation | Native `silverRootReferenceScalars()` pre-action effective gold and max HP | Search/evaluator config, RNG identities/counters, teacher data, SHA/hash/source/root IDs, native action order, collection timing |

An absent monster has only its slot reference and `present=false`; a present
dead/half-dead monster retains its state. Runic Dome masks model move history
even if a malformed producer supplies hidden values. Frozen Eye observed
order is preserved. Unknown piles are multisets; their deterministic storage
order does not assert draw order. The native materializer remains authoritative
for wire validation and legal-action enumeration.
For a potion-discard candidate, the native target field can contain the packed
discard sentinel (8191 for an encoded -1). Projection keeps the explicit
`discardPotion` flag and sets `target_ref` to null; it never treats that value
as a monster slot. A non-discard action with the same invalid target fails.

The card vocabulary is source-census-derived. Only `PROVABLY_UNREACHABLE`
entries are excluded. `REACHABLE` and `UNKNOWN` retain distinct names and
categories, both forward and inverse mappings, and a content hash. Null is
absence/padding; compact ID 0 is a real retained card. Encountering an excluded
or unmapped occupied card fails the whole root's projection. Regression
fixtures cover BRUTALITY/COMBUST, colorless cards, curses, statuses, and
event/generated cards.

## Selection, teachers, and integrity

The checked-in plan has 512 fresh repository-inventoried A0 Ironclad sources,
split 384 TRAIN / 64 VALIDATION / 64 LOCKED_TEST. Source policy is project-fair
Silver, native floor/win OOC, exact 10k source decisions, adaptive/early-stop
disabled, allocated reuse cap 32768, through Act 3, keys off. All `STS_*`
environment variables are cleared before applying the frozen source flags.
Execution uses one worker and `OMP_NUM_THREADS=1`; models, both executable
hashes, source SHA, Silver upstream SHA, runtime sidecars, logs, and actual
capture configuration are retained. The existing benchmark-canary validator
checks each completed source's effective backend, SHA, seed, budget, thread
count, fair regime, reuse mode, and failure telemetry. Legitimate losses remain.

Within each source and act, select one SHA-256 identity-ranked early root
(turn <=2) and one later root per combat when available, otherwise up to two
identity-ranked roots from that combat. Interleave identity-ranked early and
later candidates, taking at most eight per act. This yields at most two per
combat and 24 per source; missing later acts never cause backfilling. Pilot
selection takes the first two of those selected roots per act, on the fixed
16 TRAIN sources, making it an exact subset of the later full selection.

After capture and before labeling, the selection manifest freezes every root
and selects the minimum identity-hash root per validation/test source for J.
Sources with no eligible observations remain completed sources with zero roots;
absence is reported, never filled with a replacement seed or another act.

L uses eight x 5000 continuation simulations per native legal action. Only
preselected evaluation roots receive J, eight x 10000. Teacher identity is
`FNV64(teacher_identity/root_id/L-or-J)` followed by the existing native
replicate mixer. Identities do not depend on worker, action rank, or resume.
Sibling actions share each replicate identity; L and J roles differ. A shared
seed is not a claim of identical random events across actions.

Immediately terminal actions have zero continuation simulations. Nonterminal
replicates require the entire budget. Every raw row retains the leaf-root
mean, full and applied original-root victory correction, victory count,
terminal/stochastic flags, and RNG identity/counters. The validator recomputes
replicate identity, correction, action mean, and complete action/replicate
accounting. Missing actions or replicates invalidate the whole root.

Cross-split duplicate audit conservatively compares the full model observation
plus the candidate multiset after removing native candidate order. It reports
all aliases and lists all affected roots for quarantine. Unresolved overlap
produces an immutable attempt report under `reports/`, without creating
`release.json` or `report.json`. No labels are used to
select roots or detect overlap. J stays in `raw/J`; it is excluded from model
observations and training loaders. Finalization reports only integrity/counts
for locked-test artifacts, never values or rankings.

After inspecting that report, explicitly rerun finalization with
`--quarantine-overlap`. This excludes **every** root in every detected
cross-split duplicate group; it does not permit arbitrary root exclusion or
replacement. The resolver requires the exact previously saved attempt report,
complete labels, no remaining overlap, complete retained membership, and a
nonempty retained TRAIN/VALIDATION/LOCKED_TEST split (TRAIN only for the pilot).
It saves a content-addressed resolution under `resolutions/`, bound to the
execution and selection hashes, before publishing a release. Original source
captures, labels, shards, and attempt/failure evidence remain unchanged. The
report keeps original counts and separately reports `retained_membership`.
Quarantined judged roots are excluded without selecting replacement J roots.

```bash
python3 tools/silver_prior_collect.py finalize /durable/silver-prior-v1
# Inspect the saved overlap attempt, then explicitly resolve that same population:
python3 tools/silver_prior_collect.py finalize /durable/silver-prior-v1 --quarantine-overlap
```

## Execution and resumption

Use one reviewed source checkout. A review record must contain
`reviewed_sha`, `implementation_review: "PASS"`, `reviewer`, and an
`evidence_reference`. Bind only a clean checkout at that SHA after configuring
and building `one_combat` and `silver-prior-label`. The labeler embeds the
configure-time Git SHA and rejects a mismatched job/runtime SHA. The driver
verifies both binary hashes and both native OOC model hashes on every phase.

```bash
python3 tools/silver_prior_collect.py bind /durable/silver-prior-v1 \
  --plan docs/experiments/evidence/silver_prior_dataset_v1/plan.json \
  --vocabulary docs/experiments/evidence/silver_prior_dataset_v1/vocabulary.json \
  --review /durable/review.json \
  --source-binary build/linux-gcc-release-ccache/one_combat \
  --label-binary build/linux-gcc-release-ccache/silver_prior_label
```

Run `capture`, `select`, `label`, then `finalize`, each with the same corpus
directory. First run every phase with `--pilot`. The pilot report measures
source capture seconds, legal-action/replicate counts, L throughput, and
compressed bytes. Its forecast explicitly separates serial extrapolation from
parallel wall time; it does not invent J throughput from a TRAIN-only pilot.
Inspect that report against the configured resource budget before full capture.

Finalization independently verifies the selection's schema, plan hash, source
SHA, and exact pilot/full phase. It reads and validates the completion record
for every required source, counts those verified records, and reconstructs the
deterministic selection from their captures. The supplied selection must match
that reconstruction exactly. Missing sources yield an incomplete attempt
report, never a release; a completed source with zero eligible roots is counted
and listed separately. Thus a pilot-sized or partial selection cannot stand in
for the full corpus even when its individual labels are valid. Release checksums
also cover all verified source completion records.

Full gameplay/label phases must run via the designated launcher. Its `run`
command supplies `tools/seed_guard.sh --gcp-research` and the required context;
there is no extra `--gcp-research` CLI switch on `gcp_benchmark.py` itself.
For example, from the local checkout after deployment to the reviewed remote
worktree, replace `REVIEWED_CHECKOUT` and `DURABLE_CORPUS` with actual paths:

```bash
python3 tools/agent/gcp_benchmark.py run --foreground -- \
  python3 REVIEWED_CHECKOUT/tools/silver_prior_collect.py capture DURABLE_CORPUS
```

For the explicitly authorized **512-source local collection** of this frozen
plan, bind with `--local-512 --workers 4`, then pass `--local-512` to each
`capture` and `label` phase. `--workers` may be 1–4 and cannot exceed the value
frozen at bind. Every native one-source or one-root command still runs through
`tools/seed_guard.sh`; this scoped authorization changes the aggregate local
source allowance only for the exact checked-in plan hash. A corpus execution
lock prevents concurrent capture/label phases from exceeding the frozen worker
bound or racing a resumed job. The exception does not change the native per-command guard, source configuration,
teacher budgets, seed identities, or split boundaries. The local execution
mode and worker bound are recorded in the binding. `select` and `finalize`
remain read-only validation phases and do not need the locality option.

```bash
python3 tools/silver_prior_collect.py bind /durable/silver-prior-v1 \
  --local-512 --workers 4 --plan docs/experiments/evidence/silver_prior_dataset_v1/plan.json \
  --vocabulary docs/experiments/evidence/silver_prior_dataset_v1/vocabulary.json \
  --review /durable/review.json \
  --source-binary build/linux-gcc-release-ccache/one_combat \
  --label-binary build/linux-gcc-release-ccache/silver_prior_label
python3 tools/silver_prior_collect.py capture /durable/silver-prior-v1 --pilot --local-512 --workers 4
python3 tools/silver_prior_collect.py select /durable/silver-prior-v1 --pilot
python3 tools/silver_prior_collect.py label /durable/silver-prior-v1 --pilot --local-512 --workers 4
python3 tools/silver_prior_collect.py finalize /durable/silver-prior-v1 --pilot
```

The launcher starts in `/home/philippherrmann/sts_sweep`; the driver invokes
the native programs with the reviewed checkout as their working directory.
Without this task-specific local authorization, full collection remains on the
designated remote path. Follow the exact-SHA remote deployment procedure in
[build and debugging](build-and-debugging.md).

Storage must be outside `/tmp` and disposable source worktrees. Capture/source
completion and label-root records are atomic, compressed, and create-only.
Identical retries are accepted; changed evidence is rejected. Root timing is
committed inside the same raw record, so a crash cannot leave timing blocking
a valid retry. Durable attempt directories preserve partial/malformed output
even across interruption. Existing failed roots/sources require explicit
inspection before retry; failures are never automatically erased or resampled.

The release contains SHA-256 file checksums. `load_training_corpus(directory)`
requires a finalized, valid release, checks shard hashes and frozen jobs, and
yields only TRAIN L observations and aligned raw values. Quarantined membership
must match the sealed resolution and its execution/selection binding. Lower-level
`load_training(path, vocab, expected_job)` is for an already integrity-gated
single root. Fixture shards are rejected by both training paths. Candidate
permutation must use `permute_candidates()` so values remain aligned.

## Structured policy model v1

`tools/train_silver_prior.py` trains the offline `SilverPriorNetV1` student.
Its release-gated preparation path admits TRAIN L and VALIDATION L only; the
separate `evaluate-validation-j` command can open only the 64 preselected
VALIDATION J shards. There is no LOCKED_TEST evaluation command in this tool.
The preparation cache is bound to the release, vocabulary, trainer source hash,
and cache schema, and contains compact ragged tensors rather than decompressed
shards. Put that cache and all checkpoints outside Git and outside `/tmp` for
durable runs.

```bash
CORPUS=/home/philippherrmann/Documents/sts/silver-prior-v1-corpus-v2
RUN=/home/philippherrmann/Documents/sts/silver-prior-model-v1
python3 tools/train_silver_prior.py prepare "$CORPUS" "$RUN/cache/train-validation.pkl"
python3 tools/train_silver_prior.py train-stage-a "$CORPUS" \
  "$RUN/cache/train-validation.pkl" "$RUN/stage-a"
python3 tools/train_silver_prior.py evaluate-validation-j "$CORPUS" \
  "$RUN/cache/train-validation.pkl" "$RUN/stage-a"
```

The trainer uses source-grouped TRAIN/VALIDATION membership frozen by the
corpus, TRAIN-only normalization and top-two-gap temperature scale, and three
predeclared target temperatures. Every root contributes equally to grouped
cross-entropy regardless of candidate count. Candidate softmax is grouped by
root. Stage-A validation includes root-level metrics with 5,000 source-cluster
bootstrap replicates. The independent J command is run only after all three
Stage-A fits and VALIDATION-L metrics are complete. A positive result is an
offline policy-prior finding only; no Silver integration or gameplay claim
follows from it.

## Verification boundary

The focused CTests are `silver_prior_dataset_fixture` (native replay,
representation, visibility, correction, terminal handling, and capture
neutrality) and `silver_prior_resume` (crash/retry, failure evidence, source
completion, selection binding, and overlap resolution). Both carry `smoke`
labels and are included by the authoritative CI selection `-L 'core|smoke'`. The
unchanged `silver_forced_action_fixture` protects the historical audit.
Run `python3 -m unittest tools.test_ironclad_reachable_domain_census` for the
source census. Those integrity checks do not assess policy quality; that belongs
to the separate structured-model experiment described above.
