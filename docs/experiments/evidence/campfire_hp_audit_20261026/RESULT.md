# Campfire choices vs HP before the act-3 bosses and the Heart (offline audit, 2026-10-26)

Question (deep-research experiment 8, Philipp 2026-10-26): does the bot smith or Recall at low HP before
the act-3 bosses or the Heart, including the Ruby rule spending a campfire, and what does that cost?

Data: existing games only, no seeds. §683 (1,024 seeds × D/MAP/OFF, share `ooc-map-only-search/units`)
and §676 (512 seeds × A/C, share `ctm-calibration-ab/units`), 4,096 complete games, all with
`STS_KEY_RUBY=policy` (Ruby is forced only at the act-3 pre-boss campfire, map row 14 = floor 49).
`extract.py <unit root> <out.pkl>` reads the decision and CTM rows; `analyze.py m683.pkl g676.pkl`
writes `analyze.json`. Choice = MCTS selected effect where recorded, else inferred from the next
non-campfire state (agreement 100% on smith/rest/recall where both exist).

## Findings (all five arms; MAP alone agrees)

1. **The policy's own campfire choices are fine.** Without Coffee Dripper and with HP below 60% in acts 2–3 it
   rests 3,641 of 3,669 times. Nearly every low-HP smith/lift/dig is a Coffee Dripper run (rest illegal):
   444 smiths with Dripper vs 5 without. Voluntary Ruby Recalls below 60% HP without Dripper: 16.
2. **Act 4 is not a campfire problem.** The act-4 campfire smiths with ≥ 10 HP missing in 64 of 1,696
   arrivals (3.8%). The Heart is entered 21.6 HP below max, which is the Shield and Spear damage
   (19.8 HP when won). HP into the Heart is a S&S combat question, not a campfire one.
3. **The forced Ruby is the one lever.** It takes the pre-boss campfire in 60% of the 2,304 runs that
   reach it, mostly at ≥ 80% HP (no cost). Below 60% HP without Dripper: 164 runs (4.0% of all runs),
   act-3 boss death 72%, Heart kill 12.8%; runs that rested there at the same HP band: death 50%, kill
   24.2% (n 62, already holding Ruby; observational).
4. **Implied cost (observational logistic on boss-1 entry HP, upper-bound style).** A rest (+27 HP)
   instead of the forced Recall for those 164 runs: −1.2 pp act-3 boss deaths and **+0.65 pp Heart kills
   over all runs**. Only 82 of them (2.0% of runs) passed an earlier act-3 campfire at ≥ 60% HP, where
   Recalling would have freed the pre-boss rest: **≤ +0.32 pp**, before charging the action lost at that
   earlier campfire (rest 38, smith 32). At a 70% threshold: ≤ +0.62 pp. The other half had no earlier
   high-HP act-3 campfire, so only routing could help them.

## Intervention and test

Smallest intervention: the existing `STS_KEY_RUBY=hp` (Recall at the first act-3 campfire with HP ≥
`STS_KEY_RUBY_MIN_HP`, default 0.6), no code. It changes play in about a third of runs (341 of 1,024
MAP seeds pass such a campfire without Ruby), but the expected gain is at most about +0.3 pp, while a
paired A/B on the 341 diverging §683 seeds (MAP arm as control) has an MDE of roughly 2 pp. No affordable
whole-run test can show it. Recommendation: no run; record as an audit. If wanted, the cheap causal check
is a pre-boss fork (rest vs Recall) on the 82 states replaying both act-3 bosses, which needs act-3
support in `act4replay` (currently S&S/Heart only).
