# Ritual-refit CTM vs deployed CTM in A0 OOC MCTS — result (2026-10-17)

**Result: uninformative, with 64/64 identical pairs.** No run in either arm ever held a Ritual Dagger, so the refit
Ritual head was never queried. Both arms ran byte-for-byte the same games.

- 128/128 units rc=0, run 12:09–14:37Z on 8 local cores. Binary `d02d4a1d…`, run commit `607d683b`, seeds
  111000800–111000863. Independent pre-launch review PASS. Rows are in [results.csv](results.csv).
- Act-3 clears were 58/64 in both arms, with 0 discordant pairs. Mean floor was 49.55 in both. Mean wall time per
  run was 542 vs 543 s.
- All 64 `ritual` units logged `[ctm-research-candidate] candidate_id=pathb-r2-ritual-refit`, so the candidate
  was loaded.
- There were no OOC MCTS support aborts in either arm (`.mcts.csv.support.jsonl`). In particular,
  `writhing_ritual_intersection` never fired.
- The decision traces show no "Ritual Dagger" in any deck.

**Interpretation:** at A0 the Dagger is rare. It comes from the Nest event, and the bot never took it in 64 runs. A
seed A/B of this size cannot measure the refit's effect. The refit only changes play in runs that hold a Dagger.
To measure it, a run would need either a targeted set of seeds that reach the Nest and take the Dagger, or forced
Dagger acquisition, as in the coverage pilots. No default change was made.
