# R1 rescue: restore the historical floor0 Headbutt choice

Starting independently reviewed #844 head:
`dbd2a1f7b44f1467ab45ae1346f0bc02c3125788`.
Accepted execution charter: one new treatment for seed111101326. Same existing
chat/branch/app-managed worktree; no new worktree/thread or manual subset search.
Knowledge impact: experimental evidence and current-research status, no defaults.

## Contrast and hypothesis

The completed13-skip arm executed6 groups, first map node(1,0) rather than historical
(5,0), never completed the engine, and died Automaton act2/f33. Those results stay
unchanged. R1 disables only that manifest's first skip: ordinary historical policy
may take floor0 Headbutt again. It keeps the other12 exact semantic identities and
normal downstream policy. No impossible keys, substitute skips or forced cards/path.
The hypothesis is that restoring this earliest choice rescues route/engine stability
long enough for the remaining reward compression to operate.

Existing evidence supplies the historical control and completed13-skip arm; neither
is recollected as a gameplay-control estimate. Current production C++, oracle/K/
bounds/models/rewards/OOC MCTS/Silver/gameplay defaults remain untouched.

## Frozen patch and manifest

Historical source d8fd2a105a8d2a481b7639e26c683f75e382e3d4; same verified GCC13.3.0
Ubuntu13.3.0-6ubuntu2~24.04.1/CMake4.4.2 linux-gcc-release/linux-gcc-build, Release/
O3/DNDEBUG/OpenMP/LTO, parallel4, pinned json/pybind11 and eight original model files.
Use a new plain source archive under ignored build/infinity-heart-r1-20261025,
not a worktree; preserve both earlier source/runtime/evidence packets unchanged.

`R1_INTERVENTIONS.json` equals the original frozen manifest with the sole addition
interventions[0].enabled=false. Remaining12 are byte-identical JSON objects with
omitted enabled meaning true. All13 canonical keys/act/floor/seed identities remain
unchanged. `FREEZE.json` records exact hashes and this one-field contrast.

`r1-enabled-entry.patch` is the narrow delta from the previous research header;
`historical-intervention.patch` is the complete reproducible patch against d8fd.
Absent enabled=>true, true=>old action semantics, false=>DISABLED_BY_DESIGN. Disabled
entries never cause semantic enumeration, matching or execution. Existing NOT_SEEN
relevance guards exclude them. Normal accounting: matched+not_seen+disabled=13;
failed=0, no duplicate executions. The enabled matching/executor/fatal rules do not
change. Manifest unset still performs no additional enumeration or trace.

The resulting executable is a NEW research-patched binary, never the historical
executable or the prior13-skip runtime. Build/source/patch/model custody is checked.
Seed-free instrumented-API tests cover disabled zero enumeration, remaining12,
absent/true regression semantics, accounting, at-most-once and old failure paths.
These tests are not real simulator qualification.

## Independent review, qualification and budget

Independent implementation/design review; commit/freeze reviewed SHA before seeds.
Then exactly one manifest-unset `qualify.py 111101326 --reviewed-sha SHA` using
original Heart Student-C/MCTS/model/environment settings. Clear ambient STS_/OMP_,
remap observational output paths only, use historical seed guard and model symlinks.
Full header +137 retained state objects +136 trace objects must match exactly,
without comparator exclusions. Stop owned process group after the qualified prefix.
Any mismatch/failure => R1_RUNTIME_PARITY_FAILED; no rescue treatment or retries.

Only PASS permits one `treatment.py --reviewed-sha SHA`. Same binary/settings/seed,
R1 manifest enabled. Natural full run, no outcome-driven retry or intervention edit.
One-attempt run directories are latches. OMP1 and1800wall seconds per execution,
ordinary historical10k real Silver/512 OOC sims; all seed commands use seed_guard.
No other seed, lead, policy, budget or arm.

Primary mechanism: compare the full original trace through the first post-floor0
map choice (first3 trace objects) with R1 BEFORE interpreting gameplay. Expected
node(5,0), control(5,0), prior13-skip(1,0). Check this live; any material difference
before an enabled intervention => R1_EXECUTION_IDENTITY_DIVERGED, abort owned run,
inspect identity read-only, never repair choices or interpret it as gameplay.
If identical, allow natural continuation. Record first later skip and route/state
divergence, every trigger status and all natural engine offers/acquisitions with
floor/decision/deck size/HP/gold.

## Conditional capture and unchanged annotation

Engine = Corruption + Dark Embrace + two Flash of Steel, upgrades allowed. If never
complete/early death: stop this seed, COMPRESSION_PATH_FRAGILITY_CONFIRMED. No next
subset, restored second Headbutt, leave-one-out, other source or seed automatically.

If complete, freeze FIRST subsequent combat, completion/entry permanent sizes and
same-run relic/deck/binary/model/decision provenance. Existing fixed-floor public
trace cannot know this target prospectively: as in the prior accepted protocol,
one identical deterministic capture-only replay may collect that frozen combat;
it is not a second arm or changed treatment. Require full treatment/capture state,
trace/summary/outcome equality before using roots. Maximum executions: one flag-off
qualification, one treatment, and only if necessary one capture-only replay of it.

Capture all normal public player-decision roots. Freeze<=4 distinct public inputs
by active(hand+draw+discard) count then earlier decision, no Tier1 selection gate.
Use same-run complete relic inventory to establish no Shard; never use hidden future
draw order. Oracle adapter byte-identical, K4/depth24/nodes2000/candidates16/periods128/
actions-per-candidate1024/total-replay-actions4096; no adaptive sampling/reruns.
Inspect candidates and independently check any simulator-certified witness.
Report Tier1(active<=8+existing draw/energy screen) separately.

## Decisions and stop

Restored first map(5,0) implicates floor0 skip for the immediate bifurcation; it
alone says nothing about preservation of later engine/route or general survival.
Engine failure/early death after R1 => COMPRESSION_PATH_FRAGILITY_CONFIRMED for this
historical seed/remaining package; stop hand-designed ablations. No individual later
skip attribution or general incompatibility claim from this single observation.

Engine completes with target active minimum<=12 or reduction>=6 from historical30
=> OOC_COMPRESSION_LEVER_ESTABLISHED; actual engine-preserving compression, not
permanent-deck accounting. Additional candidate/certified labels require real oracle
results. If improved but insufficient and no candidate, COMPRESSION_IMPROVES_BUT_NOT_ENOUGH.
Unsupported/capped/NONE are not negative labels. No target means active minimum and
fractions unavailable/null, not inferred from permanent deck size.

Stop after R1 interpretation. No beam implementation, second rescue, models, AZ,
other leads, defaults changes or merge. Preserve prior CI account-billing distinction;
no manual CI redispatch or unearned pass claim.
