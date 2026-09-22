# Silver prior dataset v1: validated pipeline, collection blocked

**No training-ready corpus or empirical bulk forecast has been produced.**
The designated GCP instance is unavailable. Read-only status returned exit 1:

```text
ERROR: (gcloud.compute.instances.describe) Could not fetch resource:
The resource 'projects/sts-ai-502709/zones/europe-west3-c/instances/sts-test' was not found
```

No replacement infrastructure was created. No source gameplay collection,
pilot teacher labeling, or full-corpus teacher labeling was launched. The
checked-in representative shard is explicitly a fixture and is rejected by
the training loader.

Later execution note: the user explicitly authorized running this frozen
512-source plan locally while GCP is unavailable. The collection driver now
requires an explicit `--local-512` execution mode, recorded in its binding;
this initial status and zero counts remain the pre-collection snapshot.

## Frozen plan and evidence

- Inspected handoff baseline: `289e1ab96d4a022d894756b9108bb081e34be8a3`.
- Implementation baseline/current main at preflight:
  `8613f9c7811ce19a81cb731e78b6b58d01ec91ca`.
- Review-correction base: current main `ac9db6c2`, merged into the task branch
  without conflicts. The original `dbeb3fcc` review freeze is superseded;
  the updated candidate SHA is recorded in PR #284 for review before the pilot.
- [plan.json](plan.json): exact 512 source seeds, 384 TRAIN / 64 VALIDATION /
  64 LOCKED_TEST, fixed 16-source TRAIN pilot, source config, teacher identity,
  selection rules, and hashed freshness inventory. Its seeds are
  `24000000..24000511`; all hard64 discovery sources are explicitly excluded.
- [vocabulary.json](vocabulary.json) and [census-cards.json](census-cards.json):
  census regenerated against execution source; 214 excluded, 131 reachable,
  27 unresolved, 158 retained slots. No additional integer padding slot.
- [representative-fixture.json.gz](representative-fixture.json.gz): complete
  replay, structured projection, candidates, and raw bounded fixture labels.
  The fixed replay fixture retains its historical source SHA; `fixture_only`
  explicitly permits that and prevents its use as scientific training data.
- [collection-status.json](collection-status.json): machine-readable blocker,
  intended/completed accounting, artifact inventory, and absence of forecast.
- [checksums.json](checksums.json): SHA-256 of committed durable data artifacts.

The source freshness inventory covers tracked repository experiment evidence,
including compressed manifests/roots and conservative numeric seed ranges.
Remote inventory could not be checked. Historical audit roots do not satisfy
the new source SHA/Act-3 corpus protocol; only the correction fixture was
reused. The new run must bind a clean independently reviewed SHA, binary/model
hashes, and matching regenerated vocabulary before capture.

## Verification

Focused commands, with native seed-driving calls guarded internally:

```bash
cmake --preset linux-gcc-debug-ccache
cmake --build --preset linux-gcc-debug-ccache-build \
  --target silver-prior-label silver-bridge-test silver-forced-action-audit -j 4
ctest --test-dir build/linux-gcc-debug-ccache --output-on-failure \
  -R 'silver_prior_dataset_fixture|silver_prior_resume|silver_forced_action_fixture'
ctest --test-dir build/linux-gcc-debug-ccache --output-on-failure \
  -L 'core|smoke' -R 'silver_prior_dataset_fixture|silver_prior_resume'
python3 -m unittest tools.test_ironclad_reachable_domain_census
python3 tools/silver_prior_dataset.py validate-plan \
  docs/experiments/evidence/silver_prior_dataset_v1/plan.json
git diff --check
```

Native fixture output:

```json
{"actions":4,"capture_neutral":true,"deterministic":true,"fixture_only":true,"terminal_and_correction_valid":true,"vocabulary":158}
```

The representation fixture covers vocabulary/inverse mapping, distinct copies,
target/potion references, candidate/label permutation, unknown-order and UID
invariance, observed order, Runic Dome masking, excluded-card failure, complete
surface/replicate rejection, deterministic replay, terminal zero-budget
actions, original-root correction, wrong schema/SHA, disjoint L/J identities,
source/act/combat caps, and capture-enabled/disabled gameplay/RNG neutrality.
The 12 resume/finalization tests execute no gameplay. They cover durable
malformed-output preservation, idempotent publication, conflicting writes,
the full-run local prohibition, pilot/full selection binding, actual completed
source counts, zero-root completed sources, partial-selection rejection, and
explicit overlap quarantine followed by release/loader validation. Overlap
attempts remain available and original captures/labels/shards remain unchanged.
Both dataset tests are included in the existing CI smoke label selection.
The existing forced-action fixture remains
unchanged. Source census tests pass 9/9.

Independent implementation review found and repaired timing/raw publication
ordering, incomplete finalization, failure-evidence retention, an internal
loop counter in model inputs, and an undecoded monster-slot bitfield. Final
SHA-bound review and raw verification outcomes are recorded in the draft PR.
The later requested corrections specifically close false full-corpus
completion, immutable overlap-finalization dead ends, and missing CI labels;
they do not change the accepted representation or teacher design.

## Accounting and remaining work

| Unit | Planned | Scientifically completed |
| --- | ---: | ---: |
| Source seeds | 512 (pilot 16) | 0 |
| Combats | Observed, not predetermined | 0 |
| Decision roots | At most 12,288 | 0 |
| Legal actions | Complete native surface at each selected root | 0 |
| L replicate rows | 8 per legal action | 0 |
| J roots | One per validation/test source, up to 128 | 0 |
| J replicate rows | 8 per judged legal action | 0 |

L requires 40,000 requested continuation simulations per legal action; J
requires 80,000, with immediately terminal actions consuming zero. These are
budget formulas, **not throughput measurements or wall-time estimates**. A
forecast remains unavailable until the reviewed-SHA pilot runs. The driver
will report capture seconds, legal-action counts, L throughput, compressed
storage, act/encounter/turn/raw-HP coverage, observed vocabulary, failures,
missing roots, split overlap, and intended/completed counts separately.

Once the designated execution path is available: verify remote source-seed
freshness, freeze the independently reviewed SHA, deploy/build it through the
existing GCP procedure, bind the run, and execute the 16-source pilot. Use its
measured costs to assess the configured budget before the full collection.
Pilot/full jobs have identical identities and reuse completed roots only when
the source/schema/selection/teacher contracts match exactly.

This work makes no policy-quality claim. The historical harmful-root teacher
regression remains unresolved. No network training, policy integration,
rollout modification, model format change, or simulator ID change is included.

**Knowledge impact:** stable dataset schemas, public feature boundaries,
teacher integrity, and collection/resumption procedure are maintained in
[the operations field map](../../../knowledge-base/operations/silver-prior-dataset.md).
This evidence directory contains the frozen plan and execution blocker, not a
scientific result.
