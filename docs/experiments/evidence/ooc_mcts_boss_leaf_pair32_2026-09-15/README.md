# OOC MCTS all-current-act-boss leaf paired 32

Classification: **`BOSS_LEAF_NO_OBSERVED_BEHAVIORAL_EFFECT`**.

On fresh paired seeds 12003000--12003031, both the existing native `v_win`
leaf and the all-current-act-boss combat-evaluator leaf won 24/32. Every seed
had the same win/loss, floor, final HP, max HP, and death combat/encounter.
The paired boss-minus-native win delta is 0.0 percentage points; the fixed
200,000-resample paired percentile interval is [0.0, 0.0]pp because all 32
observed paired differences are exactly zero. This is no observed effect on
this cohort, not proof of policy equivalence.

The treatment evaluates all three possible bosses for the leaf state's current
act with the tracked qualified V2 combat-transition model. Per boss, utility is
`0.75 * P(survive) + 0.25 * P(survive) * E[ending HP fraction | survive]`;
the leaf is their arithmetic mean. Exact terminal values remain 0/1. Any
unsupported boss fails the simulation/root closed. The treatment leaf never
calls `v_win`; the normal live fallback OOC chain remains unchanged.

Both arms used source `b5f037d56cc9ac6d841ccab43274e85ca3330313`
plus implementation diff SHA256 `e6cb7b1249d0d77e947470f99b79b2e6d367be2035df30bcfd388251415f78a0`,
binary SHA256 `8b69fab5eab347cb67b01982059c581cea7d882deea774168ccbc0d46855199a`,
V2 combat artifact SHA256 `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`,
and V4 policy SHA256 `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`.
The shared regime was Ironclad A0, fair RNG, keys off, Act-3 stop, exactly 512
OOC MCTS simulations, V4 policy priors, and ordinary exact-root-budget 10k
Silver real combat with 12 OpenMP workers. Both arms ran sequentially through
`tools/seed_guard.sh`.

Native/boss mean floor was 47.9375/47.9375, mean final HP
40.1875/40.1875, and mean seconds per run 103.8807/104.1177. Each arm recorded
5,540 OOC decisions, 4,528 MCTS-owned decisions, 1,012 fallbacks, 1,181,831
completed simulations, 1,180,553 leaf evaluations, nine expected Smoke support
aborts, and 375 discarded simulations. All 32 non-timing per-run trace rows
match exactly. There were zero continuation-limit aborts; all support reasons
were the frozen `smoke_bomb` exclusion.

`plan.json` was written before paired collection. `run.py` validates binary
and model hashes and complete seed membership. `analyze.py` validates both
32-row result and trace cohorts, computes the paired result with fixed seed
20260915, and binds raw artifact hashes in `results.json`. Two pre-game failed
starts caused by invalid abbreviated provenance labels are retained under
`failed-start/`; neither completed a seed.

The opt-in implementation remains experimental and live OOC MCTS remains OFF
by default. This N32 result provides no reason to replace the native leaf or to
run more seeds without a distinct hypothesis about why leaf values are not
changing root choices.
