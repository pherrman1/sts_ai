# Active Lizard Tail paired rescue pilot

**Decision: `PILOT_INCONCLUSIVE_NO_MODEL_CHANGE`.** This 32-pair descriptive
screen tests whether ordinary CTM death probability can stand in for active
Tail consumption, and whether the existing conditional transition heads look
usable after Tail-consumed wins. It does not train a rescue head, qualify CTM
support, or authorize runtime integration.

## Collection and provenance

The cohort contains one paired no-Tail/active-Tail combat for each source seed
`4200100..4200131`. Rows were validated by
`tools/combat_transition_lizard_pair_pilot.py` against the aggregate manifest.
The producer is `d6674ee4ef66ee5fc214e528be4e42077151c0dd`, executable SHA-256
`ddd63f3b7cd74949b23740638c7c718634466a1904586a6e873e443dc74f9838`. The
frozen teacher is
`silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77`; its
artifacts, fair-RNG regime, Silver configuration, per-seed membership, and
component row hashes are recorded in `manifest.json` and `provenance.json`.
The exact paired JSONL SHA-256 is
`c7e55552ae2329d85dee6d486bdaa266702f1cb122e615273cebb7daccfe41a3`.

The first serial attempt was stopped after its first row for throughput; that
row was preserved and the remaining seeds were completed as individually
guarded runs. One earlier row, seed `4200100`, had no per-seed sidecar manifest;
the aggregate provenance binds its bytes and records its same-argument guarded
batch origin. All 32 rows passed strict aggregate validation, all 31 individual
manifests were checked against the shared teacher/provenance, and the seven
seeds that had exposed the invalid reward action all completed after the
collector fix.

The invalid action was a potion-reward `CHOOSE` while all three potion slots
were full. The paired source-reward branch in `apps/one_combat.cpp` had omitted
the full-inventory guard used by the normal reward policy. Adding that guard
made the source path skip the impossible potion pick. This repairs collection
correctness; it is not evidence about Tail modeling.

## Results

| Paired outcome | Count |
| --- | ---: |
| Ordinary win; active Tail retained | 30 |
| Ordinary death; active treatment won and consumed Tail | 1 |
| Ordinary death; active treatment won and retained Tail | 1 |

The ordinary CTM predicted mean death probability was `0.05704`, against an
observed no-Tail death rate of `0.0625` (Brier `0.01474`). Active treatment
consumed Tail once (`0.03125` of pairs); comparing the same death probabilities
to consumption labels gives Brier `0.03182`. With only two ordinary deaths,
these are descriptive diagnostics and cannot establish calibration or a
predictive advantage.

Both ordinary-death pairs won under the active-Tail treatment, but only one
consumed Tail. In seed `4200105`, Tail was consumed; in `4200129`, Tail remained
available. This shows that merely adding Tail can alter the policy's combat
behavior, so Tail consumption is not a direct proxy for the paired no-Tail
counterfactual. The two cases do not estimate a useful rescue rate.

Only one row was available for the existing conditional-head screen after a
Tail-consumed win. That row is not enough to assess HP, potion, or other
post-combat predictions. No extra-effective-HP scalar, rescue head, or
specialist was trained.

## Commands and limits

The aggregate was checked with:

```text
PYTHONPATH=. python3 tools/combat_transition_lizard_pair_pilot.py \
  --manifest /tmp/lizard-tail-paired-4200100-32-fixed-aggregate.jsonl.manifest.json \
  --output /tmp/lizard-tail-paired-4200100-32-fixed-aggregate.analysis.json
```

The analysis JSON is preserved in `analysis.json`. The pilot used 32 source
seeds, under the 128-source local cap. It is not the 111-source failed-head
qualification cohort described in ledger §338, and it does not reverse that
cohort's proper-score rejection or the `active_unqualified_lizard` guard.

**Knowledge impact:** exploratory paired evidence only; no model, support
metadata, runtime behavior, or default changed.
