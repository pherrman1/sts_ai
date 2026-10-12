# #397 live hidden-queue ablation: legacy native fallback vs public futures (pre-registered)

Frozen 2026-10-11 ~21:55Z before any pilot seed ran. Smoke seed 74015900 (both arms rc=0, scorer receipt present) is excluded.

Question: the native OOC fallback (card picks, shop, removal, upgrade/heal when V4 gates decline) feeds the
tracked floor/win trees the realized unrevealed encounter queue (nextEliteId, nextFight0..2) even under
STS_FAIR=1. How much playing strength does that hidden information carry on the current research base?

Code: main 491bc21b (Release, linux-gcc-release), one_combat sha256 bab14cd5800ed39aeffc3a284670a10525434efde3bceb400a4c57b53406ee6c.
Base: exactly the §422 "off" arm (exact-10k fair Silver, V4 token gates margin 1.0, OOC MCTS off, keys off,
STS_REST_WIN=0, act-3 stop, 1 OMP thread). Sole difference: STS_OOC_PUBLIC_FUTURES=0 (legacy) vs 8 (public8).
Seeds: 74015000..74015127 (128 pairs), both arms, ascension 0.

Primary: paired difference in Act-3 wins, public8 − legacy, percentile bootstrap 95% CI (10,000 resamples, seed 397).
Labels: LEAK_HELPS if the CI upper bound < 0; PUBLIC8_BETTER if the lower bound > 0; else LEAK_NOT_SHOWN.
Secondary (descriptive): paired Δfloor with CI, discordant counts, McNemar exact p, mean s/run,
public scorer receipts (public8 must report scorers > 0 on every seed; legacy must report none).
Validity: every seed present once in each arm, rc 0; otherwise report INVALID and do not interpret.
No default change from this run. 128 pairs cannot resolve effects below ~±8 pp; a null is "not shown", not "no effect".
