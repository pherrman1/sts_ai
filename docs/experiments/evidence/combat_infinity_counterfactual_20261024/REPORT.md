# Frozen reward skips failed to preserve the engine-bearing trajectory

**COMPRESSION_SURVIVAL_TRADEOFF.** The single authorized counterfactual for
seed111101326 executed6 of13 frozen semantic skips, then died to the Automaton
on act2/floor33/fight16. Dark Embrace was acquired; Corruption and both Flashes
were not. Engine completion never occurred. The experiment stops here: no capture
replay, selected combat root, sampled world or infinity-oracle execution.

Starting #844 SHA: `5adfd78bfb32580ac49eca4a4c8f52498be08653`.
Frozen independently reviewed runtime/protocol SHA:
`06119a587009844c427339a1e5c93c60ca3998c8` (PASS, no blocking findings).
Final publication SHA is recorded in the #844 handoff; this report cannot contain
its own enclosing commit's hash. All changes are confined to experiment evidence,
the experiment ledger and current-research status. Current production C++ is
unchanged from the starting SHA.

## Runtime qualification

Historical source: `d8fd2a105a8d2a481b7639e26c683f75e382e3d4`.
The [historical research patch](historical-intervention.patch) adds one narrow
fixed-seed/13-entry manifest hook to a plain archived source snapshot. Its only
historical source changes are apps/one_combat/infinity_frozen_skips.h and the
run_driver.cpp dispatcher entry/summary calls. No new worktree or thread; original
read-only snapshot and original executable remain intact.

This is a **research-patched executable**, not the original historical executable:

- Patched binary SHA256: `2e6fe2ee357a85748d17ac33ee981da9b4efb013555f43d238da69f92e146d50`.
- Patch SHA256: `1b47c17ab7b3626389f8160e8ae1cf5388ab66a06d4d85b2cca5736f42f305de`.
- Original retained executable SHA256: `0e17e0f22259afe21f35ba89a0413f2af7663cfae1312311f1ea8c71b00c2d52`.
- Original13-entry manifest SHA256: `c98f1671a12ac41f7bee827f8f7428d4aedf628b10f2cedd9c14ec58f982754e`.

GCC13.3.0 Ubuntu13.3.0-6ubuntu2~24.04.1 / CMake4.4.2, historical
linux-gcc-release/linux-gcc-build, parallel4, Release/O3/DNDEBUG/OpenMP/LTO,
unchanged pinned submodules and eight model hashes. Exact compiler/linker flags
match the original reconstruction after source-path normalization.
[Build identity](build-result.json), [flags/libraries](build-details.json),
[raw build output](build.log), [raw configure output](configure.log.gz).
The historical Student C hash remains
eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509.

With STS_INFINITY_SKIP_MANIFEST unset, the hook returns before semantic enumeration
and emits no extra trace. Enabled matching uses seed/act/floor/exact canonical key,
never the old decision index. Only exact SKIP_CARD_REWARD/REWARDS actions execute
through the existing semantic executor; incomplete/ambiguous/failed actions abort.
Absent groups leave NOT_SEEN and the historical dispatcher acts normally. Each
entry executes at most once. The13 entries and protected-engine metadata are
unchanged; no engine, path, shop or survival choice is forced.

The one flag-off qualification passed the **full retained header +137 states
+136 traces**, with no comparator exclusions or first difference. It included
all retained gameplay/public fields through the Three Darklings fight and its
following state. It stopped intentionally at that bounded prefix, not a run-end
outcome. Wall400.039s; child CPU391.814s. No retries or configuration corrections.
[Receipt](parity.json), [retained states](parity.states.jsonl.gz),
[retained trace](parity.trace.jsonl.gz), [independent review](independent-review.json).
This qualifies the disabled patched runtime empirically; it does not claim that
the patched binary is hash-identical to the original.

## Actual treatment

Same reviewed executable, historical controller/environment, seed and eight
verified models; only the unchanged frozen manifest is enabled. One normal full
run through the repository seed guard, no retries or adaptive interventions.
Wall375.570s; child CPU364.788s. Simulator integrity passed. All131 emitted public
OOC states were supported. Final outcome: Heart not killed, floor33/act2/HP0.
The final battle entered with69/80HP,23 permanent cards and two Regen potions,
and lost to AUTOMATON. Mark of Pain remains a relic, not two permanent Wound cards.
[Execution receipt](treatment.json), [public OOC states](treatment.states.jsonl.gz),
[complete trace including intervention summary](treatment.trace.jsonl.gz),
[actual measurements and public-state examples](measurements.json).

Exactly13 =6 MATCHED_EXECUTED +7 NOT_SEEN; zero failed or duplicate executions.
All six executions left the existing deck unchanged while skipping that reward
addition. Actual treatment decision indices differ from historical audit indices.

| Actual decision | Act/floor | Permanent cards after skip | HP | Gold | Corruption / Dark Embrace / Flash count |
|---:|---|---:|---:|---:|---|
|1|1/0|11|68|99|0 / 0 / 0|
|3|1/1|11|62|99|0 / 0 / 0|
|61|2/20|19|41|224|0 / 0 / 0|
|70|2/22|19|24|335|0 / 0 / 0|
|77|2/24|19|44|355|0 / 0 / 0|
|93|2/27|20|26|122|0 / 0 / 0|

The [complete13-trigger table](TRIGGERS.md) is regenerated from the raw summary.
Seven groups were NOT_SEEN:

- Floor3: actual Pommel Strike/Bloodletting/Clash group, not the frozen Shockwave group.
- Floor10: Golden Shrine event; no reward group.
- Floor12: Hemokinesis/Ghostly Armor/Clash, not the frozen Reaper group.
- Floor16: Impervious/Exhume/Immolate, not the exact frozen Impervious group.
  The controller could still take Impervious naturally; matching was not a card-name blacklist.
- Floor29: Rampage/Dark Embrace/Headbutt, not the frozen Battle Trance group.
- Floor33: boss loss, so no post-boss reward group.
- Act3/floor36: never reached.

## Engine and route divergence

The first post-skip map decision already changed: historical decision2 chose
floor1 node(x5,y0); treatment decision2 chose(x1,y0). No path repair was applied.
The counterfactual floor7 was an EVENT rather than the historical Corruption
reward. Across all retained cards_offered.cards records, Corruption and Flash of
Steel were never offered and neither was acquired. There were no CARD_SELECT
steps in this counterfactual trace. This is not a case of observing a Corruption
or Flash offer and silently forcing/declining it for the experiment.

Dark Embrace appeared in the floor0 group skipped by the frozen intervention
(the historical action there was Headbutt). It appeared again on floor29;
MCTS naturally took it at actual decision104, trace/state index119. Final/max
ownership was Corruption0, Dark Embrace1, Flash0. The historical floor36
Sensory Stone Flash acquisitions were never reached. Full offer/public-state
identities and acquisition pre/post states are in measurements.json.

| Measurement | Historical qualified control | Actual treatment |
|---|---|---|
| Engine-bearing target | Act3/f37 Three Darklings | Never exists |
| Permanent deck at engine completion / target entry |31 /31|Unavailable / unavailable|
| Minimum active pool in that target fight |30|Unavailable; no engine-complete target|
| Last observed combat permanent deck |Not the comparison target|23, act2/f33 Automaton|
| Target public combat roots captured |Previous control evidence retained|0|
| Selected roots / sampled worlds |Not rerun|0 /0|
| Tier1 / active-pool diagnostic |Historical minimum30|Not measured|
| Oracle fractions / reach / node-cap rate |Not rerun|Null / null / null|

Do not call23 versus31 an eight-card engine-preserving reduction: these are
different floors/decks and the treatment lacks three required engine cards.
The optimistic31->18 accounting was not realized. No combat-active-pool size is
inferred from permanent deck size. [Oracle matrix/stopping status](MATRIX.md).

## Interpretation and stop

**COMPRESSION_SURVIVAL_TRADEOFF** is supported for this one intervention on this
one historical seed: naturally reacting to the frozen skips changed the route,
failed to reproduce the engine acquisitions and died before the control's target
region. This does not isolate which particular skip caused the loss, estimate a
win-rate effect, or prove that aggressive skipping is generally bad. The nominal
13-skip projection overstates the enacted treatment: only six exact groups recurred.

OOC_COMPRESSION_LEVER_ESTABLISHED is not established: no engine-bearing combat
compression measurement exists. NATURAL_NEAR_INFINITY_ESTABLISHED and
NATURAL_POSITIVE_ESTABLISHED are not established: no oracle was executed. This is
not NONE, a negative infinity label, an oracle-recall failure, or proof of no
possible loop on a different trajectory. The archived unsupported roots and
prior conclusions remain unchanged.

No capture-only replay, other skip set, removal arm, other seed/lead, beam search,
model/reward/AZ/Silver/default change or #844 merge. This result alone does not
pass the beam-search gate: engine-preserving actual compression is still missing.
Stop after this experiment; no automatic next study.

## Verification and limitations

Focused hook tests: five seed-free instrumented semantic-API contract groups PASS;
these are not substitute simulator integration tests. Exact flag-off prefix parity
is the real integration qualification. Raw archived bytes/receipts, frozen manifest,
all trigger accounting and generated result/tables validate with analyze.py --check.
Current production C++/oracle/models are unchanged; existing adapter binary hash
remains28e942c218cbaeef29f3a58a3301873d2fca012f6205379445e4e23ffef0ebe9.

An offline reporting parser initially assumed every offer.cards row was a reward
group; shops use [name,price] rows. measure.py was corrected to handle both explicit
layouts and regenerate from unchanged raw evidence. No executable, comparator,
manifest, run configuration or result changed, and no seed was rerun. Review hashes
identify the pre-run committed measurement script; final evidence gets a separate
light delta review. Initial whitespace-only packaging failures were repaired by
retaining raw configure bytes as gzip and storing a zero-context equivalent patch.

Repository/ledger/diff checks and independent review outcomes are recorded in
verification.txt and review artifacts. GitHub Actions account-level billing/start
failures remain separate from implementation; no manual CI redispatch or CI-pass
claim. Knowledge impact: experimental evidence and current research stopping point;
no production behavior or default promotion.
