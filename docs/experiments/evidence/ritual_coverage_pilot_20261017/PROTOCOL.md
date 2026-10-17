# Controlled A0 Ritual coverage pilot — preregistration

Status: **prepared for implementation review; not executed; user resource
approval pending**. This protocol grants no collection, fitting, TEST access,
support change or promotion. Final source, executable, build receipt, teacher,
artifact headers, split metadata, launch recipe and independent review must be
frozen before an approved run. The implementation and user approval must
agree with the exact recipe; a draft protocol is not execution authority.

## Question and evidence inventory

Can the corrected source produce adequately replicated positive Ritual growth
and identified potion paths in controlled Writhing combat states?

The preserved old TRAIN/VALIDATION intersection has only three positive TRAIN
labels and no positive VALIDATION labels. The old native producer lost lethal
Dagger growth and credited half-dead phases; rows lack the history needed to
repair labels and later pre-states. The artifact-bound §503 diagnostic used
the actual deployed children, but its 143 all-zero VALIDATION targets cannot
qualify positive growth. The reviewed §504 one-source corrected canary emits
24 valid RAW rows in 16.344 s, including Writhing 18→21, but guarantees only
one ordinary Dagger and no potion/upgrade/copy coverage. No preserved corpus
therefore supplies the corrected, provenance-bound cells required here.

This is an **intervention-conditioned development data pilot**. It does not
measure ordinary gameplay, upstream calibration, model quality or active-Tail
composition. No fit objective or intervention is chosen from its labels.

## Fixed public-state intervention

Use the existing `combattransitionforcedgen` loop and twelve exact setup names:
`ritual_writhing_v2_{base,upgraded}_{single,double}_{natural,brew,smoke}`.
Cell order is base before upgraded, single before double, and natural, Brew,
Smoke in that order. Unknown names fail closed. Existing setups are preserved.

All variants obtain the existing once-run Dagger and share the ordinary
prefix until the first Act-3 hallway fight. At each such fight, before both
predictor and RAW pre-state capture:

1. Force Writhing Mass. Retain the first one/two physical Daggers, remove
   surplus Daggers, append missing ones without acquisition hooks, and reset
   upgrades and damage to the declared state: single `[15]`, double `[15,30]`.
   Recompute physical indices within each fight; do not treat ordinal as UUID.
   Repeated resets discard previous growth deliberately and must be recorded.
2. Natural leaves the belt unchanged and can naturally hold Brew or Smoke.
   Brew/Smoke retains the named potion if held, otherwise fills the lowest
   free active slot, otherwise overwrites the last active slot. This is
   explicit direct public-state placement, including under Sozu, with no
   potion drinking, acquisition hooks, RNG draw or selected-action override.
3. Bind original public state → normalized combat ROOT → predictor and RAW
   pre-state. Record exact operations, belt/copy/upgrade/damage identities,
   original/normalized predictor inputs and all fourteen RNG identities.
   Require unchanged RNG and unrelated public fields. Mutation is atomic on
   failure. Original- and normalized-state differences are interventions,
   never labels for growth.

Native Silver chooses all actions, then normal native combat and RAW transfer
produce labels. Neither growth nor potion use is forced. Temporary in-combat
upgrading can legally give a base pre-state Dagger +5; legality comes from
native support and compatible traces, not a modulo-three shortcut. A Smoke
escape against single-enemy Writhing has no eligible permanent kill and must
not be required to show growth simultaneously.

## Sources and ordering

Use original source membership only from
`/home/philippherrmann/Documents/sts/wt-ctm-retrain/build/ctm-retrain-a69f8862/p1/split_manifest.json`,
SHA-256 `a32ff220b0a6e4b8fa7350ed0f29cba267ea46cef1b140c60f0cdbb181ba8e85`.
Within 52000000..52000399 select the first eight TRAIN and first four
VALIDATION members, before inspecting any new outcome:

- TRAIN: 52000001, 52000002, 52000003, 52000004, 52000005, 52000006,
  52000008, 52000009.
- VALIDATION: 52000007, 52000011, 52000015, 52000019.

Each source receives all twelve variants: **144 trajectories, twelve original
source groups**. These are reused development sources, and 52000001 is known
from the canary; this is not prospective qualification. Variants and all
fights retain the original source partition. There is no TEST group and no
TEST payload need be decoded.

Run source-major. The first TRAIN source's twelve variants are the mechanics
checkpoint **within the 144**, never twelve extra runs. Continue to later
sources only if custody/capture/requested-cell mechanics are valid. A valid
no-target/no-growth result is retained and does not trigger replacement or
early stopping. Do not stop or extend in response to label coverage.

## Exact teacher, identity and resource ceilings

A0, 10,000 caller simulations, native Silver `project_fair`, plain learned
stopping (`gbt-770201c31f7b`, threshold 0.0323), allocated reuse cap 32768,
absolute playout action cap 1000, singleton roots unsearched. Root prior,
adaptive/exact-root budgets, pruning, sequential halving, direct learned leaf,
Arm C, CTM rollout and student are off. Keep the canary's historical legacy
rollout table and all three leaf terms explicitly off.

Copy the canary teacher/model custody into the new frozen teacher and pin
current clean source/executable identities. Explicitly set:
`STS_COLLECT_KEYS=1`, `STS_STOP_AFTER_ACT=0`,
`STS_CTM_GEN_DEPLOYED_OOC=0`, plus every existing canary setting. Do not inherit
caller `STS_*` options. These match the canary's effective keys-on Path-B
policy, while removing reliance on defaults. Any Act-4 continuation is retained
and reported outside this Act-3 target slice. This is not historical-teacher
reproduction or a paired gameplay comparison.

The user approval request will cover:

- Exactly 144 planned source/cell units, no replacements, retries or extension.
- **At most two native workers/CPU cores**, one thread each; pin affinity and
  OMP/OpenBLAS/MKL limits, no GPU.
- **60 seconds collection per unit**, at most five seconds cleanup for that
  unit's own process group; **90 minutes whole-packet wall time**.
- **8,000,000,000 bytes virtual address space per worker**, at most two workers.
- Every native invocation goes through `tools/seed_guard.sh`; one global
  execution latch and exclusive per-unit outputs prevent accidental reruns.

A clean-source build receipt must bind source SHA/tree/status, reviewed live
ancestor, exact configure/build commands, successful return codes, raw log
hashes and executable SHA. Freeze model/header hashes, teacher, all effective
flags, setup descriptor, source/cell order, budgets and final independent
implementation/protocol review. Recheck identities before execution. No
changed or missing identity is repaired silently at launch.

## Integrity, retention and analysis

Keep every source outcome, target/non-target RAW row, receipt, timeout,
quarantine, partial output, invalid and unattempted unit. The producer buffers
rows per source, so an incomplete source can leave an empty/partial file;
this is incomplete evidence, never zero fights. Retain failure receipts and
all already available partial rows. Stop on source/provenance/capture/setup
integrity failure; kill only this campaign's owned process groups when a
resource boundary requires it. Do not replace or rerun units.

Use the unchanged strict RAW row contract. Require one capture per real row,
no quarantine/unresolved outcome, complete source accounting and matching
source/executable/teacher/setup identities. Requested target predicates must
hold on the actual normalized pre-state before reading labels. Validate
Ritual deltas by native candidate support and structurally compatible exact
potion traces, without neural model inference. Exact RNG reconstruction here
is label/provenance evidence, never a predictor input.

Define ordinary-child support from pre-state only, applying the current
artifact-specific public domain with a deliberate offline Writhing/Ritual
override. Count/exclude active Tail without Bloom, pre-smoke-used, Act-4 and
other unsupported public roots. Retain all such RAW rows. Classify actual
FAST/standard routing from initial Brew, including co-held Brew in natural
or Smoke cells. Describe conditional-on-victory event metrics separately.

Retain common-prefix/no-op duplicates raw. For analysis give each exact
original-source/fight/predictor/pre/outcome/post observation one contribution
and retain the duplicate map. Compare canonical payloads as well as hashes.
Never collapse distinct outcomes/branches simply because their public input
matches. Never treat a variant suffix as an independent source group.

## Frozen coverage rules and interpretation

Report integrity, public-state, growth, actual route, copy attribution and
potion paths separately. For each of twelve nominal cells require:

- Included ordinary-child target roots from at least **4 TRAIN / 2 VALIDATION
  distinct sources**.
- Positive legal target growth from at least **3 TRAIN / 2 VALIDATION distinct
  sources**, counted once per source/cell, using actual captured base/upgraded
  and physical copy count.

In each actual base/upgraded × one/two-copy stratum, require positive legal
growth from **3 TRAIN / 2 VALIDATION sources on each actual FAST/standard
route**, pooling nominal cells within a route without splitting source groups.
For each two-copy stratum/route require each ordinal to show positive growth
from **2 TRAIN / 1 VALIDATION sources**. Joint growth is descriptive: a single
Writhing supplies only one ordinary permanent kill.

For identifiable named-potion use in each Brew/Smoke Dagger stratum require
**2 TRAIN / 1 VALIDATION sources** to call that use path covered. Use exact
compatible generation/escape traces; slot disappearance can be a discard and
is not proof of use. Report ambiguity as possibilities/bounds. Report Brew
recursion, Forge availability, co-held/generated Smoke and structurally
unrepresentable escape separately. Initial presence alone does not cover use.

All integrity requirements and coverage minima passing gives
`PILOT_COVERAGE_ADEQUATE_FOR_REVIEW_ONLY`. Missing source/cell/event coverage
gives `PILOT_COVERAGE_INCONCLUSIVE`. Any incomplete or invalid unit gives
`PILOT_INCOMPLETE_OR_INVALID`. Keep exact missing paths and denominators.
These are small development replication checks, not a power calculation,
fit permission, TEST opening, model qualification or support promotion.
There is no automatic extension after any result.

Knowledge impact: controlled producer and source-bound coverage contract;
no qualified model/default change. No execution has occurred under this
protocol.
