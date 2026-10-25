# Public-root infinity annotation pilot (K=4)

## Outcome

**Adapter contract PASS; natural-root annotation BLOCKED by missing no-Shard
provenance.** Four constructed public controls produce the expected sidecars
across 16 sampled worlds. All four preselected archived public roots are
unsupported and retain null fractions. They are not negative infinity labels.
No prevalence, population recall, calibrated fraction or natural-label quality
claim follows from this pilot.

Baseline: independently reviewed phase-2 commit
`59d7c463f733c9fb23ccef194d9d3d5c1dd9a3ff` (draft PR #843, unmerged when work
started). This continuation uses a separate fresh app-managed worktree,
`infinity-public-root-pilot/sts_lightspeed`, branch
`research/infinity-public-root-pilot`. The reviewed phase-2 worktree was not
modified. No worktree was created inside another. This is a dependent research
change; phase-2 oracle logic remains unchanged.

## Sampling and information boundary

Silver has no separate eager concrete-world API. It represents draw knowledge
with `CardPile` and samples unknown cards lazily using `drawTop(shuffleRng)`.
The research adapter calls that exact operation on a copied information-set
pile until drained, reverses the draw sequence to the simulator's bottom-first
concrete representation, and retains the post-drain shuffle RNG. Known top and
bottom facts, physical cards, their costs and upgrades stay intact. No card is
played and no draw-trigger effect is applied during materialization.

Public roots hydrate through the existing wire importer. Concrete-order and
hidden-intent inputs reject in this initial pilot. A source-supplied
`isolatedSearchSeed` is discarded before hydration; observation-generation
metadata is excluded from sampling identity. Hash the canonical public wire with
SHA256, then derive each world seed from the first 16 hex digits of
`SHA256("combat-infinity-public-world-v1:" + public_hash + ":" + k)` for k=0..3.
`seedSearchRng` initializes all six simulator streams. No real run seed or RNG
stream is used. Extra private-order metadata is ignored and never read.

This uses Silver's existing public-conditioned draw distribution. It does not
claim the same pathwise RNG coupling after arbitrary interleaving of lazy draws,
shuffles and other effects; eager materialization consumes future unknown-draw
choices up front. The sampled worlds are hypothetical full states, not recovered
historical trajectories. Only the current draw pile is materialized; ordinary
simulator mechanics handle later shuffles and other stochastic actions.

The oracle still requires proven absence of Prismatic Shard because combat's
two relic bitsets omit it. The research input retains #839's explicit boolean
`oracle_no_prismatic_shard` assertion from retained run provenance. Missing or
false returns UNSUPPORTED with null labels; nonboolean rejects. The adapter
never invents the assertion from card colors or the two combat relic bitsets.

## Sidecar contract

The standalone research CLI adds:

```sh
combat_infinity_oracle --public-fixtures
combat_infinity_oracle --public-roots ROOTS.jsonl
```

The latter reads only the first four rows, K fixed at 4. Each row supplies a
`public_wire` envelope or the archived `state` envelope and optional proven
no-Shard assertion. It writes `combat_infinity_public_sidecar_v1`:

- `certified_fraction`: worlds with actual simulator-certified same-turn kill / 4.
- `candidate_fraction`: worlds containing any damaging candidate / 4, including
  both certified and replay-rejected candidates. It excludes stall-only cycles.
- `minimum_reach_depth`: minimum over damaging candidates, null if none.
- `worlds`: k, sampled seed, hypothetical draw order, and complete unchanged
  oracle output (witness/reach, deltas, bounds, replay reason/actions and CPU).

All K worlds must be supported to emit numeric fractions. Unsupported worlds
are not removed from the denominator or counted as negatives. The root has
explicit status/reason and supported-world count; numeric fields remain null
when provenance/domain/quiet-boundary support is missing. `K=4` is a diagnostic
sample, not a calibrated probability or an assertion that worlds are unique.
Sampling is with replacement; a one-card draw pile has the same order in every
world, while future RNG seeds still differ.

Every oracle cap remains depth 24, nodes 2,000, candidates 16, replay periods
128, actions per candidate 1,024, total replay actions 4,096, **per sampled world**.
No production caller, model/training/loss/target/reward/default, Silver or OOC
algorithm changes exist. The standalone oracle now links existing OpenSSL
Crypto for SHA256, as the existing public-pair research probe already does.

## Frozen roots and controls

[PREREG.md](PREREG.md) and [root-inventory.json](root-inventory.json) were written
before pilot execution. Natural inputs are the first four rows from
`silver_quiescent_queue_item_20260922/native8-first-captures.jsonl.gz`, in fixed
file order: `2026100100/0` through `2026100103/0`. They are preserved project-fair
public search roots at floor 1; selection was not conditioned on oracle results.
Only their public wire envelope and source case ID are copied into
[public-roots.jsonl](public-roots.jsonl). Source gzip, exact selected raw lines
and extracted input have retained hashes. No new run-seed cohort was collected.

These combat wires lack full public run-relic provenance. Inspection of the
retained forced-action/prior-root corpora and Champ D13 public-root record also
found no such provenance; the prior-root archive additionally uses unsupported
hidden-intent wires. Do not infer Shard absence from the early floor or red
cards. No archived root was silently replaced or resampled to obtain coverage.
The four natural outputs all report `missing_proven_no_prismatic_shard` and
perform **zero oracle-world searches**. The result identifies a metadata gap,
not an absence of infinities.

Controls start from phase-2 constructions, then explicitly forget draw order
while retaining the public multiset. Known construction provenance proves no
Shard. Static-exhaust Dropkick and Sundial/zero-cost Dropkick certify 4/4;
no-Vulnerable Dropkick certifies 0/4 and has no damaging candidate; inherited
Awakened One phase guard certifies 0/4 but has a damaging candidate in 4/4.
All damaging control candidates have reach depth 4. See [MATRIX.md](MATRIX.md).

A separate nontrivial sampler fixture has three distinct unknown cards (Anger
#2, Defend #3, Bash #4), known top Dropkick #1 and known bottom Strike #5.
For all four world seeds, exact full-draw sequence and post-drain RNG match
Silver's lazy kernel. Reversing the source unknown vector, poisoning the source
RNG identity and adding a private-order side channel yields identical sampled
worlds. Known boundaries and the physical multiset are preserved. This is
kernel parity and invariance evidence, not an empirical uniformity study.

## Verification and evidence

Focused Release target build passes (GCC 13.3.0, `-j2`, ccache preset; ordinary
serial-LTO note only). Every game-driving command runs through the seed guard.
Each direct pilot command has a fixed 30-second wall bound:

```sh
cmake --preset linux-gcc-release-ccache
cmake --build --preset linux-gcc-release-ccache-build -j2 --target combat-infinity-oracle
timeout 30s bash tools/seed_guard.sh build/linux-gcc-release-ccache/combat_infinity_oracle --public-fixtures
timeout 30s bash tools/seed_guard.sh build/linux-gcc-release-ccache/combat_infinity_oracle --public-roots docs/experiments/evidence/combat_infinity_public_20261023/public-roots.jsonl
ctest --test-dir build/linux-gcc-release-ccache -R '^combat_infinity_(oracle|recall|public)$' --output-on-failure
python3 docs/experiments/evidence/combat_infinity_public_20261023/analyze.py
python3 docs/experiments/evidence/combat_infinity_public_20261023/analyze.py --check
git diff --check
```

Three focused CTests pass, including all phase-1/phase-2 regressions and the new
public contract tests. Public tests cover positive/negative/candidate-only
aggregation, exact K denominator, null minimum without a candidate,
missing/false/malformed no-Shard provenance, foreign-character unsupported
worlds, concrete-order and hidden-intent rejection, root immutability and the
sampler parity/invariance checks. A second focused run followed the addition of
the malformed/hidden/foreign truth-table checks; unchanged initial results were
reproduced. This was not an outcome-driven root or seed extension.

Raw outputs: [public-controls.jsonl](public-controls.jsonl),
[public-sidecars.jsonl](public-sidecars.jsonl), [focused-ctest.txt](focused-ctest.txt).
The reproducible [analyzer](analyze.py) checks expected fractions, all per-world
budgets, seed/index counts, natural null labels and source-input hash, then
writes [RESULT.json](RESULT.json), [MATRIX.md](MATRIX.md), and
[expanded-sidecars.json](expanded-sidecars.json). The expanded reporting adds
supported/certified/candidate sample counts, cap-hit counts, and an exact
representative witness selected from the raw candidate records. Unsupported
roots retain null fractions; their cap metrics are marked not searched. No
runtime sidecar schema or adapter code is changed by this reporting step. Source/CMake/binary
hashes are in [sha256.txt](sha256.txt). Per-world CPU/node diagnostics are raw in
the control sidecars; there is no natural-root timing or throughput claim because
no natural world was eligible for search.

Not run: full local suite, gameplay/full-run experiment, fresh natural collection,
model inference/training, AZ annotation integration or a larger K/root sample.
GitHub Actions Linux GCC remains the authoritative pre-merge check. Draft and
independent review status belongs to the PR evidence packet.

Reporting completion uses only the retained raw records. `--check` validates
the generated bytes without rewriting them. Eligible natural roots remain 0;
annotated natural worlds remain 0. The scientific verdict and all recorded
measurements are unchanged; no experiment or sampling was rerun.

Knowledge impact: maintained research status and the oracle's research interface
contract updated; new chronological evidence recorded in the ledger.

## Conclusion and next boundary

The adapter can produce the requested sidecar fields from a public information
set using Silver's existing draw-sampling semantics, and its control checks pass.
The preserved-root pilot cannot yet produce eligible natural labels because
no-Shard provenance is absent. Do not train from these nulls, call this natural
recall qualification, or expand the sample to hide that gap. The next required
input is public root data accompanied by complete run-relic provenance (or an
existing retained authoritative record proving the assertion). No capture
schema, new producer run, model integration, automatic scale-up or merge was
performed to compensate.

## Subsequent provenance-route inspection (no new pilot)

The [read-only source/artifact audit](PROVENANCE_OPTIONS.md) found a companion
full-run trace for a different retained historical Champ capture, with matching
receipt/file/manifest/binary hashes. It offers a first-16 development proposal
without a producer change; oracle eligibility and annotation remain unexecuted.
The earlier inventory statement concerns individual root records. The later
paired-file join does not supply provenance to the four frozen native8 roots.
Their null fractions and this report's BLOCKED natural-annotation verdict remain
unchanged. No world sampling or experiment was rerun.
