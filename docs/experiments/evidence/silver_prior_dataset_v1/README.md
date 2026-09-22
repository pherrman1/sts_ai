# Silver prior dataset v1: local collection complete

**The frozen 512-source corpus completed locally at reviewed executable SHA
`dd18c1cac3b47f8e4c13607a1274f714a778e6f5`.** The full integrity report
is training-ready: 512 completed sources, 11,868 selected roots, 128 J roots,
zero missing roots, zero failures, and zero cross-split duplicates. The
release-gated loader yielded all 8,862 TRAIN rows. No network was trained or
policy-quality result measured.

The designated GCP instance was unavailable. Its earlier read-only status
returned exit 1:

```text
ERROR: (gcloud.compute.instances.describe) Could not fetch resource:
The resource 'projects/sts-ai-502709/zones/europe-west3-c/instances/sts-test' was not found
```

No replacement infrastructure was created. The user authorized this exact
frozen plan locally. The collector required `--local-512`, froze a four-worker
bound, and still guarded every native source and root invocation. The original
[collection-status.json](collection-status.json) is the pre-collection,
zero-count snapshot; it is not the outcome of this later run. The checked-in
representative shard remains a fixture and is rejected by the training loader.

## Frozen plan and evidence

- Inspected handoff baseline: `289e1ab96d4a022d894756b9108bb081e34be8a3`.
- Implementation baseline/current main at preflight:
  `8613f9c7811ce19a81cb731e78b6b58d01ec91ca`.
- Review-correction base: current main `ac9db6c2`, merged into the task branch
  without conflicts. The original `dbeb3fcc` review freeze was superseded by
  independently reviewed collection SHA `dd18c1ca`.
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
  intended/completed accounting, artifact inventory, and absence of forecast
  at the original pre-collection snapshot.
- [binding.local-512.json](binding.local-512.json),
  [pilot-report.local-512.json](pilot-report.local-512.json), and
  [collection-report.local-512.json](collection-report.local-512.json): copied
  binding and measured reports from the complete durable corpus at
  `/home/philippherrmann/Documents/sts/silver-prior-v1-corpus-v2`.
- [checksums.json](checksums.json): SHA-256 of committed durable data artifacts.

The source freshness inventory covers tracked repository experiment evidence,
including compressed manifests/roots and conservative numeric seed ranges.
Remote inventory could not be checked. Historical audit roots do not satisfy
the new source SHA/Act-3 corpus protocol; only the correction fixture was
reused. The complete run bound a clean independently reviewed SHA, binary/model
hashes, and matching regenerated vocabulary before capture. Binding hash:
`7febae9df90e427ad5db631a2004ff4c4cdd579346d22d25b3e1f4532af96e17`;
selection hash: `ed91b3bb4c6983be3701333320f1e6c12f7332e3e371ac24b857a76a47d3b5ed`;
release hash: `b32d8d79b44ee799af05892e79e45fb146f4859df58364722d7cd92531bd8419`.
The first pilot attempt at SHA `71d48d28` failed on a preserved native
potion-discard target sentinel. Its evidence remains in the separate
`silver-prior-v1-corpus` directory. The targeted projection correction was
independently reviewed before the successful SHA-bound restart.

## Verification

Focused checks at the collection SHA, with native seed-driving calls guarded
internally:

```bash
cmake --preset linux-gcc-release-ccache
cmake --build --preset linux-gcc-release-ccache-build \
  --target one_combat silver-prior-label silver-bridge-test -j 4
python3 tests/silver_prior_resume_test.py  # 15/15, no gameplay
python3 tests/silver_prior_dataset_fixture.py \
  build/linux-gcc-release-ccache/silver_bridge_test \
  build/linux-gcc-release-ccache/silver_prior_label
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
The 15 resume/finalization tests execute no gameplay. They cover durable
malformed-output preservation, idempotent publication, conflicting writes,
the exact-plan local exception and corpus lock, pilot/full selection binding,
actual completed source counts, zero-root completed sources,
partial-selection rejection, and explicit overlap quarantine followed by
release/loader validation. The native fixture also covers the packed
potion-discard target. Both dataset tests are included in the existing CI
smoke label selection. CI was not run for this collection because the user
waived it during the GitHub billing issue.

Independent implementation review found and repaired timing/raw publication
ordering, incomplete finalization, failure-evidence retention, an internal
loop counter in model inputs, and an undecoded monster-slot bitfield. Final
SHA-bound review and raw verification outcomes are recorded in the draft PR.
The later requested corrections specifically close false full-corpus
completion, immutable overlap-finalization dead ends, and missing CI labels.
The local override is restricted to the exact frozen plan hash; the pilot
revealed a potion-discard projection sentinel and that targeted correction
received a fresh independent review before collection restarted.

## Collection accounting

| Unit | Planned | Completed |
| --- | ---: | ---: |
| Source seeds | 512 (pilot 16) | 512 (pilot 16) |
| Combats | Observed, not predetermined | 8,492 (pilot 84) |
| Decision roots | At most 12,288 | 11,868 (pilot 88) |
| Legal actions | Complete native surface at each selected root | 76,172 (pilot 620) |
| L replicate rows | 8 per legal action | 609,376 (pilot 4,960) |
| J roots | One per validation/test source, up to 128 | 128 |
| J replicate rows | 8 per judged legal action | 6,184 |

L requires 40,000 requested continuation simulations per legal action; J
requires 80,000. The full run requested 3,046,880,000 L and 61,840,000 J
simulations; it actually executed 2,931,845,000 L and 60,340,000 J because
immediately terminal actions consume zero. The 16-source pilot measured 438
serial capture-seconds and 141 serial L-seconds, forecasting 14,005 serial
capture-seconds for all 512 sources and 19,659 serial L-seconds at the
12,288-root ceiling. These were cost extrapolations, not wall-time promises;
the full measured L sum was 14,959 seconds. The report keeps source, root,
split, act, encounter, turn, HP, vocabulary, simulation, failure, and overlap
accounting separately.

The finalizer passed exact source/selection/job/shard membership, hashes,
native action and replicate validation, and projection checks. It found no
cross-split duplicate groups, so no quarantine was needed. The release-gated
training loader yielded exactly the 8,862 TRAIN observations with matching
candidate/value lengths; VALIDATION and LOCKED_TEST rows are excluded from
that iterator. The complete 3.6 GB corpus remains outside the worktree at
the durable path above.

This work makes no policy-quality claim. The historical harmful-root teacher
regression remains unresolved. No network training, policy integration,
rollout modification, model format change, or simulator ID change is included.

**Knowledge impact:** stable dataset schemas, public feature boundaries,
teacher integrity, and collection/resumption procedure are maintained in
[the operations field map](../../../knowledge-base/operations/silver-prior-dataset.md).
This evidence directory contains the frozen plan, historical blocker, and
post-collection integrity reports. It does not establish policy quality.
