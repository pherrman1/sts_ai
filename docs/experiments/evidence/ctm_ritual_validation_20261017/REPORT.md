# Current A0 Ritual validation diagnostic

At reviewed source `f2d0dbd30b3667a847d3b92332a110baded509b6`, the single frozen
32-draw diagnostic completed with exit 0 in 4.135 seconds. Peak GPU allocation
was 14,107,648 bytes; peak RSS was 1,014,046,720 bytes. All 143 selected
VALIDATION rows from 68 source groups passed the ordinary public predicates.
Routing used the actual fast artifact for 142 rows and the standard artifact
for one initial-Brew row. There were no active-Tail or generated-escape cases.

| Component score | Value |
|---|---:|
| Conditional teacher NLL | 0.0033221452176290895 |
| Ancestral mixture NLL | 0.003305526033288567 |
| Mean exposure gap | -0.00001661918434052221 |
| Source-bootstrap 95% interval | [-0.00013898656525652327, 0.00010269314778911387] |
| Zero teacher / mixture masses | 0 / 0 |

Classification: `CURRENT_CHILD_RITUAL_VALIDATION_DIAGNOSTIC`. No model or
support qualification follows from it. An independent reviewer recomputed the
scores and 1,000-repetition source bootstrap exactly from preserved row masses.

## Coverage limits and next question

Every observed VALIDATION Dagger increment was zero. The current children
assign high probability to that outcome, but this cohort does not test positive
Ritual growth. It also provides only one standard-fallback row, one Dagger per
row and no active-Tail coverage. No fitting intervention is justified by these
negative-outcome scores alone.

A label-only census of preserved TRAIN/VALIDATION intersection rows found
1,095 TRAIN rows from 458 sources, with only three positive increments (all
+5), and 143 VALIDATION rows with none. TRAIN includes 82 two-Dagger rows;
VALIDATION has no two-Dagger rows. All 1,238 saved targets match independently
recomputed native pre/post deck changes. This is a coverage diagnosis, not
new model inference or TEST evidence.

## Producer defects reproduced and repaired

A deterministic legal-action fixture confirmed that ordinary final Ritual
kills lost permanent growth: Cultist and Writhing Mass, base/upgraded, retained
15 instead of 18/20. The queued card had not returned to a pile when combat
ended, and the exit copier omitted it. Transfer now includes that card with
physical master-deck identity checks and a monotonic merge. Generated cards
remain isolated, including a generated Dagger whose ID is later occupied by
the Parasite appended after Implant. Stale queue history cannot lower newer
growth.

A second fixture confirmed that nonfinal Darklings and the Awakened One's
first phase incorrectly earned +3/+5. Vanilla excludes half-dead targets;
the simulator now tests that flag instead of the cleared Regrow power.
Python/native candidate closure likewise allows only three eligible kills in
the Awakened encounter, shared between Ritual Dagger and Hand of Greed.

All 14 persistence and 12 eligibility cases pass. The two final Awakened
controls traverse its real rebirth before confirming eligible +3/+5. Four final-hit cases also
capture the real RAW observer and production state serialization, asserting
18/20 before screen continuation. Ten affected CTests pass; paired
Python/native closure tests cover the corrected shared kill budget. Independent
agents reviewed persistence, eligibility and candidate closure with no findings.

Old RAW rows have no action/kill history or terminal card identity. An unchanged
Dagger may mean no kill or lost growth, and later pre-states and teacher
choices also depended on the old damage. Preserve the old rows; they cannot
be repaired reliably by incrementing their labels. Corrected-source collection
is needed before affected Ritual growth qualification can be renewed. Neither
this source repair nor the all-zero diagnostic qualifies the existing models.

The superseded 12-to-60-epoch warm-start proposal was not executed. Tensor
custody showed that it targeted neither deployed head. No fitting, new collection seeds, TEST numerical access, capability promotion
or deployment occurred in this diagnostic. Deterministic source regressions
use their fixed test seed through the seed guard.

## Evidence

- [Protocol](PROTOCOL.md), [custody](custody.json), [review](review.json),
  [freeze](freeze.json), [commands](commands.json).
- [Raw result](result.json), [stdout/stderr](run.log),
  [TRAIN/VALIDATION census](train-validation-growth-census.json),
  [native loader parity](native-parity-summary.json),
  [producer repair receipt](producer-repair.json).
- Persistent detailed row masses and sanitized input records remain in
  `build/ctm-ritual-validation-20261017-current/`, with hashes in the freeze and
  result receipts. The original archive is unchanged.

Knowledge impact: current model custody and limits of the available growth
coverage; no qualified baseline/default change.
