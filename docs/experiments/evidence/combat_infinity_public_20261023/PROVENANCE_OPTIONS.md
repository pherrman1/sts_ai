# Cheapest next natural-root provenance sample

Read-only investigation, 2026-10-24. No oracle execution, world sampling, new
capture, model work or experimental verdict change. Source schema inspection
uses the #844 source tree (substantive reviewed SHA
`40d10995a57e5159a2b5d9d48917aa4280635237`); capture producer semantics are also
checked at the exact historical source below. This supplements the pilot; it
does not replace its frozen roots.

## Existing schema answers

| Question | Repository evidence | Consequence |
|---|---|---|
| Does current AZ/self-play retain full relic provenance? | `heart1_policy.cpp::encodeObservation` iterates `gc.relics.relics`; serialized `obs.relics.relics` retains all IDs. `heart_outcome_capture.cpp` ties real-run state/decision rows to a producer header and `stateIndex`. `tools/heart1/az_targets.py::convert_run` retains those records. | The OOC AZ records can establish the inventory at their own boundary, with a pinned producer/enum and complete-run identity. They do not contain an in-combat public wire. No arbitrary seed/floor-only join is justified. |
| Do all combat capture formats retain it? | `SilverRunContext` contains act/Omamori only. Combat Player/BattleStateWire carry relicBits0/1, omitting Shard. `silver_synth_gen.cpp::SynthSink` writes combat roots with that wire; its manifest supplies producer custody, not missing per-root relics. | The older SilverAZ combat-root format alone cannot establish no-Shard. Do not confuse it with the current OOC AZ records. |
| Is an existing exact-run join available? | The retained `Capture_0` receipt binds the public trace, full OOC trace, metadata, manifest and executable. Its unique Champ battle has a complete pre/post relic inventory. | Yes, a historical development sample is available without collection or a capture patch. Details below. |
| Can the current producer expose this already? | `STS_OOC_DECISION_TRACE` serializes every owned run relic via `oocTraceState`; `STS_SILVER_PUBLIC_TRACE` with `STS_SILVER_PUBLIC_TARGET=SEED:FLOOR` captures the public combat wire. Both work in the same run driver. Optional Heart CTM rows also retain full prebattle relics through `captureCombatPredictorInput`, but are not combat roots themselves. | Existing paired opt-in capture paths suffice. A new field is unnecessary for this first sample. |

This is a bounded local inventory and source-schema audit. Remote current AZ
corpora under `/mnt/project-files` were unavailable here; no claim is made that
all extant remote artifacts were searched or that current-policy combat roots
with this join already exist there.

## Verified retained pair

The archive is outside Git in the retained app worktree:

```
/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/build/overnight_20261008/corrected_canary
```

[provenance-inventory.json](provenance-inventory.json) retains exact file paths,
SHA256s, sizes, join identity and public relic inventory. The receipt's status is
completed/exit 0. Actual hashes match its public trace, OOC trace and run metadata
entries; the protocol manifest and executable match their receipt hashes too.
Historical producer `3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0` explicitly serializes
**all** `gc.relics.relics` into the OOC trace, takes `pre` before combat and emits
it with `post` after combat. Its public sink gates the same seed and floor and
uses the legitimate public conversion with isolated diagnostic seed zero.

The unique join is seed **610081002**, act **2**, floor **33**, encounter
**CHAMP**, fight **13**; OOC trace line **123** (1 based). Full pre/post relic
inventories agree:

```
BURNING_BLOOD, BAG_OF_PREPARATION, MAW_BANK, LANTERN, GINGER,
SELF_FORMING_CLAY, ECTOPLASM, ENCHIRIDION, GIRYA, NLOTHS_GIFT
```

There is no Prismatic Shard. This is complete owned-run inventory evidence,
not an inference from card colors, floor, combat bitsets or a different run with
the same seed. Relic acquisition does not occur inside this Champ encounter;
the matching inventories bracket its public decisions. No outcome is used to
select among the roots.

All **72** public records are valid and match that identity and Ironclad/A0.
**65** satisfy the basic normal-input, visible-intent, information-set draw
checks. A deterministic proposal is the first 16 of those in file order:

```
1, 2, 3, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20
```

These are provenance-backed candidate inputs, **not 16 demonstrated
oracle-eligible or annotated roots**. The ordinary hydration, audited-card,
quiet-boundary and other support checks must still run and fail closed. The
archive has one old A0 encounter under an older policy, with highly correlated
roots; it cannot estimate current-policy prevalence or natural recall.

## Next bounded decision

The cheapest useful next step is a separately frozen offline feasibility pilot:
extract only the public wires for those first 16 decisions, bind each to this
receipt/inventory proof, and use K=4 (at most 64 worlds), retaining the current
per-world caps. Do not carry the real run's hidden draw order or RNG into
sampling. Record unsupported roots explicitly and do not replace them based on
oracle results. Compare disagreement, runtime/cap hits and inspect any witness.
This audit has extracted no oracle inputs, set no eligibility assertions and
annotated **zero** worlds. It does not authorize a larger sample or model work.

For a sample under the **current** policy, co-emit the existing full OOC trace
and targeted public combat trace from one nominated run/fight, with the normal
seed-guard protocol and receipt. Retain 8–16 consecutive supported public roots;
no large cohort is needed. That collection has not been launched. Prefer the
existing archive for the first development check, then decide whether freshness
is necessary; implementation success and natural usefulness remain separate.

No producer patch is genuinely needed now. If paired-file custody later proves
operationally inadequate, the smallest capture-only proposal is to append a
complete public `run_relic_ids` inventory plus a version/completeness marker to
`NativeSilverBackend.cpp::tracePublicAction`, using the already available `gc`
under the existing default-off trace gate. Bind it to the producer/receipt and
validate against `gc.relics.relics`; do not add a model field or change gameplay.
This fallback is proposed only and was not implemented.

## Reproduction and unchanged pilot

```sh
python3 docs/experiments/evidence/combat_infinity_public_20261023/inspect_provenance.py --check
```

The read-only audit needs the retained archive, its receipt-referenced manifest
and binary, and the historical Git object. It fails if any are unavailable or
mismatch. It never runs the binary, samples a world or creates annotation input.
Its committed inventory permits inspection elsewhere, but does not substitute
for custody verification before using the external roots.

The original four native8 pilot roots remain **UNSUPPORTED**, with **0 eligible
natural roots**, **0 annotated natural worlds**, and null certified/candidate
fractions. Their missing provenance has not been repaired by finding this
different archive. `RESULT.json` and the original scientific verdict remain
unchanged: natural annotation in that pilot is BLOCKED.

Knowledge impact: a verified existing provenance route and its limits are now
recorded in the maintained research status. No new experiment ledger entry is
needed because this was artifact/source inspection, not a new run.
