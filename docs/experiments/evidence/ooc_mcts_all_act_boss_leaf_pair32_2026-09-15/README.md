# OOC MCTS all-Act boss leaf paired 32

Classification: **`INVALID_TREATMENT_NOT_EXERCISED`**.

This is not a valid A/B test. Live OOC MCTS used `checkpointLeaves=true`, and
the executed checkpoint branch ignored `bossLeaf` and called native `v_win`
in both arms. The 1,199,100 leaf evaluations per arm therefore did not
exercise the treatment. The exact equality below is a bug signal, not evidence
of no behavioral effect. Raw artifacts are retained for provenance only.

Fresh paired seeds 12003032--12003063 compare the existing native `v_win`
leaf with a combat-evaluator leaf averaged across all ten Act 1--4 bosses.
Both arms won 26/32. Both-win26/both-lose6/native-only0/all-bosses-only0
gives a 0.0 percentage-point delta. The fixed 200,000-resample paired
percentile interval is [0.0,0.0]pp because every observed paired win difference
is exactly zero because both arms executed the same evaluator.

The intended, but unexercised, boss probe preserves the leaf's deck, HP, max HP, gold, relics and potions,
while using the encounter's canonical act and boss floor (17, 34, 50, or 55).
Per-boss utility is `0.75 * P(survive) + 0.25 * P(survive) * E[ending HP
fraction | survive]`; the leaf is the equal mean over Slime Boss, Guardian,
Hexaghost, Champ, Collector, Automaton, Awakened One, Donu and Deca, Time Eater,
and Heart. That implementation existed only in `leafValue()`, which the live
checkpoint path bypassed.

Both arms used Ironclad A0, project-fair RNG, keys off, Act-3 stop, exactly 512
OOC MCTS simulations, V4 priors, and ordinary exact-root-budget 10k Silver real
combat with 12 OpenMP workers. The binary, implementation diff, V2 combat model
and V4 policy hashes are frozen in `plan.json` and each arm receipt. Local HEAD
was five documentation/offline-tool commits behind inspected `origin/main`
`28d39cd`; the diff confirmed those commits changed no OOC runtime, combat
runtime, or model artifact, so the newest relevant executed implementation was
unchanged. Both arms ran sequentially through `tools/seed_guard.sh`.

Native/all-boss mean floor was 49.15625/49.15625, mean final HP
46.09375/46.09375, and mean seconds per run 110.3850/109.9430. Each arm
recorded 5,720 OOC decisions, 4,626 MCTS-owned decisions, 1,094 fallbacks,
1,199,941 completed simulations, 1,199,100 leaf evaluations, twelve expected
Smoke support aborts, 550 discarded simulations, and zero continuation-limit
aborts. All 32 terminal-state rows and all 32 non-timing trace rows match.

`plan.json` was written before collection. `run.py` validates hashes and exact
seed membership; `analyze.py` validates both result/trace cohorts, performs the
fixed paired bootstrap, and binds every raw artifact hash in `results.json`.
This packet must not be used for treatment-effect inference.
