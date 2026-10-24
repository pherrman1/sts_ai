# Heart historical-runtime reconstruction protocol

Frozen before seed execution, starting #844 head
`0772ffe7ca8c63bd941036fa3c8cbecf040c934a`.

Question: can source `d8fd2a105a8d2a481b7639e26c683f75e382e3d4`
reproduce the retained Heart round-2 public trajectory through the declared
ingredient-bearing fight, without the original executable?

Only leads 111101032, 111101326, 111101512, in that order. No AZ work.
Exact executable target SHA256:
`0e17e0f22259afe21f35ba89a0413f2af7663cfae1312311f1ea8c71b00c2d52`.
A different hash is a BEHAVIORAL_RECONSTRUCTION_CANDIDATE until fidelity passes.

## Build and custody

Bounded artifact search precedes build. Use a Git-archive source snapshot,
read-only tracked files, and exact pinned submodules; no new worktree or branch
switch. Follow historical `cloud_worker.sh`: linux-gcc-release preset,
linux-gcc-build preset, one_combat target, parallel 4. Record compiler, flags,
linked libraries, configure/build output and executable SHA. No source patches.
Any required compatibility shim stops execution for reporting.

## Replay and comparison gate

Use original receipt's STS_/OMP_ environment, same unsigned game seed,
heartoutcomegen 1 SEED STATES on, the repository seed guard, and verified
historical Student/model bytes. Change only output destinations. Relative model
paths are preserved in an isolated runtime directory. Inherited STS_/OMP_
variables are removed before applying receipt settings. HOME/PATH reflect the
local machine; they are host plumbing, not policy substitutions.

Existing STS_SILVER_PUBLIC_TRACE and STS_SILVER_PUBLIC_TARGET=SEED:FLOOR
are enabled along with original OOC trace paths. Capture is quarantined until
fidelity succeeds; no oracle runs before that gate. No gameplay actions forced.

Compare every complete historical state object (including the full public
record) and every complete OOC trace object through these frozen prefixes:

| Seed | Ingredient checkpoint | Target fight | Target trace/state index | Last state index |
|---|---:|---|---:|---:|
|111101032|65|act 2 floor 18 fight 11 SHELL_PARASITE|66|67|
|111101326|134|act 3 floor 37 fight 19 THREE_DARKLINGS|135|136|
|111101512|52|act 1 floor 14 fight 8 TWO_FUNGI_BEASTS|55|56|

Also compare the full producer header, including the boolean `rootTrace`
and all policy/model identity fields, exactly. Public
states carry deck IDs/upgrades, relic IDs/counters, potions, key bits, map/path,
screens and offers; trace objects carry HP/max HP, gold, public pre/post states,
OOC decisions/options and fight identity. Misc values and engine RNG states not
recorded historically cannot be compared; no invented values fill that gap.

Stop immediately at the first material mismatch (record JSON pointer and both
values). No seed/configuration massage. One correction is permitted only for
an obvious missing historical setting supported by source/receipt, documented
before retry; otherwise stop the reconstruction and do not try other seeds.

For an identical prefix, stop only the owned process group after the target
battle's post trace and following public state are flushed and verified.
This intentional bounded-prefix termination is not a full-run completion.
Per-run wall limit 1,800 seconds, OMP_NUM_THREADS=1, at most three sequential
runs; no adaptive seed extension. Original full-run cloud times were about
756/910/721 seconds. Hash-identical runtime still requires normal replay
qualification. Hash-different runtime with exact frozen-prefix agreement earns
CHECKPOINT_IDENTICAL / BEHAVIORAL_RECONSTRUCTION_QUALIFIED.

## Qualified capture and annotation

After qualification retain all ordinary public player-decision roots in the
target fight under the same execution receipt and full OOC run relic inventory.
Apply existing #844 frozen selection: Tier 1 active hand+draw+discard <=8 with
suitable draw/energy, otherwise Tier 2 strongest known engine with smallest
active pool; never weak filler. At most four roots per combat, ordered by lower
active count, stronger ingredient class, earlier decision. Freeze root hashes
before annotation. Distinguish ingredients from an observed near-infinite state.

Use unchanged adapter: K=4, depth 24, nodes 2,000, candidates 16, replay periods
128, actions/candidate 1,024, total replay actions 4,096. No adaptive reruns or
budget increases. Inspect any candidate/kill before continuing to the next lead.
No model, reward, policy, gameplay, production capture schema or oracle changes.

Stop on supported user-defined conclusion; if replay diverges or reconstruction
fails, no oracle annotation or fresh current-policy cohort is launched.
