# Exhaustive five-skip existence search on historical111101032

Starting independently reviewed #844 head13bed5e0060788f58a0138e563877f1e9c312696.
Accepted user charter authorizes exactly the five-intervention32-mask space,
not more hand-designed subsets on326 and not a general beam. Same chat/branch/
app-managed worktree. This is deterministic feasibility/search on correlated
variants of ONE seed, not win-rate, policy-quality or prevalence estimation.
Knowledge impact: experiment ledger/evidence and current-research status only.

## Frozen source and five interventions

Historical d8fd2a105a8d2a481b7639e26c683f75e382e3d4, same GCC13.3.0/CMake4.4.2
release presets/flags/submodules and eight exact Heart round2 Student-C/MCTS model
files. Current production C++, models, rewards, AZ, OOC MCTS, Silver, oracle and
bounds/defaults untouched. Use a plain archived source snapshot, no new worktree.
New executable is RESEARCH_PATCHED, not original historical or either326 binary.

FROZEN_INTERVENTIONS.json was derived before runs from committed opportunities,
legal-111101032.json.gz and original67-trace prefix. Each take/skip key is verified
against the receipt-bound legal list. Exact seed/act/floor/canonical public reward
group identifies an intervention; historical decision indices/card names are audit
metadata only. No outcome or oracle influenced identities. No Flame Barrier
(transform dependency), Cleric removal, Pandora alteration or engine/map forcing.
Normal downstream policy, including its legal removals, remains natural.

| Bit (LSB=0) | Act/floor | Historical card | Audit decision / trace |
|---:|---|---|---|
|0|1/4|Clothesline|13 /16|
|1|1/5|Armaments|16 /20|
|2|1/10|Twin Strike|32 /38|
|3|1/12|Immolate|38 /45|
|4|1/16|Reaper|53 /63|

All32 manifests are frozen before qualification. Binary digits are MSB-left:
00001 enables only Clothesline,10000 only Reaper,11111 allfive. Disabled entries
stay DISABLED_BY_DESIGN; an enabled but absent exact group stays NOT_SEEN; no
substitute key. Require supported/complete semantic enumeration, one exact typed
SKIP_CARD_REWARD/REWARDS match, existing semantic executor, fatal ambiguity/failure,
at-most-once execution. Five-entry accounting matched+unseen+disabled=5.

The archived patch adapts only seed/count from the previous skip hook and adds a
small manifest-enabled checkpoint to its existing OOC trace before each real action.
It records public state/current encounter/next fight index/native intervention
snapshot. It reads no future draw order or RNG state. Manifest unset emits no
checkpoint and does no extra enumeration. The existing trainingRunValid(true)
predicate is reused for integrity_so_far: this checks the accumulated real-run
health accounting, NOT that a prefix is a decided terminal or training label.
Healthy paths are observational; an invalid prefix is rejected, never a loss label.
No production capture format or generic branching mechanism is added.

## Qualification and one-count execution schedule

Independent implementation/design review, then commit/freeze reviewedSHA before
any seed. Qualify once with manifest UNSET on111101032: complete historical header,
68 public states and67 OOC traces exact, no exclusions/retries. Same original
STSs/OMP environment/models/seed/10k Silver and512 OOC simulations. Clear inherited
STS_/OMP_, remap output paths only; invoke historical tools/seed_guard.sh.
Failure => MASK_SEARCH_RUNTIME_PARITY_FAILED, no search variants.

Successful qualification serves mask00000. Its target fight was played to prove
parity, but mask0 scoring uses ONLY its first engine-complete combat ENTRY; outcome
and later state are excluded. Allfive mask0 statuses are logically disabled by
manifest-unset design. No second mask0 run.

Then mask00001 is the existing first treatment/canary, not an extra arm. Require
all normal trace objects BEFORE its first enabled skip to match the historical
prefix exactly, plus checkpoint/manifest/health/output contract validation. A real
canary death/failed engine is a valid search result, not a reason to change masks.
Technical/parity/canary-contract failure stops dispatch; never rerun failed masks.

After valid canary, run masks2..31 in frozen numeric schedule, four worker runner
processes. Each runner owns exactly one native subprocess/session and separate
fresh files; OMP_NUM_THREADS1, OMP_DYNAMICFALSE. Per-run wall limit900seconds.
Mask-local child CPU is measured in its own runner, avoiding overlapping global
RUSAGE_CHILDREN deltas. No CPU equalization with prior experiments.

Local preflight:12 logical CPUs,8.4GiB available memory, no other native experiment
observed. Measure actual native per-process threads/RSS during qualification and
canary before four-worker dispatch. Build finishes first. Native guard accepts one
source seed/invocation; repository ADR0024 has no fixed numerical seed ceiling,
and the explicit user32-mask authorization covers the31 new variants. No safety
bypass, global process kill or other cohort. Resource problems pause/stop new dispatch,
not substitute seeds/settings. Fresh directories and a batch latch prevent retries.

## Nonadaptive prefix stop and public-state measurements

Engine complete is ACTUAL simultaneous Bash + Pommel Strike(any upgrade) +>=2
Dropkick in permanent deck. Record the first acquisition/completion state, not a
projected Pandora outcome. Stop on first of:

1. actual death (allow native integrity/footer/summary to flush);
2. first combat boundary after engine completion;
3. first boundary at floor>=19 without prior engine completion: historical target
   region floor18 and its reward opportunity have been passed.

If engine completes before that horizon, continue only to first subsequent combat,
even if a normal intervening choice later loses a core card; explicitly record
engine intact at entry as well as ever-completed. No entry lacking core passes the
engine-preserving gate. All current decision/boundary observations are read-only.

A host monitor terminates only its owned process group after the first matching
checkpoint is complete. A short scheduling overrun may leave later raw rows; retain
them for custody, but clip every search measurement and health/ranking input at the
frozen first endpoint. Do not use a later combat result/run outcome as score.
Prefix termination is not a completed run, negative label or full-run integrity
claim. No outcome footer is fabricated. Native status snapshots make pre-stop
MATCHED/NOT_SEEN/DISABLED counts auditable even on intentional prefix stops.

Record Pandora offered/selected naturally and actual pre/post transformation
products; two Dropkicks must really exist. Record current/maximum relevant cards,
completion size, first target identity/entry deck/HP, allfive statuses, alive/dead,
stop reason, source/binary/model/manifest/receipt hashes, wall/CPU and cap/technical
failures. Technical/incomplete masks are not negative feasibility evidence; no
exhaustive-absence verdict or capture follows an incomplete32-mask evaluation.

## Frozen ranking and gate

After ALL32 valid results, lexicographic ascending key:
(-engine_complete,-alive_first_post_engine_target,entry_deck,-entry_HP,
 enabled_skip_count,numeric_mask). Missing target deck sorts after real sizes.
Fewer forced skips means smaller enabled subset(popcount); actual matched skips
are reported separately. This is a deterministic search objective, no oracle score.

The single ranked best passes capture gate only if its actual full engine remains
intact at an alive first post-engine entry and permanent deck<=14. Historical
control is18 permanent/minimum active16. If no qualifying best exists, report
STATIC_SKIP_SEARCH_NO_ENGINE_PRESERVING_COMPRESSION and stop; disclose any edge
case where overall ranking and feasibility differ rather than silently reranking.
No Cleric addition,512 continuation, adaptive mask or beam implementation.

## Single permitted selected-mask follow-up

Only after complete exhaustive matrix, frozen ranking and gatePASS: exactly one
capture-only replay of that identical best mask if required by fixed-floor public
trace. This is data collection, not another search evaluation. Enable existing
public trace targetSEED:FLOOR, same OOC pairing/receipt/models. Require exact equality
of ALL trace/boundary records through frozen target ENTRY and the same public-state
prefix. Then let ONLY that target combat finish to collect its roots, verify health,
and terminate. Its outcome does not alter search ranking or choose another mask.

Use actual combat active(hand+draw+discard) counts; compare historical16, report
whether any active<=8. Freeze<=4 distinct ordinary public roots sorted(activecount,
 earlier decision), no Tier gate. Same-run full relic proof/noShard and unchanged
public-conditioned determinization; no privileged real hidden draw order.
One unchanged adapter batch:K4/depth24/nodes2000/candidates16/periods128/
replay-actions-per-candidate1024/total4096. No adaptive reruns or oracle/budget changes.
Inspect all candidates and independently verify any simulator-certified witness.
Only real damaging candidates/real certified victory earn the corresponding labels.

Report permanent and active compression separately; classify lever versus insufficient
compression from actual selected target evidence, never from a projected deck alone.
NONE/unsupported/cap hits are not negative labels. Stop after this search and its
single gated capture/oracle packet. No model/default change, further static subset,
new worktree/thread, general beam or merge. Existing326/R1 conclusions unchanged.
