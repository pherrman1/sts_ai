# Map-only OOC search screen at A20 (#854): result (2026-10-24)

Campaign `ooc-map-only-search`, RUN_COMMIT `772df240`, code `a2968186`, binary `6c7747a9…` (x86-64-v3), base main
`61a536fe` (before #852, so Act 4 is played with the learned Silver stop; see the PREREG addendum). 1,024 paired seeds
111374100–111375123 on 32 cloud workers (19:08Z–22:05Z). `verify.txt`: 1,024/1,024 units OK, 0 missing, 0 bad,
0 duplicates, 32/32 worker DONE files, one run commit. Pre-launch review PASS (reviewer J,
`/mnt/project-files/reviews/pr857-prelaunch-review.md`). Tar hashes in `tars.sha256`; `analyze.py` output in
`result.json`.

**Dropped or timed-out seeds per arm:** none. All 3,072 arm runs ended rc 0 with a complete, integrity-passed game
record (D 0, MAP 0, OFF 0 dropped; no rc 124).

Arm names, as run: **D** = today's A20 OOC default (MCTS at every searched root); **MAP** = OOC MCTS only at map roots,
every one at the full 4096-simulation budget; **OFF** = *student_sel behind the rule chain*: no OOC search, but the
key, tree, relic and chest rules, the rest/shop rules and match-and-keep still decide first, then student_sel's argmax
(so OFF is not §569's plain student_sel arm).

## Primary and guard
| | D | MAP | OFF |
|---|---|---|---|
| reached Act 4 | 428 / 1,024 (41.8%) | **441 (43.1%)** | 392 (38.3%) |
| Heart kills | 239 (23.3%) | **253 (24.7%)** | 239 (23.3%) |
| kills per Act-4 arrival | 0.558 | 0.574 | 0.610 |
| mean final floor | 42.65 | 42.57 | 41.04 |
| deaths act 1 / 2 / 3 / 4 | 134 / 219 / 243 / 189 | 137 / 226 / 220 / 188 | 146 / 260 / 226 / 153 |
| whole-run wall mean (max) | 527 s (1,517) | 435 s (1,088) | 87 s (803) |

| pair | Act 4: only first / only second | Act 4 diff [95% CI] | p | Heart: only first / only second | Heart diff [95% CI] | p | floor diff [95% CI] |
|---|---|---|---|---|---|---|---|
| **MAP − OFF (primary)** | 109 / 60 | **+4.79 pp [+2.34, +7.32]** | 2e−4 | 87 / 73 | +1.37 pp [−1.07, +3.81] | 0.30 | +1.52 [+0.86, +2.19] |
| **D − MAP (guard, Heart)** | 107 / 120 | −1.27 pp [−4.20, +1.46] | 0.43 | 90 / 104 | **−1.37 pp [−4.00, +1.37]** | 0.35 | +0.08 [−0.62, +0.80] |
| D − OFF | 133 / 97 | +3.52 pp [+0.68, +6.45] | 0.02 | 96 / 96 | 0.00 pp [−2.64, +2.64] | 1.0 | +1.61 [+0.92, +2.29] |

(p = exact McNemar on the discordant pairs; CIs = 10,000 seed-bootstrap resamples.)

## Verdict under the frozen decision rule: PASS
MAP − OFF Act 4 = +4.79 pp ≥ +2.5 pp with the CI above 0, and D − MAP Heart = −1.37 pp ≤ +1.0 pp. **Route search is the
useful part of OOC search, and searching the other screens adds nothing measurable** (D is, if anything, slightly
behind MAP on both endpoints).

## Mechanism: first divergence (act : screen : decider in first arm / second arm)
| pair | class | seeds | Act 4 Δ | Heart Δ |
|---|---|---|---|---|
| MAP − OFF | identical games | 379 | 0 | 0 |
| | act 1 map (MCTS / student_sel) | 287 | **+29** | +12 |
| | act 2 map | 256 | +16 | +5 |
| | act 3 map | 100 | +4 | −3 |
| D − MAP | act 1 rest (D searches, MAP student_sel) | 425 | **−13** | **−15** |
| | act 1 event | 247 | +4 | −6 |
| | act 1 rewards | 105 | +3 | −3 |
| | act 1 shop | 69 | +1 | +7 |
| | act 1 map (both search; D's fast roots differ) | 67 | −5 | +3 |
| | act 1 card select | 67 | −2 | 0 |
| D − OFF | act 1 rest | 407 | +8 | 0 |
| | act 1 event | 241 | +12 | −1 |
| | act 1 rewards | 101 | +8 | −4 |
| | act 1 map | 95 | +6 | −1 |
| | act 1 shop | 69 | +3 | +6 |

Search diagnostics (`result.json` `search`): D searched 90,322 roots (map 37,846, rewards 27,428, shop 8,971, event
7,021, rest 6,692, boss relic 1,561, card select 689, treasure 114); MAP 37,587, all on map screens; OFF none. Picks off
the tree prior's argmax: D maps 1.9%, rewards 3.9%, rest 4.3%, shops 6.5%, boss relics 5.8%; MAP maps 2.9% (full budget
on every map root vs D's 25% full roots). D's card-select figure (68%) is not an override rate: `heart1full` gives
card-select roots a uniform tree prior, so its "argmax" is arbitrary; in MAP and OFF those screens are decided by
student_sel's own card-select policy (`heart1::policyStep`).

## Interpretation
- **Replication:** the gen-0 decomposition (map overrides carry the search gain, mostly act 1) replicates in a
  randomized design on today's stack: map search alone gives +4.8 pp Act-4 arrivals over no search; 45 of the net
  49 extra arrivals come from pairs that first split at an act-1 or act-2 map choice.
- **The arrivals convert to kills only weakly:** MAP − OFF Heart +1.4 pp (n.s.); kills per arrival fall from 0.61
  (OFF) to 0.57 (MAP). OFF's extra deaths are in act 2 (+34 vs MAP); MAP's extra arrivals die in Act 4 (+35 Act-4
  deaths). **Inference:** the routes search picks are safer for survival, not stronger for the Heart, which fits a
  leaf that scores survival (rollout3 + X2-B) better than final Heart strength.
- **Today's default gains nothing from non-map search:** D − OFF Heart is exactly 0 (96 / 96) despite +3.5 pp Act 4,
  and D − MAP is −1.4 pp kills. The largest single class is D searching act-1 rest sites (425 seeds where it was the
  first split vs MAP): −13 arrivals, −15 kills (observational, not randomized within the pair).
- **CPU:** MAP costs 0.83× D's wall (435 vs 527 s per game) and 5.0× OFF's.

## Follow-up per the PREREG
PASS → a separate PR may propose MAP (`STS_OOC_MCTS_SCREENS=map`, full budget on map roots) as a candidate A20 default,
to be qualified by a paired A20 A/B at matched CPU (AZ-loop rule) on the current main (with Act 4 strong). That and
any default change are Philipp's call. Natural next questions: whether the saved CPU is better spent on more map
simulations, and whether rest-site search is actively harmful (an `all minus rest` arm).

## Caveats
- One screen of 1,024 seeds; the guard is a non-inferiority bound, not a proof that non-map search is useless.
- Base `61a536fe` predates #852 ("Act 4 strong"); kill rates under the new default will differ, and the Act-4 strength
  change could change how arrivals convert.
- First-divergence classes are observational (the class is a consequence of the arms, not randomized).
