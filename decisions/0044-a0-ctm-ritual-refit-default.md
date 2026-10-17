# ADR-0044: The A0 CTM default is pathb-r2 with refit Ritual Dagger heads and Writhing+Dagger support

Date: 2026-10-17
Status: accepted

## Context

The A0 combat transition model (CTM) stack pathb-r2 refused every imagined Writhing Mass fight with a Ritual Dagger
in the deck (`writhing_ritual_intersection`). A refusal aborts that decision's OOC MCTS search, and V4 decides
instead. Its Ritual heads were trained on rows from a simulator bug that dropped Dagger growth from the combat-ending
kill (#585). They predicted about 0.5% growth where corrected rows show 7–10% (§507).

§507 refit only the `ritual.*` tensors of both pathb-r2 artifacts on corrected pilot rows (§505, §506).
- On VALIDATION Writhing fights, NLL went from 0.514 to 0.350, and predicted growth from 0.6% to 6.2% against 8.3% observed.
- On non-Writhing Dagger fights the point estimate was −0.002 nat, but the CI upper bound of +0.0107 missed the
  preregistered +0.005 margin.
- Philipp overrode that criterion (`docs/experiments/evidence/ctm_ritual_refit_20261017/decision.json`).
- The 64-seed A0 A/B (§508) was identical on all pairs, because no run held a Dagger.

On 2026-10-17 at 16:43Z, Philipp wrote: "ship it anyway".

## Decision

- The automatic A0 stack is the research candidate `pathb-r2-ritual-refit`, embedded as the current built-in
  production manifest (`1a13abb7…`) so it loads without `STS_CTM_RESEARCH_CANDIDATE_MANIFEST`:
  - fast `selfplay/models/combat_transition_deepsets_pathb_r2_lizard_ritual_refit.native` (`3bbff6b6…`);
  - Brew fallback `selfplay/models/combat_transition_near_full_escape_pathb_r2_ritual_refit.native` (`2f0f5d97…`).
- Both artifacts carry `writhingRitual`. Every other tensor and capability is unchanged from pathb-r2.
- The same stack is the default in OOC MCTS (`ooc_mcts_adapter.cpp`), `screen_leaf_s0`, `ctmScoreRows`, the live
  advisor's fallback pairing and new live-runtime installs (`tools/live_game_runtime.py`).
- Live releases installed with the pathb-r2 pair still validate.
- The previous pathb-r2 manifests stay built in. Rollback:
  - `STS_OOC_MCTS_COMBAT_MODEL=selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native`
  - `STS_OOC_MCTS_BREW_FALLBACK_MODEL=selfplay/models/combat_transition_near_full_escape_pathb_r2.native`
  - `STS_OOC_MCTS_ACTIVE_LIZARD=1`
  - Live: `STS_CTM_MODEL` and `STS_CTM_BREW_FALLBACK_MODEL`.
  - Caveat (post-merge review, 2026-10-17): this rollback is exact only below A20. Setting
    `STS_OOC_MCTS_COMBAT_MODEL` or `STS_OOC_MCTS_BREW_FALLBACK_MODEL` leaves the automatic stack, so the
    pathb-a20 CTM that ADR-0033 loads for ascension-20 decisions is dropped, and adding
    `STS_OOC_MCTS_A20_CTM=1` fails at startup (`ooc_mcts_adapter.cpp`, `a20Compatible`). An A20 run with these
    variables uses the old A0 pair for A20 decisions too.

## Consequences

- Runs holding a Ritual Dagger can play differently. OOC search no longer aborts on Writhing+Dagger states, and Ritual
  growth probabilities change in every Dagger fight. Runs without a Dagger are unchanged (§508: 64/64 identical).
- The playing-strength effect is unmeasured. The non-Writhing no-regression margin was waived, not shown.
- A0 Ironclad CTM refusals that remain: `pre_smoke_bomb_used`, Alchemize, the HP envelope, active Tail with Mark of
  the Bloom, and malformed inputs (`docs/experiments/evidence/ctm_ritual_refit_20261017/SUPPORT_INVENTORY.md`).
