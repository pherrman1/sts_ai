# R1 restores the immediate route, but does not preserve the engine

**COMPRESSION_PATH_FRAGILITY_CONFIRMED.** One preregistered R1 rescue treatment
restored the historical floor0 Headbutt choice and first map(5,0), instead of the
completed13-skip arm's(1,0). Seven later frozen skips executed. R1 naturally acquired
Corruption at floor7, but the unforced MCTS controller exchanged it for Vajra at
WeMeetAgain on floor20. It never owned Dark Embrace or either Flash and died to
Automaton on floor33. The engine never completed. Stop this seed; no second rescue,
capture replay, oracle run, beam implementation or model work.

Starting reviewed #844 SHA: `dbd2a1f7b44f1467ab45ae1346f0bc02c3125788`.
Frozen independently reviewed runtime/protocol SHA:
`e37fac336fbaf0227c088afaddc2cd2a5808a9fb` (PASS, no blockers).
Final publication SHA is recorded in the #844 handoff, outside its own enclosing
commit. Same branch/chat/app-managed worktree; no new worktree/thread or merge.
Prior13-skip result and raw evidence remain unchanged; R1 is a new experiment.
Knowledge impact: bounded experimental evidence and current-research stopping point,
not a production/default/model change.

## Exact patch/manifest contrast and build

[Incremental R1 patch](r1-enabled-entry.patch) adds one constructor assignment for
`enabled:false` and disabled-count accounting to the previous historical research
header. [Complete patch](historical-intervention.patch) applies to source
`d8fd2a105a8d2a481b7639e26c683f75e382e3d4` in a separate plain source archive,
not current production C++. The historical run_driver.cpp is byte-identical to the
prior research arm. Existing enabled semantic matching/execution/fatal paths do
not change; the existing NOT_SEEN relevance check excludes disabled entries before
enumeration/matching/execution. Omitted enabled=>true, explicittrue=>same semantics,
false=>DISABLED_BY_DESIGN. Manifest unset remains free of additional enumeration
and trace emission. No arbitrary action override or generic branching framework.

[R1_INTERVENTIONS.json](R1_INTERVENTIONS.json) has all13 original identities and is
exactly the original frozen JSON plus interventions[0].enabled=false. Remaining12
objects/semantic keys are unchanged and enabled by default. The old manifest's
status/new_runs fields remain historical freeze metadata, not execution status;
treatment.json is the authoritative R1 execution receipt.

| Artifact | SHA256 |
|---|---|
| New research-patched binary |cb46712feaccfc4ae874b37ba1437261e4b64bfcf62ea92682b0204438505509|
| Complete historical patch |763c005e85f63e46de666546181950f11420be92f49df046d8278fd2f7dd1479|
| R1 delta patch |fdfad711801f761226a0b95c3465213b1089796d38b0992b9f29e04895d44f2f|
| R1 manifest |e169bb62143b5034d8182f81851aeee6f1492da5a1b0c7ece23ff73d686ce5cd|
| Original unchanged manifest |c98f1671a12ac41f7bee827f8f7428d4aedf628b10f2cedd9c14ec58f982754e|

This binary is neither the original historical executable nor the completed13-skip
binary. Same historical source/configuration, eight exact models, GCC13.3.0 Ubuntu
13.3.0-6ubuntu2~24.04.1 / CMake4.4.2, linux-gcc-release/linux-gcc-build, parallel4,
Release/O3/DNDEBUG/OpenMP/LTO, same pinned submodules. Actual compile/link flags match
the qualified historical reconstruction after source-path normalization.
[Build identity](build-result.json), [flags](build-details.json), [raw build log](build.log),
[raw configure output](configure.log.gz), [frozen contrast/charter hash](FREEZE.json).
Original runtime and earlier research runtime/source/evidence remain intact.

## Qualification and primary mechanism

One manifest-unset qualification matched the entire historical header, all137
retained public states and136 traces with no exclusions or differences. It stopped
intentionally after that prefix, not at a full-run outcome. Wall394.772s,
childCPU386.264s. No retry, environment correction or comparator weakening.
[Receipt](parity.json), [raw states](parity.states.jsonl.gz), [raw trace](parity.trace.jsonl.gz),
[independent pre-launch review](independent-review.json).

Only then the one R1 treatment ran with the same reviewed binary/seed/settings/models
plus the R1 manifest, through the historical seed guard. Its first three trace
objects were exactly historical before any enabled intervention. Floor0 Headbutt
was selected by ordinary MCTS, not forced. The first post-floor0 map choice was:

| Arm | First map node | Mechanism |
|---|---|---|
| Historical control |(5,0)|Take floor0 Headbutt|
| Completed13-skip |(1,0)|Skip floor0 group|
| R1 |(5,0)|Disable floor0 override; ordinary controller takes Headbutt|

This supports the floor0 skip as the cause of the immediate route bifurcation in
that completed arm. It does not establish that restoring it preserves the rest of
the trajectory or explain the whole package-level death. R1's first enabled skip
was floor1/actualdecision3, the second historical Headbutt group. The first later
map-node difference was act2/floor18: R1(3,0), historical(0,0), actualdecision57
versus historical52. This is the first later MAP-node difference, not a claim
that every earlier non-map policy choice remained identical.

## R1 execution and thirteen statuses

Normal full run completed, simulator integrity PASS, all118 public OOC states
supported. Wall273.869s, childCPU264.616s. Highest act2/floor33, Heart not killed,
finalHP0. Automaton was fight15; it entered with60/80HP,18 permanent cards,
281gold and one Power potion. No action, path or survival repair was applied.
[Receipt](treatment.json), [raw public OOC states](treatment.states.jsonl.gz),
[full trace and final summary](treatment.trace.jsonl.gz).

Exactly13 =7 MATCHED_EXECUTED +5 NOT_SEEN +1 DISABLED_BY_DESIGN;
failed0, duplicate executions0. [All13 rows](TRIGGERS.md) regenerate from raw summary.

| Act/floor | Historical target | Status |
|---|---|---|
|1/0|Headbutt|DISABLED_BY_DESIGN|
|1/1|Headbutt|MATCHED_EXECUTED|
|1/3|Shockwave|MATCHED_EXECUTED|
|1/10|Anger|MATCHED_EXECUTED|
|1/12|Reaper|MATCHED_EXECUTED|
|1/16|Impervious|MATCHED_EXECUTED|
|2/20|Anger|NOT_SEEN|
|2/22|Havoc|MATCHED_EXECUTED|
|2/24|Blood for Blood|MATCHED_EXECUTED|
|2/27|Limit Break|NOT_SEEN|
|2/29|Battle Trance|NOT_SEEN|
|2/33|Impervious|NOT_SEEN|
|3/36|Panic Button|NOT_SEEN|

Unseen groups were not replaced: floor20 was an event, floor27 a rest, floor29 had
Reaper/Pommel Strike/Uppercut rather than the frozen group, floor33 ended in a boss
loss and act3/floor36 was not reached. Disabled floor0 is not counted as unseen.

| Actual decision | Act/floor | Cards after skip | HP | Gold | Corruption / Dark Embrace / Flash |
|---:|---|---:|---:|---:|---|
|3|1/1|12|60|99|0 /0 /0|
|11|1/3|14|66|0|0 /0 /0|
|32|1/10|15|67|4|1 /0 /0|
|40|1/12|16|31|71|1 /0 /0|
|52|1/16|16|46|101|1 /0 /0|
|71|2/22|17|17|215|0 /0 /0|
|78|2/24|17|22|231|0 /0 /0|

## Natural engine history and exact loss boundary

[measurements.json](measurements.json) contains every engine offer/action's complete
public pre/post state, floor/decision/deck/HP/gold, all ownership transitions, and
full cards_offered.cards occurrences. Core ownership was not operationally forced.

| Ingredient/action | Act/floor; actual decision | Owned before -> after | Permanent cards after | HP | Gold |
|---|---|---|---:|---:|---:|
| Dark Embrace offered with Headbutt/Dropkick; MCTS takes Headbutt |1/0;1|0 ->0|12|68|99|
| Corruption offered; tree rule takes gold first |1/7;23|0 ->0|14|64|44|
| MCTS takes Corruption |1/7;24|0 ->1|15|64|44|
| WeMeetAgain: MCTS gives Corruption, obtains Vajra |2/20;65|1 ->0|17|41|200|
| Flash of Steel |No offer/acquisition before death|0 throughout|—|—|—|

There was no later Dark Embrace offer/acquisition and no Flash offer/acquisition
in the retained public records; the run ended before the historical Sensory Stone
region. All118 records are supported. Corruption was not silently removed by a
skip: its loss is a separate ordinary MCTS event action, trace/state75. The exact
historical GameContext.cpp WeMeetAgain branch removes the offered nonbasic card
for option2, then awards a relic; raw pre/post show Corruption removed and Vajra
added with unchanged HP/gold. No rationale about the controller's utility estimate
is inferred from that action.

Maximum owned engine counts were1/0/0; final counts0/0/0. Engine completion never
occurred, so completion deck size, first-engine-complete target/entry deck and
active minimum are unavailable. Last-combat permanent18 is not an engine-preserving
13-card reduction versus historical31. The historical target minimum active30
cannot be compared with an unobserved R1 target. Mark of Pain Wounds are temporary
combat cards, not extra permanent deck entries.

Counterfactual capture replays0, captured/selected public combat roots0, annotated
worlds0, no candidates or witnesses. Fractions/reach/node-cap rate stay null;
[MATRIX.md](MATRIX.md) records why annotation was not reached. No oracle NONE or
negative infinity label was produced. Original oracle/K/bounds remain unchanged.

## Conclusion and checks

**COMPRESSION_PATH_FRAGILITY_CONFIRMED** for this historical seed and the remaining
frozen skip package. The immediate route cause was isolated, but R1 still changed
later route, lost the acquired engine card through natural policy, and died before
useful engine completion. The floor0 skip is not a sufficient explanation of the
whole package failure. This does not attribute failure to an individual later skip,
prove that all reward compression is incompatible with the engine, or estimate a
win-rate effect. No actual engine-preserving combat compression lever was measured.

Stop hand-designed subset chasing on this seed. No second Headbutt restoration,
leave-one-out/binary search, other seed/lead, beam implementation, oracle change,
model/reward/AZ/Silver/default change or merge. No next experiment was launched.

Eight seed-free hook contract groups PASS; actual integration qualification is the
full simulator parity run, not the stub tests. measure.py --check and analyze.py
--check validate every committed measurement/table against archived raw bytes.
Independent implementation and final evidence reviews, source/runtime/model custody,
prior evidence checks, repository health, ledger dry-run and whitespace outcomes
are retained in review/check artifacts. GitHub CI is not claimed passed; no manual
redispatch while account billing/start failures remain a separate condition.
