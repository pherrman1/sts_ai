# Prior vs search at OOC roots: result (#882, 2026-10-28)

Rules: [PREREG.md](PREREG.md) (frozen at `fe7eed5`, the treasure drop at `b93d4d3` before launch). Analysis:
`python3 -I analyze.py /mnt/project-files/ooc-prior-vs-search-882/forks/units /mnt/project-files/ooc-map-only-search/units`
→ [analysis.json](analysis.json). Diagnostic only: no training, no default change.

## Run

- 26 roots × 16 salts = 416 units, 832 games; RUN_COMMIT `b93d4d3`, code `b225220d`, binary `4dfc84d9…` (independent
  clean build matched), student_sel `cf6bf7fb…`; replays of the used §683 MAP seeds 111374100–115, no new seeds.
  16 cloud workers (15 delivered), first unit 11:31Z, last 15:27Z 2026-10-28. Pre-launch review PASS after the drop of the 2 unforceable treasure roots
  (`/mnt/project-files/reviews/ooc-prior-vs-search-882-prelaunch.md`).
- `tools/cloud/verify_campaign.py`: 416/416 units OK, 0 missing, 0 bad, 0 duplicates, one run commit. analyze.py:
  416 valid pairs, 0 invalid games (every game equals its §683 game up to the root; every A root row is
  `by=forced_decision`).

## Result (Heart kill, A = alternative − B = production, mean over roots, 95% two-stage bootstrap CI)

| group | roots | Heart Δ pp | Act 4 Δ pp |
|---|---:|---|---|
| all disagreement roots | 26 | −1.9 [−7.9, +3.8] | −1.0 [−7.2, +5.0] |
| search_departs (PUCT 4096 or 32768 leaves production) | 13 | +1.4 [−5.3, +8.7] | +1.4 [−7.7, +10.1] |
| leaf_only (only the uniform leaf reference disagrees) | 13 | −5.3 [−14.4, +2.9] | −3.4 [−11.5, +4.8] |
| boss relic | 4 | −4.7 [−26.6, +15.6] | −3.1 [−15.6, +7.8] |
| card select | 4 | −7.8 [−23.4, +7.8] | −4.7 [−20.3, +6.3] |
| event | 3 | −2.1 [−16.7, +14.6] | 0.0 [−16.7, +16.7] |
| map | 3 | +2.1 [0.0, +8.3] | +2.1 [−4.2, +12.5] |
| rest | 4 | +4.7 [−4.7, +14.1] | +14.1 [+1.6, +28.1] |
| rewards | 3 | −4.2 [−18.8, +10.4] | −10.4 [−27.1, +6.3] |
| shop | 5 | −1.3 [−13.8, +10.0] | −5.0 [−21.3, +11.3] |

Base Heart rate of the production arm over these roots: 26.0%. Correlation of the leaf reference's gap with the
real Heart difference across roots: r = −0.10 (the leaf's margin does not predict which roots gain).

## Classification (PREREG rules)

- **search beneficial:** not shown for any group (no lower CI bound > 0 on the primary). search_departs +1.4 pp
  [−5.3, +8.7].
- **search/exploration constrained:** not shown. The alternatives the leaf prefers but search does not take
  (leaf_only) are, if anything, worse: −5.3 pp [−14.4, +2.9].
- **value/leaf limited:** the leaf's own preferences are not better in real play (leaf_only point ≤ 0, leaf gap vs
  outcome r = −0.10), but where search follows the leaf with budget (11 of 16 deep departures go to the leaf's best)
  the point is slightly positive, so the rule is not met cleanly.
- **prior near-ceiling:** not met formally (all-roots upper bound +3.8 pp > +3 pp), but the point is negative and,
  with phase 0 (searched non-map screens D vs MAP −0.3 pp [−4.3, +3.5], 631 seeds, §683 data), every measurement
  of search vs prior outside map roots is within ±4 pp of zero.
- **per type:** all **inconclusive** (2–5 roots each, CIs ±10–20 pp). Rest is the only type whose secondary endpoint
  clears zero (Act 4 +14.1 pp [+1.6, +28.1], 4 roots, one of 18 tests); map's Heart lower bound is exactly 0.

Overall reading: at the roots where search or its leaf most clearly disagree with the student_sel prior, forcing the
alternative does not win more Hearts; the evidence points to the prior being at or near what this leaf can
distinguish (median leaf gap 0.022 next to a median per-root real-play SE of 0.09), not to search being starved of exploration.

## Counterexamples (per root, 16 paired salts; none is significant after 26 comparisons)

Largest gains for the alternative: 111374102/118 boss relic Busted Crown → Velvet Choker +12.5 pp (SE 20.2);
111374115/175 rest Rest → Smith Metallicize +12.5 (SE 8.5); 111374112/79 card select Feel No Pain → Shrug It Off
+12.5 (SE 8.5). Largest losses: 111374107/124 boss relic Slavers Collar → Velvet Choker −31.3 (SE 17.6);
111374102/143 card select (rest-site upgrade) Perfected Strike → Shockwave −25.0 (SE 11.2); 111374100/73 duplicate Apotheosis → Impervious
−12.5 (SE 12.5). Per-root rows with labels, base rates and SEs: [analysis.json](analysis.json).

## Not covered

Treasure roots (key rule decides them; not forceable), Act 4, roots where all three searches agree with production,
budgets above 32768, other leaves. Per-type power is low by design; the pooled groups carry the conclusion.
