# ADR-TBD: At A20, real OOC MCTS searches only map screens, each at the full budget

Date: 2026-10-24
Status: accepted

Changes which real roots [ADR-0043](0043-az-loop-gumbel-policy-target.md)'s OOC MCTS searches, and how
[ADR-0055](0055-ooc-fast-root-cap.md)'s fast-root cap applies at them.

## Context

The OOC direction review (2026-10-24) found gen-0's whole search gain (§569) in pairs whose first divergence was a map
override. §683 tested it on 1,024 paired A20 seeds (base `61a536fe`, Act 4 under the learned stop): OOC MCTS only at
map roots, all at 4096 simulations (MAP), reached Act 4 +4.8 pp [+2.3, +7.3] more often than no OOC search, and today's
all-screen search did not beat MAP (Heart D − MAP −1.4 pp [−4.0, +1.4]; Act 4 −1.3 pp). MAP cost 0.83× D's wall.

Philipp decided on 2026-10-24 (22:40Z): "kein A/B. mach MAP default kandidat mit act 4 strong."

## Decision

- With `STS_OOC_MCTS_SCREENS` unset, OOC MCTS with the heart1 prior, outside the live advisor, at real roots of
  ascension 20 runs:
  - **only on map screens**; every other screen, after the unchanged rule chain (key, tree, relic, chest, rest/shop
    rules, match-and-keep), is decided by student_sel's argmax (`heart1::policyStep`, `by=heart1_screen`);
  - **at the full budget on every map root**: with playout-cap randomization (`STS_OOC_MCTS_FULL_BUDGET_FRACTION`)
    every searched root is a full-budget root, so the fast-root cap never applies and every map root supplies a
    policy target.
- `STS_OOC_MCTS_SCREENS=all` restores every screen and the fraction's fast/full split. An explicit screen list keeps
  §683's research meaning (the listed screens; the fraction applies as set).
- Ascension below 20, runs without the heart1 prior, imagined decisions inside a search and the live advisor are
  unchanged. Together with [ADR-0060](0060-act4-strong.md) (Act 4 strong) this is the A20 default stack.
- The startup banner prints `screens_a20_default=map_full_budget`; the OOC provenance JSON records
  `"searchScreensA20Default":"map_full_budget"`.

## Consequences

- Play changes on every A20 run at non-map screens and at map roots that were fast roots. No A/B was run with Act 4
  strong (Philipp's decision); §683's evidence predates ADR-0060.
- CPU: in §683 a game took 435 s with MAP vs 527 s with all screens (Act 4 under the learned stop).
- Data generators that use the real OOC chain at A20 (`heartoutcomegen ... policy`, AZ-loop generators with
  `STS_AZGEN_PRODUCTION_OOC=1`) now record OOC policy targets only at map roots; set `STS_OOC_MCTS_SCREENS=all`
  for targets on every screen.
- Comparability: runs from before this ADR at A20 are reproduced with `STS_OOC_MCTS_SCREENS=all`; freeze files must
  record the flag.
- The live advisor keeps its all-screen search until a separate change and reinstall.
