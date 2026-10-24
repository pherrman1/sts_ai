# Act-4 combat strength: more Silver budget does not win the Heart; prior playouts save 4.4 HP in Shield and Spear (2026-10-24)

**Question** ([PREREG](PREREG.md)). From the decks today's agent brings to Act 4, does stronger Silver search win
Shield and Spear (S&S) with more HP or the Heart more often, or are the decks the limit?

**Run.** Frozen at run commit `60b39fa6` (code `888bda40`, binary `00d3f309…`), pre-launch review PASS
(`/mnt/project-files/reviews/pr852-prelaunch-review.md`). 32 cloud workers × 4 lanes, queue schedule, 2026-10-24
09:37Z–12:09Z. `tools/cloud/verify_campaign.py`: 768 of 768 units OK, 0 bad, 0 duplicates, one run commit; every
unit's `.env` carries `STS_EXECUTABLE_GIT_SHA=60b39fa6`. 767 units rc 0; `heart 15 P` rc 91: copy 4 at 40k hit
Silver's 1,000-decision stall guard (`exceeded 1000 decisions seed=111398224`), so the fight has no outcome.
12,287 fights with an outcome, all valid.

**Deviation.** `analyze.py` was changed after the freeze (commit `269cf66d`): a fight that threw is dropped, with its
(state, copy), from every cell so the cells stay paired, and listed under `errors`. This drops 6 fights of Heart
state 15 copy 4 (one error). Results: [`analysis.json`](analysis.json).

| cell | Heart wins | Heart HP lost | Heart CPU s/fight | S&S wins | S&S HP lost | S&S CPU s/fight |
|---|---|---|---|---|---|---|
| P@10k | 57.5% | 54.8 | 9 | 93.8% | 29.9 | 6 |
| P@40k | 58.7% | 53.9 | 37 | 94.0% | 28.7 | 22 |
| PP@10k | 60.9% | 53.8 | 58 | 94.7% | 25.4 | 36 |
| PP@40k | 61.9% | 53.1 | 230 | 95.1% | 25.5 | 141 |
| N@10k | 57.4% | 56.7 | 9 | 92.3% | 30.6 | 6 |
| N@40k | 56.1% | 57.0 | 37 | 92.7% | 31.3 | 22 |

(1,023 Heart and 1,024 S&S fights per cell; HP lost counts a death as all entry HP. Production plays the Heart as
PP and S&S as P, with the learned stop.)

**Primary** (95% bootstrap over the 128 states):
- Heart win `PP@40k − PP@10k` **+0.9 pp [−1.1, +3.0]**: below +3 pp.
- S&S HP lost `P@10k − PP@40k` **+4.4 HP [+3.1, +5.7]**: above 3 HP with the CI above 0.
- Rule: **COMBAT_HEADROOM**, from S&S alone. The Heart part is saturated.

**Secondary.**
- The S&S gain is the prior playouts, not the budget: `P@10k − PP@10k` +4.5 HP [+3.1, +5.9]; `PP` 40k − 10k
  +0.1 HP [−0.8, +1.1] lost; `P` 40k saves 1.1 HP [0.1, 2.2]. S&S deaths 6.2% (P@10k) vs 5.3% (PP@10k).
- Heart: prior playouts (production) beat greedy playouts by 3.4 pp [1.1, 5.8] at 10k; 40k − 10k is +1.2 pp
  [−1.1, +3.3] with greedy playouts and −1.3 pp without a prior. The root/tree prior adds nothing at 10k
  (`P − N` +0.1 pp) and +2.5 pp [+0.3, +4.8] at 40k.
- Lost decks: of the 128 Heart decks, 15 lose all 48 fights (every cell, every copy) and 20 win all 48. Under
  production (PP@10k) 20 never win, 41 always win and 67 are mixed: for half the decks the fight's own randomness
  decides. Only 5 decks that production never wins are won by another cell, each in 1 of 8 copies.
- Entry HP: Heart wins are 25-33% below 40 HP, 31-38% at 40-59, 66-73% at 60-69 and 64-70% at 70+, in every cell.
- Fidelity: on the same 128 states the replay (PP@10k) wins the Heart 60.9% against 58.6% in the real games
  (learned stop). S&S replays lose 29.9 HP against 24.1 recorded; the recorded HP is after Burning Blood's +6 heal
  at the end of combat, which `act4replay` does not apply (all 128 decks have Burning Blood).
- Node cap. Silver drops its reused tree at reroot once it holds 32,768 nodes. At 40k that happens at ~30% of reroots
  (node-cap check, `/mnt/project-files/silver-node-cap/`), so these 40k cells are closer to 2.3× the 10k
  search than 4×. The follow-up `../act4_combat_reusecap_20261024` replays every 40k cell with the cap raised.

**Interpretation.** More search per decision does not win the Heart from these decks (at least at this node cap);
about half of them are coin flips that the fight's random draws decide, and 12% are lost to every Silver tried. In
S&S, playouts that follow the g7f_E prior instead of the greedy table save about 4.5 HP right before the Heart; §642
found no gain on 32 states with the act4replay reconstruction errors this PR fixes. At the replay's Heart slope
(about 35 pp between 40-59 and 60-69 HP) 4.5 HP is worth roughly +2-3 pp per Heart fight.
