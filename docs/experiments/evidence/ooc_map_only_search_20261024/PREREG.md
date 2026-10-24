# Map-only OOC search screen at A20 (#854): default vs search only at map roots vs no search (pre-registration)

Written 2026-10-24 before any campaign game ran. Origin: the OOC direction review of 2026-10-24
(`/mnt/project-files/ooc-direction-review/REPORT.html`), experiment 1; Philipp, 2026-10-24 18:28Z: "lets start with 1
and open for 2 and 3 and issue each in github". Issue #854.

**Authorization:** Philipp, 2026-10-24 18:56Z: "lets go, 32 workers." 1,024 paired A20 seeds × 3 arms on 32 cloud
workers. The independent pre-launch review (reviewer J) runs in parallel; a blocking finding stops the campaign.

## Question
The review found that gen-0's whole search gain (§569, +40 kills on 1,664 pairs) sits in pairs whose first divergence
was an OOC MCTS **map** override (629 seeds, +49 kills, +78 Act-4 arrivals), almost all in act 1, while pairs whose
first divergence was a non-map override lost (764 seeds, −13 kills). Today's default (fast-root cap 1024, M0 leaf
calibration) overrides act-1 map choices about 4x less often than gen 0 did (fast 2.3% / full 5.7% vs 9.7% / 9.2%).
Two questions:
1. Does map search, run at the full budget, beat no search at all (MAP − OFF)? This is the direct test of "the useful
   part of search is the route".
2. Does today's default get anything from searching the other screens (D − MAP)? If not, the non-map search can go,
   and the CPU it costs can fund the map roots.

## Arms (`run_unit.sh` is the source of truth)
Only `STS_OOC_MCTS_SCREENS` and `STS_OOC_MCTS_FULL_BUDGET_FRACTION` differ. Everything else is today's A20 OOC default
as frozen for the #853 control arm, minus that pilot's value-head leaf: student_sel tree prior and rollout policy
(`cf6bf7fb…`), rollout3 + X2-B leaf with the default M0 calibration (ADR-0057; nothing set, banner must show it),
tree rules, learned OOC stop 0.99, fast-root cap 1024, learned Silver stop with exact root budgets for real combats,
g7f_E root table and prior, boss-only prior playouts, keys on, the default CTM (§679), CTM rows on.
- **D (control):** today's default; `SCREENS` unset; 25% full-budget roots.
- **MAP:** `STS_OOC_MCTS_SCREENS=map`, `STS_OOC_MCTS_FULL_BUDGET_FRACTION=1`: OOC MCTS only at map roots, every one of
  them at the full 4096-simulation budget (no fast root, so the 1024 cap never applies). Every other screen: the same
  rule chain as D (key, tree, relic, chest, rest/shop rules, match-and-keep), then student_sel's argmax.
- **OFF:** `STS_OOC_MCTS_SCREENS=none`: the same rule chain, then student_sel's argmax everywhere. No OOC search.

## Implementation (research option, default unchanged)
`STS_OOC_MCTS_SCREENS` (`apps/one_combat/ooc_mcts_adapter.cpp`): `all` or unset = default; `none`; or a comma list of
`map,event,rewards,boss_relic,card_select,treasure,rest,shop`. Requires the heart1 prior (the excluded screens are
decided by `heart1::policyStep` directly, which also covers the card-select screens that the `heart1full` fallback
excludes); refused in the live advisor and without OOC MCTS. In `realOocChainStep` the filter acts after the whole rule
chain and before the MCTS step, so the rules decide exactly the same screens in all arms; such decisions record
`by=heart1_screen`. If student_sel has no answer on an excluded screen, the old chain continues (MCTS); the analysis
counts these (`search.decisions`, expected zero or near zero).

Pre-launch checks (results in `SMOKE.md`):
- Unset and `SCREENS=all` reproduce main `61a536fe` (same game record on a smoke seed).
- MAP: every `by=mcts` decision is on a map screen; OFF: no `by=mcts` decision.
- Banner shows `screens=` exactly as set; bad values are refused.

## Seeds and scale
- Campaign: **111374100–111375123** (1,024 seeds, in the free block 111370020–111379989 of the seed ledger; repo seed
  guard clean). One unit = one seed with D, MAP, OFF in sequence (order rotated by seed % 3) on one lane.
- Extension (only if the rule says EXTEND): **111376000–111377023** (another 1,024, same block).
- Smokes: 111375990–111375999.
- Cost (smoke seed 111375990, 4 lanes busy): D 689 s, MAP 647 s, OFF 216 s -> ~26 min per unit, ~450 core-hours for
  1,024 units; on 32 workers × 4 lanes ~3.5 h wall plus a straggler tail. MAP costs about as much as D because every
  map root runs the full budget.

## Endpoints
- **Primary:** Act-4 arrival, MAP − OFF, paired: exact discordance counts (exact McNemar p) and a 95% seed-bootstrap
  CI of the paired difference. Act-4 arrival rather than kills because the gen-0 map gain shows twice as clearly there
  (+78 vs +49) and the review's mechanism is "better route -> more arrivals".
- **Guard:** Heart kills, D − MAP.
- **Secondary:** Heart kills and Act-4 for MAP − OFF, D − MAP, D − OFF; kills per Act-4 arrival; mean final floor;
  deaths by act; mean wall per arm and the wall ratios.
- **Mechanism:** first-divergence attribution per contrast (act, screen, deciders of the decision before the first
  differing state row) with Act-4 and kill deltas per class, as in the review.
- **Search:** decisions by decider × screen, searched roots per screen, share of picks off the prior argmax per screen.

## Decision rule (frozen)
- **PASS:** MAP − OFF Act-4 ≥ +2.5 pp with the 95% CI above 0, **and** D − MAP Heart kills ≤ +1.0 pp. Meaning: route
  search is the useful part and the non-map search adds nothing measurable. Follow-up: a separate PR proposing MAP as
  a candidate default at matched CPU (paired A20 A/B, the AZ-loop rule), and spend the saved CPU on map roots.
- **FAIL:** MAP − OFF Act-4 ≤ 0. Meaning: today's map search does not carry the gen-0 gain. Follow-up: ledger entry;
  stop tuning OOC search and move to the teacher (#855, #856).
- **Otherwise EXTEND** once to 2,048 seeds with the extension block, same rule; after that NOT_SHOWN.
- Recommendation will be one of PASS (MAP candidate), FAIL (stop search work), NOT_SHOWN.
- A PASS on the primary with D − MAP Heart > +1.0 pp is reported as "map search helps, other screens also help":
  no default change from this screen.

## Known limitations
- Equal CPU is not required here and MAP is about as expensive as D (smoke: 0.94x wall), so this screen says where
  the gain sits, not that MAP saves CPU; a MAP default would need its own matched-CPU A/B. The wall ratios are reported.
- 1,024 seeds resolve about ±2.5 pp on Act-4 arrival (paired); this is a screen, not a qualification.
- MAP keeps D's search budget per map root at 4096 with the learned stop; the stop was trained on all screens.
- The gen-0 attribution is observational (first-divergence classes are not randomized); this screen is the
  randomized test of it.
