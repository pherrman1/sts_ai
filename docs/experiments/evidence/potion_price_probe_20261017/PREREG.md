# Potion prices by paired continuation at A20: pre-registration (2026-10-17)

## Question

Silver's end-of-combat score values every held potion at 11 HP (`SilverEvalWeights::potionWeight`).
The §385 X2-B pricing valued them at 2-8 HP-eq and lost gameplay (PR #422, closed). Philipp asked
(2026-10-17, thread "Silver leaf evaluation") for a direct measurement at A20, with potions priced
individually. What is a held potion worth in HP under the current A20 policy, pooled and per type?

## Method (`one_combat potionpriceprobe`, `apps/one_combat/potion_price_probe.cpp`)

- Source run per seed: A20 Ironclad, played by the same continuation policy the branches use
  (`finishOocCounterfactual`: deployed V4 OOC step, exact-10k Silver, OOC MCTS off; environment in
  [run_slice.sh](run_slice.sh), the §422/§473 `off` stack plus the value models below).
- Sampled states: battle-start states (after the first fight) holding at least one potion. Up to 8
  per run by deterministic reservoir sampling.
- Variants per state: `base`; one `pot:<TYPE>` per distinct held potion type (one copy discarded);
  `hp:-12` when HP > 12. Every variant shares the GameContext RNG, the agent seed and the OOC policy
  thread state (common random numbers). Replay of the whole procedure is byte-identical (smoke).
- Each variant plays the next 3 fights with the same policy. If the run is still going, the state is
  valued at the next battle by the models; otherwise by its terminal floor/win.
- Value columns: `altFloor` = A20 floor model `models/candidates/v_rich_a20_419.txt` (**primary**);
  `floorValue` = production A0 floor model `models/v_rich_trees.txt`; `won` = public X2-B;
  `altWon` = `models/candidates/v_win_a20_419.txt`.
- Price of a variant = value(base) − value(variant). HP-eq price of potion type T =
  mean(potion delta over T) / (mean(HP delta) / 12), a ratio of means with a 2,000-sample bootstrap
  over source seeds (`tools/analyze_potion_price_probe.py`).

## Run

- Frozen commit: the commit carrying this file (RUN_COMMIT in the share brief). Release build of `one_combat`.
- Seeds 111110000–111110999 (coordinator block 111110000–111119999); this thread takes
  111110000–111110499, the second cloud worker 111110500–111110999. Each container runs 4 lanes and
  starts no new seed after its deadline (3 h after launch). Seeds that did not start are unused and
  stay reserved for this line. Smokes used 111119900–111119904.
- Expected size (from the smoke: ~5.8 CPU-s per continuation, ~130 s per seed with 5 states): about
  250 seeds and 2,000 states per container.
- Smoke noise: per-pair SD of the `altFloor` delta ≈ 5-6 floors; the HP −8 delta averaged +0.9.
  At ~4,000 states the pooled potion and HP means have SE ≈ 0.1 floor.

## Decision rule (primary: pooled over all potion types, `altFloor`)

- CI of the pooled HP-eq price entirely above 11: `FORMULA_UNDERPRICES`.
- CI entirely below 11: `FORMULA_OVERPRICES`.
- CI contains 11: `CONSISTENT_WITH_11`.
- Also reported against §385's 2-8: whether the CI excludes 8.
- Per-type prices are descriptive, given only for types with n ≥ 100, with no multiplicity claim.
- If the HP slope CI includes 0, the HP-eq prices are `UNCALIBRATED` and only the floor-unit deltas
  are reported.
- No default changes from this run. A per-type potion term in Silver would be a separate
  pre-registered gameplay test.

## Known limits

- Price at battle start, before the fight, not at the end of the previous fight. With a full belt,
  the leaf price also includes a freed slot for a potion drop; this probe does not measure that.
- Known-RNG continuation: the true future encounters, shared by all variants.
- Removing a potion is measured; adding one is not.
- The policy is A0-trained V4 with A20 Silver, as in §473's A20 cohort.
