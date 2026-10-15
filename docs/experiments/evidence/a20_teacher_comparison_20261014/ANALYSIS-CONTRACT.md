# A20 teacher pilot analysis contract

Preimplementation contract, 2026-10-14. No scientific data have been collected
for this pilot. The controlling design is `PROTOCOL.md` in the matching
committed evidence directory. The analyzer uses only the frozen four-source
panel, or the separately flagged excluded canary. It never launches a game.

## Validity and output

CLI: `python3 tools/analyze_a20_teachers.py OUT.json FREEZE.json PREFIX...`.
`--canary` requires exactly the frozen canary prefix/seed. Without it, exactly
all four frozen cohort prefixes/seeds are required. Output is created
exclusively: an existing output is never replaced. A failed analysis preserves
an `INVALID_OR_INSUFFICIENT` report with the reason and available custody;
partial evidence never receives comparison summaries. Success is
`CANARY_VALID` for the excluded canary, or
`DESCRIPTIVE_COMPARISON_MEASURED` for the cohort. Every included source must
have at least one supported matched state. No winner or promotion label exists.

The report contains schema/version, status, reasons, frozen/input hashes,
coverage (captured, selected, supported, excluded reasons and source counts),
per-state metrics, per-source means, equal-source means, pooled-state means,
and per-job/total execution cost. Aggregation names state their denominator.
The canary is never pooled with the cohort. JSON numbers must be finite.

The freeze binds source, binary, all model/teacher/configuration artifacts,
producer/analyzer/runner/protocol and seed guard hashes, full environment,
arms, seed lists, resource caps and exact output paths. Each runtime manifest
and runner receipt must agree. CSV output hashes must match each manifest.
Unknown schema fields/arms/states, duplicate JSON keys/CSV headers/row keys,
missing files/rows, nonfinite or malformed values, failed jobs, excess resource
use, source invalidity, source/control mismatch, wrong seed derivation, or
incorrect counts invalidate the whole panel. Source deaths are valid outcomes.

For each selected state, exactly one original `source` RAW sample is required.
For each supported state require a single original-future `control`, 32 CTM
samples and four samples for each of plain2k/prior2k/plain10k/prior10k, with
matching arm rows. Control RAW fields must equal the source RAW sample and
explicit source RAW fields; the producer also requires full persistent-state
JSON replay equality. Battle-end `terminalHp` and post-callback `sourcePostHp`
are diagnostics and never substitute for RAW HP. Unsupported CTM states consume
their original slot and require a reason and source sample, but no treatment or
control rows. There is no selective exclusion of invalid controls or deaths.

The first six eligible chronological slot selections and manifest accounting
are checked against the complete captured entry metadata. Any missing later
slots stay missing. Source-to-source state counts can differ. Candidate redraw
and planner seeds must equal the producer's documented salted derivation and
be shared across the four candidate arms for each state/replicate. In the
A20-only `teacher_a20_native_init_v1` kernel, the first MT19937-64 draw sets a
detached battle seed and the next six draws reseed GC combat streams. Ordinary
combat initialization derives its four correlated streams from battle seed
plus floor, resetting their counters; misc/potion retain redrawn GC streams.
Colosseum continuation retains all six redrawn GC streams and their counters.
The analyzer independently checks the serialized battle seed against the first
standard MT19937-64 draw. Native mechanism tests check initialized streams.
This intentionally supersedes the older kernel that lost four redrawn GC
streams during ordinary initialization; old A0 evidence is not rewritten.
The original
control retains original source RNG. No redraw is reused as its own reference.

## Forecast metrics

Reference for each state is the original-future plain10k control. Death target
`d` is 1 exactly for `DEATH`. RAW HP target `y` is 0 on death, otherwise the
RAW persistent `curHp`, including combat-end healing. Escapes remain explicit
outcomes and are not silently converted to victory or dropped.

CTM prediction is its analytic death probability `p` and expected RAW HP `h`.
Silver prediction is the four-draw death fraction and mean death-zero RAW HP.
For each forecaster report death Brier `(p-d)^2`, signed death error `p-d`,
HP squared error `(h-y)^2`, signed HP error `h-y`, and absolute HP error.
Descriptive RMSE is the square root of the corresponding aggregated squared
error; do not average state RMSE as if it were pooled RMSE.

For CTM32 and Silver4 empirical persistent-state forecasts, categorical
plug-in Brier is `1 - 2*p(reference) + sum_v p(v)^2`; report reference match
probability too. Fields are outcome, maxHp, gold, potion slots plus count,
relics, deckHash, smokeBombUsed, stolenGold and their non-HP joint tuple.
On death every resource field is a separate structural DEATH sentinel.
Tuples prevent delimiter collisions. This scores the actual finite-sample
forecast; no unbiased infinite-draw correction or equal-K claim is made.

## Controller contrasts, repeat variance and cost

Separate paired controller contrasts are prior2k-minus-plain2k,
prior10k-minus-plain10k, plain10k-minus-plain2k, and
prior10k-minus-prior2k. Pair by state and replicate. Report mean paired change
in death indicator, RAW HP, retained potion count (HP and potions zero on
death), escape indicator and CPU seconds. No composite fight-score winner.

Within each state/forecaster report sample variance (denominator K-1), SD and
range of sampled death, death-zero RAW HP, retained potions and escape. CTM
variance uses its 32 draws; Silver variance uses its four draws. For paired
contrasts report sample variance of the four paired differences. These are
conditional draw dispersion, not between-source uncertainty or confidence
intervals for population performance.

Silver costs: total CPU for four draws, average CPU per fight, total decisions
and simulations, and CPU per decision (sum CPU / sum decisions; null if zero).
CTM costs: measured analytic expectation CPU and single prepare/sample CPU,
both converted from microseconds to seconds. Keep sample timing separate from
the empirical 32-sample distribution count. Zero denominators produce null,
never infinity. Report reference-control and overall job costs separately.

The existing Silver arm timer covers `playoutBattle` only. It excludes
`exitBattle`, RAW-state copying and continuation/callback work. CTM expectation
timing includes input capture plus expectation; sample timing includes input
capture, prepare and one draw. The report labels these scopes and does not
claim an exact end-to-end CTM/Silver CPU ratio. Runner process CPU includes
all source and evaluation overhead.

Means first average states within each source, then average the four source
means equally. Also provide pooled-state means and per-source outputs with
their counts. Cost per decision uses the ratio of corresponding total CPU and
decisions within each scope, and equal-source means average source ratios.
No confidence intervals, bootstraps, significance tests, adaptive extensions,
training, default change or model qualification are authorized by this report.

## Interpretation limits

The behavioral reference is a plain10k controller, not optimal play or ground
truth. The CTM was trained for a particular controller; changing prior/budget
can improve outcomes while increasing disagreement with that reference.
Four source clusters and at most 24 deliberately selected trajectory fights
cannot establish public-input sufficiency, OOC sibling ranking, rare-event
calibration, a best budget or student-learning value. Shared redraws support
paired controller comparisons only; policies may diverge after the first
action. The panel conditions on inherited hidden state and is not a universal
public-state expectation.
