# Boss-budget probe: result (§718)

Campaign `boss-budget-probe`, frozen per `PREREG.md` (pre-launch review PASS + delta PASS; run commit `ae23bb13`,
code `32f7ee76`, binary `3f52f677…`). 16 cloud workers, 2026-10-29 08:33-11:4xZ (Philipp: "Let's go on 16 workers").
`verify_campaign.py`: 250/250 units OK, none missing, bad or duplicated, one run commit, DONE.json 16/16. Analysis:
`analyze.py` → `result.json`. 499 boss fights in 250 runs, none dropped.

## Primary (acts 1-3 bosses, flat40000 − production, HP lost per fight)

| side | HP lost | death/fight | potions/fight | CPU/copy |
|---|---|---|---|---|
| production (learned stop ≤ 10k) | 15.41 | 0.110 | 0.70 | 25.2 s |
| flat 20k | 14.95 | 0.100 | 0.71 | 100.6 s (4.0×) |
| flat 40k | 15.16 | 0.102 | 0.70 | 195.2 s (7.7×) |
| expert (logged) | 12.02 | | | |

**flat40000 − production −0.25 [−1.10, +0.61]**. Pre-registered rule: lo = −1.10 ≤ −1 and hi ≥ 0 → **INCONCLUSIVE**.
The lower bound misses the NO_USEFUL_GAIN region by 0.10 HP. Co-reported: flat20000 − production −0.46 [−1.27,
+0.34]; death difference −0.01 [−0.03, +0.01] for both arms; production − expert +3.4 [+1.95, +4.82].

## By act and encounter (descriptive)

| | n | flat40k − prod | flat20k − prod |
|---|---|---|---|
| act-1 bosses | 250 | −0.53 [−1.42, +0.34] | −0.17 [−1.03, +0.67] |
| act-2 bosses | 128 | −0.40 [−2.45, +1.53] | −0.99 [−3.15, +1.07] |
| act-3 bosses | 121 | +0.49 [−1.63, +2.82] | −0.50 [−2.29, +1.38] |

Encounters (n ≥ 20): Automaton −2.2 / −3.4 (40k / 20k), Time Eater −2.2 / −0.9, Awakened One +2.0 / −0.8, Donu and
Deca +2.0 / +0.3, Collector +1.4 / +0.6, Champ −0.9 / −0.6, Hexaghost −0.6 / −0.0, Slime Boss −0.8 / −1.1, Guardian
−0.2 / +0.6. Every CI includes 0.

## Against §716

§716's 32 act-2 bosses are part of this sample. They reproduce exactly here (the same copy seeds give the same
flat-40k exits in 32/32 fights), so its −3.25 was a favourable subset: on all 128 act-2 bosses flat 40k gives −0.40.

## Interpretation

On Baalorlord's 499 boss states, 2× to 4× today's maximum root budget (flat 20k or 40k against the learned stop's
≤ 10k) buys at most about 1 HP per boss fight at 4-8× the CPU. The point estimates are −0.3 to −0.5 HP, and deaths
do not change. So the bot's +3.4 HP boss gap to the expert is not a search-budget problem either, at least up to
40k simulations. Flat 40k is no better than 20k. That may reflect the 32,768-node reuse cap: in the Act-4 node-cap
check of 2026-10-24 a flat 40k root started fresh at about 30% of reroots, against about 5% at 10k. It is not
measured here. Together with §716 (elites flat to 100k),
combat strength on these states is not bought with simulations. It is in the evaluation (leaf value and playout
policy), or in engine fidelity, which is untested. No default change; whole-run A/B not warranted.

Seeds: none new (external Baalorlord run seeds of §694/§711, replayed).
