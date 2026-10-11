# §426 plan — rollout3 with the §423 Lizard-capable CTM on the §425 A20 gold decisions (frozen before the run)

**Question:** §425 rollout3 aborted 24% of its A20 searches (Fairy Potion + unused Lizard Tail 167, Entropic Brew +
unused Tail 149, `hp_envelope` 54 on verified targets) because it ran the production CTM; the §423 Lizard-capable
research candidate was not loaded. With that candidate, does rollout3 pick better than the heuristic on the same gold
decisions, and does it differ from §425 `rollout3` and `prod`?

**Diagnostic that motivated it:** 4 gold seeds, 8 targets, search seeds 74002000–74002003: production CTM 7/8 searches
aborted (all Lizard), candidate 0/8 (raw `/mnt/project-files/ooc-rollout3-a20-lizard-check/`).

## Frozen inputs

- Replay tool: PR #476 head `6cd03972` (`strategicgen2` + `STRATEGIC_MCTS_TARGETS/_FORCE/_REPS/_SEED_SHIFT`, default off).
  `one_combat` sha256 `cd0bb658…` (identical to §425). Not on `main`; this PR records evidence only.
- Gold inputs: `targets.csv` `24e8c66f…`, `force.csv` `76a87ee4…` (rebuilt by §425 `build_inputs.py` from the read-only
  gold chunks), `force_fixed.csv` `44ac27e0…` for the 25 `repaired_seeds.txt` seeds, prior `573305c4…`. All match §425.
- Arm `lizard`: §425 `rollout3` environment (`env_common.sh`, ARM=rollout3) plus the §423 candidate exactly as §423
  `arm_env.sh`: `STS_OOC_MCTS_COMBAT_MODEL=selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native`
  (`c6d56bbc…`), `STS_OOC_MCTS_BREW_FALLBACK_MODEL=…near_full_escape_pathb_r2.native`, `STS_OOC_MCTS_ACTIVE_LIZARD=1`,
  `STS_CTM_RESEARCH_CANDIDATE_MANIFEST=…/ooc_rollout3_lizard_20261010/candidate-v3-lizard.json` (`64da1776…`) + its sha.
  Every log must print `[ctm-research-candidate] candidate_id=pathb-r2` and the candidate `combat_model`.
- Seeds (coordinator-assigned block 74004000–74005999): seed index i (0..261, gold seeds sorted ascending), rep
  r (0..3): one replay with `STRATEGIC_MCTS_REPS=1` and search run seed 74004000 + 4i + r (max 74005047), via
  `tools/seed_guard.sh`. 4 searches per target as in §425; only the search seeds differ.
- One cloud container, 4 CPU, 4 processes, `OMP_NUM_THREADS=1`.

## Analysis (fixed)

§425 `score.py` unchanged on arm `lizard` (state verification against the gold rows, fallback = gold-run choice,
10,000-sample decision bootstrap, seed 425), plus `compare.py`: paired Δ (lizard − §425 `rollout3`, lizard − §425
`prod`) of live regret and tie-aware top-1 on decisions verified in this run, using the §425 committed
`searches-{prod,rollout3}.jsonl.gz` picks (same fallback rule); abort rate per search.

**Primary:** live Δregret vs the heuristic, 95% CI. IMPROVED if the CI is entirely below 0, WORSE if entirely above,
else NOT_SHOWN. Everything else is descriptive. No default change in any case (the candidate stays a research artifact).

**Validity:** every unit rc=0; every replay row of a verified decision matches the gold run; reps 1–3 replay rows equal
rep 0's; Lizard support aborts reported (expected 0).
