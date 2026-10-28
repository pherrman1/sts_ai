# Prior vs search at OOC roots: paired fork test (#882, PREREG, 2026-10-28)

Issue [#882](https://github.com/pherrman1/sts_ai/issues/882): why does OOC MCTS rarely improve on the student_sel
prior outside map decisions? Diagnostic only; no default change follows from this file.

## Evidence before this run (no new seeds)

1. **§683 D arm re-read** (1,024 games, all screens searched at production budgets; `/mnt/project-files/ooc-map-only-search`):
   search leaves the prior's argmax at 2–8% of roots per type (full 4096 roots 3.5–12%). Median top prior 0.98–1.0
   (shops 0.90); the prior argmax gets 75–92% of visits. At full roots an explored sibling (≥ 4 visits) has a higher
   Q than the played action at 28–41% (rewards, map, event, boss relic) and 62–67% (rest, shop) of roots. Games whose
   first public difference D vs MAP follows a non-map override: Heart −0.3 pp [−4.3, +3.5] (631 seeds).
2. **Root probe** (`STS_OOC_ROOT_PROBE`, code `b225220d`, binary `4dfc84d9…`) on the 64 core roots of #881's shared cohort
   (branch `claude/sibling-noise-881-data` `f35262a`: replays of the used §683 MAP seeds 111374100–115, 8 roots per type;
   every probe replay equals its §683 game up to where it stopped). Raw rows:
   `/mnt/project-files/ooc-prior-vs-search-882/probe-rows-b225220.jsonl.gz` (sha256 `a1ef495a…`). Against the
   production pick: PUCT 4096 departs at 9/64 roots, PUCT 32768 at 16/64; the uniform 8192 reference of the same leaf
   (two seeds) prefers another action with z > 2 at 25/64 (median gap 0.023). 11 of the 16 deep departures go to the
   leaf reference's best action.

## Question and arms

At the 28 probed roots where PUCT 4096, PUCT 32768 or the leaf reference disagree with the production pick
(`fork_roots.jsonl`; 5 shop, 4 card select, 4 boss relic, 4 rest, 3 rewards, 3 map, 3 event, 2 treasure; the card-select
remove after shop root 111374105/38 is dropped as the same decision), is the alternative better in real play?

- **B** (production): `STS_OOC_FORCE_DECISION=INDEX:SALT:-`; **A** (alternative): `INDEX:SALT:KEY`, KEY = the deep
  search's pick if it departs, else PUCT 4096's, else the leaf reference's best.
- Both replay the same used seed and stack to the root (the #881 cohort env, `run_unit.sh`), then redraw the hidden
  future with SALT (`resampleCounterfactualFuture`), so A and B share it; salts 1–16 give 16 independent paired
  continuations per root. Both play to the end of the game. No new seeds.
- Smoke (seed 111374100, root 4): salt 0 with `-` reproduces the source game exactly; salted and forced forks
  diverge only after the root.

## Endpoints and analysis (`analyze.py`, frozen with this file)

- Primary: Heart kill. Secondary: Act 4 reached. Per root, d = mean over salts of y(A) − y(B).
- Validity: rc 0, an outcome row, the game's states equal the §683 MAP game's states up to the root, A's root row
  `by=forced_decision`. Invalid games drop their pair; counts are reported.
- Groups: all 28 roots; **search_departs** (PUCT 4096 or 32768 departs, 15 roots); **leaf_only** (only the leaf
  reference disagrees, 13 roots); each screen type. Effect = mean over roots,
  95% CI by a two-stage bootstrap (roots, then salts), 10,000 resamples, RNG 20261028.
- Also reported: per-root effect with SE, base Heart rate per root, correlation of the leaf gap with the effect.

## Classification (per type, and for the two pooled groups)

- **search beneficial:** search_departs effect CI lower bound > 0.
- **search/exploration constrained:** leaf_only (alternatives search does not take) effect CI lower bound > 0.
- **value/leaf limited:** the leaf's preferred alternatives are not better (point ≤ 0) although search moves toward
  them with budget.
- **prior near-ceiling:** all disagreement roots of the type have effect ≤ 0 with CI upper bound < +3 pp.
- **inconclusive:** anything else. With 2–5 roots per type, per-type classes are expected to be mostly inconclusive;
  the pooled groups carry the decision (pooled SE about 2 pp).

## Cost and provenance

- 448 units × 2 games, about 12 core-min per game, about 180 core-h; 16 workers × 4 lanes, queue schedule.
- Code `b225220d62965b8a6f58048b48f9ac46893f9cc3`, binary (v3 preset) sha256
  `4dfc84d9a0160b8f4ec58c6fe755e3b999c126f89f331d0e651318b766954f87`; student_sel `cf6bf7fb…`.
- Seeds: replays of 111374100–111374115 (used by §683; no new seeds). Authorization: Philipp's typed go in the #882
  thread (pending). RUN_COMMIT: the commit carrying this file's final campaign files.
