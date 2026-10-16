# §497 recovered-delivery import and seal audit

Baseline main `b35c179eb` (PRs572/573 merged). The user supplied transport
branch `claude/heart-outcome-data`, pinned commit
`e3b649ced5a392f78e9412787a84d458cffd60a1`, explicitly never merge. Extract
only `heart-outcome-collection`; check every SHA256SUMS entry and the complete
file inventory. Delivery index must be byte-identical to main's evidence copy,
SHA256 `e3621c3873dc0155edd651f787802412560b632ee6cca3f32b6e4ed2be746026`.
Existing archived data satisfy this task; no new game seeds, canaries or fits.

The current user explicitly directs use of original `wWW` deliveries excluding
lost workers7,8,27,34, replaced by both `rWW-0` and `rWW-1`. This is41 original
workers and8 replacement halves,49 accepted deliveries/1800 unique source seeds.
All four original partial archives remain superseded opaque evidence. No
outcome-dependent choice of delivery or source is permitted. Preserve the
recorded recovery deviations; do not claim unchanged no-retry compliance.

## Immutable identities and checks

Producer source `7527b5d5d07467688101212660461995665512b9`; binary
`178e7076934097987e473ab04c2dc80eec5368f9dcb12b274a631bad62f43e4e`;
Arm C native `eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509`.
Cloud plan `4b49a40427dde2470044847e8e843cc349a460e183d6fa2ddbdda4c0494d14a3`,
bundle `836a34129c99bfd68e691ed802f0a403cd75e37db7effd0e1b01f51b4697f6d5`,
activation `9f66ee277e52874b8c74dcd11561027f827029b336da28f81c534e3c5a041b22`.
Verify frozen teacher environment, artifact/tool hashes, cloud-canary completion
hashes, review/activation/latch bindings, resource receipts, exact source ownership
and archive hashes. Cloud producer Python3.13.16/NumPy2.5.3 is a distinct runtime
freeze; local offline validation does not execute or relax that producer's guard.

Only literal `train.tar.gz` and `validation.tar.gz` names may reach a tar parser.
Every member must be a regular canonical assigned-source path, with a complete
8-file unit and exact 7-file hash binding in its receipt. Check source/binary,
healthy footer, fixed public schema, actual driver origin/trace alignment,
ordered coverage, objective/keys/A20/full-run, frozen policy/environment and
pinned Arm C load/scoring contract (>=90% prior and rollout, zero legacy leaves).
All1080 TRAIN and360 VALIDATION sources must pass; invalid/incomplete units are
not relabeled as deaths or silently filtered. A failed audit stops without
training. Source-balanced later learning must split by whole run.

## TEST and partial custody

Hash bytes only: all49 `SEALED-test.tar.gz` files and4 superseded
`SEALED-partial-out.tar.gz` files. Never open a tar parser on them, list their
members, extract receipts or trajectories, read labels/logs, or compute TEST
outcome counts. The360 TEST source completions are producer receipt attestations,
not independently parsed TEST framing/clock claims. No fitting or TEST-opening
latch is created by this audit. Any eventual TEST use needs a separately reviewed
one-shot protocol.

## Frozen decision rule

Use the original plan's class-coverage gate without adaptation: TRAIN >=20 wins
and >=20 losses; VALIDATION >=5 wins and >=5 losses. Count complete runs, not
states. After all structural/custody checks, verdict is TRAIN_VALIDATION_READY
only if all class gates pass, otherwise INSUFFICIENT_CLASS_COVERAGE. Do not
extend/replace seeds, pool historical outcomes, fit despite a failed gate, or
open TEST to find more positives. Neither verdict qualifies a trained head,
model speed, gameplay, RL or native value-head integration.

Operational limitations remain explicit: the export check was one-way, not a
roundtrip; its review timestamp text does not prove final approval chronology.
Fixed simulation counts alone do not prove byte-identical behavior on W11's
different CPU. Public-record/native parity remains unqualified. These limits
are not turned into an inference-speed or teacher-quality comparison.

Done when: reviewed importer/synthetic refusal tests, exact data audit, separate
TRAIN/VALIDATION class counts and sealed-custody receipt, ledger/current-KB update,
and scoped PR evidence. Preserve all source data and the transport branch.
Knowledge impact: current corpus readiness/custody and reproducible import procedure.
