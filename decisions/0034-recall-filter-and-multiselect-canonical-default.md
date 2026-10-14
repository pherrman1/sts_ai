# ADR-0034: Optional Ruby Recall filter and canonical multi-select masks by default

Date: 2026-10-14
Status: accepted

## Context

Two default-off flags correct a defect or a redundancy rather than change a
heuristic:

- **Optional Ruby Recall.** With keys off (`STS_COLLECT_KEYS` unset or `0`),
  the engine still offers Recall at campfires. The V4 campfire gate and the
  random fallback (`ScumSearchAgent2::stepRandom`) can choose it, although the
  Ruby key is then useless because Act 4 is unreachable. The overnight
  campaign confirmed this as a defect (H04, `BUG_CONFIRMED`, five optional
  Recall detours in 259 campfires) and added `STS_OOC_SKIP_OPTIONAL_RECALL=1`,
  which removes Recall when another legal action exists. Both arms of the
  §395 512-pair confirmation used it. Live OOC MCTS already drops
  `TAKE_RUBY_KEY` from its tree when keys are off
  (`ooc_mcts_adapter.cpp`), but its rollouts and fallback use the chain that
  this flag filters.
- **Canonical multi-select masks.** Hand multi-selects (Gambler's Brew,
  Elixir, Gambling Chip, Forethought) enumerate every valid hand subset, so
  identical copies give duplicate masks (ten Strikes: 1023 masks, 11 distinct
  outcomes). `STS_MULTISELECT_CANONICAL=1` (§145) keeps one mask per selected
  card multiset; card identity includes upgrade, turn cost, free-to-play and
  special data, and order-sensitive tasks keep their order. Silver uses this
  enumerator (`SilverSearcher::enumerateActionsForNode` →
  `Action::enumerateCardSelectActions`) and only deduplicates single-card
  selects itself.

Neither flag was shown to change win rate: the Recall filter was never tested
on its own, and §145 (Searcher3, 64 seeds) was −1.6 pp [−4.6, +1.5]. On
2026-10-14 Philipp chose to turn both on ("mach 1 immer an. 4 eigentlich
auch.") after a flag audit
(`/mnt/project-files/flag-audit/AUDIT-2026-10-14.md`).

## Decision

- With `STS_OOC_SKIP_OPTIONAL_RECALL` unset, the V4 campfire gate and the
  random fallback remove Recall when keys are off and another action is legal.
  A forced sole Recall stays. `0` restores the legacy eligibility exactly;
  `1` equals the default; other values stay fatal.
- With `STS_MULTISELECT_CANONICAL` unset, hand multi-select enumeration keeps
  one mask per selected-card multiset. `0` restores the full mask list.
- The startup banner `[native OOC optional Ruby Recall excluded ...]` and the
  counterfactual teacher policy flag `skip_optional_recall` now appear by
  default.

## Consequences

- Runs can play differently from before whenever a campfire offers Recall
  with keys off (MCTS-off chain, OOC MCTS rollouts and fallback) or a combat
  reaches a multi-select with duplicate hand cards. Earlier results need
  `STS_OOC_SKIP_OPTIONAL_RECALL=0 STS_MULTISELECT_CANONICAL=0` to reproduce.
- Comparisons against controls from a binary without ADR-0034 must set both
  to `0` in the new arm or rerun the controls.
- The counterfactual teacher identity now carries `skip_optional_recall` by
  default (`combat_datasets.cpp`), so `wholecombatgen` against an older frozen
  teacher that records `ooc_policy` fails closed unless it runs with
  `STS_OOC_SKIP_OPTIONAL_RECALL=0`.
- `cardselect_parity` pins the full mask contract with
  `STS_MULTISELECT_CANONICAL=0`; `cardselect_canonical` covers the default.
- **Unverified:** the playing-strength effect of either change. Both were
  chosen because they remove a wasted or duplicate action, not because a game
  test passed.

## Evidence

`tests/rest_recall_filter_test.cpp` (unset now filters; explicit 0 keeps the
legacy action and engine state), `tests/full_hp_rest_filter_test.cpp`,
`test cardselect_canonical`, `test cardselect_parity`. Overnight campaign H04:
`docs/experiments/evidence/ironclad_a0_overnight_20261008/HYPOTHESES.md`.
Multi-select gate: ledger-06 §145.
