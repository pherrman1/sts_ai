# Observed A20 Heart-outcome corpus preparation (§497)

User authorized setup of complete-run outcome learning and clarified available
cloud resources are **Claude workers**, up to45 with four CPU cores each. No
third-party infrastructure/account provisioning and no Codex cloud dispatch.
Base: main `9129e5b850ba45114820956522cbc92c238c2afe`. Previous §494–496 targets,
models and TEST verdicts remain unchanged and are not pooled with this corpus.

## Hypothesis and scope

Value supervision from completed runs under fixed native Silver can remove the
nonterminal X2-B bootstrap from the **label**, while preserving the initial
search teacher. A prepared finite cloud cohort plus guarded local canaries
qualifies collection, not a trained value model or RL loop. No value-head native
integration, policy retraining or automatic promotion is included.

Use the existing `t_realRunContextObserver`, called only at the top of the
driver-owned `runFullRunOOC` loop. Record one public boundary before each real
OOC driver step and real battle entry. Composite policy steps can skip their
internal intermediate states; this is sampled visited-state coverage, not a
claim of every primitive-action state. Never use MCTS particles or forked
counterfactual continuations as observed trajectories.

The new `heartoutcomegen 1 SEED OUT.jsonl on|off` command fixes A20 Ironclad,
keys on, full run, no forced relic and exact10k ordinary project-fair native
Silver real combats with allocated reuse cap32768. Existing §494 teacher:
Arm C tree prior and rollout policy, calibrated A20 CTM, rollout3/native public
X2-B,512 OOC simulation cap, early-stop1, no CPU_SECONDS limit. Fixed simulations
avoid hardware-speed-dependent decisions. The collector adds no learned leaf.
X2-B may guide the frozen search, but is not emitted as the outcome label.

## Records and censoring

Exclusive fresh JSONL per source: header with source/policy/objective, ordered
actual-state rows, then one complete simulator-integrity-checked outcome footer.
Value label is1 iff the completed played run killed the Heart; otherwise0.
Missing footer, timeout, crash, health failure, stopped run, wrong objective,
producer mismatch or unsupported capture failure is **not a loss label**.
No state labels may be materialized until the whole source is validated.

Public inputs use existing `heart1-public-record-v2`; unsupported boundaries
are retained as metadata/reasons, and do not become model inputs. Keep the
existing `recordPublicParityQualified=false` limitation. At least80% of a
source's actual driver boundaries must encode; never replace/filter whole
source seeds to meet gates. Seed, source identity, result and all provenance
remain metadata, not network inputs. Each trajectory is one independent split
unit; future fits must weight sources to avoid long successful runs dominating.
All its supported states share the observed return under this fixed behavior
policy, not an optimal-policy win probability or action-counterfactual value.

## Exact seeds, budgets and gates

Local qualification:110179994 captureOFF/ON and110179995 ON, sequential,
3600s per unit. Compare exact real state/offer/post traces, MCTS action traces and final outcome,
verify frame/support/model-use integrity. These canaries are excluded from fit.
Claude qualification uses110179996 OFF/ON and110179997 ON on its actual producer.
Record exact binary/model/tool/source and hardware/resource identities. A cloud
rebuild must freeze a new bundle/plan and qualify it before dispatch; never
pretend a different compiler-produced executable has the local binary hash.

Prepared cloud cohort: exactly1,800 fresh sources110180000..110181799:
first1,080 TRAIN, next360 VALIDATION, last360 TEST.45 fixed round-robin shards,
40 seeds each:24 TRAIN/8 VALIDATION/8 TEST. Four single-thread producer processes
per worker; verify at least4 effective CPU-equivalents (quota and affinity).
3600s/source, clamped to a single21600s global deadline created once after
independent canary review and durable native artifact export verification.
No retries, replacements, seed extensions or pooling; any incomplete source
prevents claiming a complete corpus. No TEST evaluation or aggregate outcome
peek by the coordinator: separate SEALED-test archive, hashes/receipts only.

Independent approval must bind plan, source, bundle, completion-anchored canary
hash and original files. Workers reverify this approval chain and the coordinator
published immutable activation hash; an unapproved activation cannot start sources.
Python and NumPy versions are frozen with the bundle. Reuse the existing encoder
for full supported-record schema validation and the reviewed Arm C runtime contract
(loaded64/4/256/2/trim1,≥90% prior and rollout scoring, zero legacy prior leaves).
Semantic failures receive censored failure receipts and all partial outputs are archived. A ≥256MiB cross-container artifact export roundtrip
with matching hashes is required before the one exclusive activation latch.
Cloud operation is delegated via the coordinator handoff; no cloud workers are
claimed active from preparation alone. Keep all partial/failure artifacts.

Before fitting, a separate import/seal audit must verify all1800 source receipts,
unique source ownership, exact assignments/splits, identical frozen producer,
complete valid framing, coverage and loaded/scored Arm C telemetry. TRAIN needs
≥20 Heart wins and≥20 losses; VALIDATION≥5 wins/≥5 losses, without peeking at TEST
outcome counts. Failing these gates is INSUFFICIENT, not permission to extend.
Future TRAIN/VALIDATION fitting/model selection and a one-shot TEST opening need
their own reviewed frozen training protocol; this setup does not open TEST.

## Done when

Native producer, strict source validator, finite assignments, quota-aware worker
runner and separated archives are implemented; focused synthetic/native checks,
independent source/design review and local canaries are recorded. Publish a
reviewable PR plus exact Claude coordinator instructions. Report preparation,
qualification and dispatch states separately. No actual Heart value-model
quality claim follows from a collector smoke or a few observed outcomes.

Knowledge impact: label-capture semantics and finite outcome-data preparation
belong in maintained OOC pipeline/research knowledge and chronological ledger.
