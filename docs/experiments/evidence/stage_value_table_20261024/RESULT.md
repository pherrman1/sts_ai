# Stage-value table pilot, Heart stage: Stage A says STOP (2026-10-25)

**Question** ([PREREG](PREREG.md), issue #855). Can CRN fights on real Heart entry decks measure what one deck change
(add, upgrade, remove a card; lose HP) does to Heart survival, precisely enough for a reproducible global table?

**Run.** RUN_COMMIT `0de9a35c` (code `cca702c1`, binary `eb4f7c73…`, v3), 8 cloud workers x 4 lanes, queue schedule,
2026-10-24 23:18Z to 2026-10-25 00:40Z. Philipp's go: 2026-10-24 23:00Z ("go stufe A"). Pre-launch review PASS
(`/mnt/project-files/reviews/pr859-prelaunch-review.md`). `tools/cloud/verify_campaign.py`: 96 of 96 units OK,
0 missing, 0 bad, one run commit. Every `deck-*.done` reads rc=0 except deck 95 (rc=91). There, two fights
(`up:Havoc` copy 1, `rm:Pain` copy 2, deck C-111392119) hit the deterministic Silver stall ("exceeded 1000
decisions"); the same state stalled once in #852 (Heart state 15). Those two fights are dropped by the frozen analysis (the PREREG does not define error handling).
Seeds used: 111303000-111303383 (Stage A) and smokes 111308990-997. Results: [`analysis-stage-a.json`](analysis-stage-a.json).

**Data.** 96 decks, 9,598 valid fights, 8.4 CPU s per fight on average.
- Base win rate 54.7%; the same decks won 61.5% of the recorded Heart fights (production combat). This is the P10
  vs production gap seen in #852.
- CRN works. Base and variant outcomes on the same copy correlate 0.68.

**Primary (Stage A futility rule): STOP.**
- DerSimonian-Laird spread of true key effects over the 111 add/up/rm keys with at least 8 decks: **τ = 0.0**. The
  PREREG's plain method of moments gives σ̂² = −0.0006, also clamped to 0 (delta review).
- Per-deck SD of a variant-minus-base difference: 0.207.
- Projected split-half r for the full 392-deck design: **0.00**, below the 0.35 line.
- Stage B and the act-3 stage do not run.

**Secondary.**
- Gate (b) on Stage A decks (descriptive at this size): mean held-out Spearman 0.023, 95% CI [−0.024, +0.073], over 72
  decks. 24 decks gave no Spearman (constant predictions or observations).
- Raw SD of key means: add 4.0 pp, upgrade 2.2 pp (keys with ≥ 20 decks; no remove key reached 20 decks). The noise SE alone at 20
  decks is about 4.6 pp. The extremes are consistent with noise: `add:Sword Boomerang` +9.3 pp, `add:Hemokinesis` and
  `add:Seeing Red` −7.5 pp, each over 20-27 decks.
- **HP is measurable:** `hp:-8` −2.1 pp (SE 1.7) and `hp:-16` −4.7 pp (SE 1.9) Heart win. That is about −0.3 pp per
  entry HP, in line with the entry-HP death gradient of the guard run.

**Interpretation (inference).**
- At the Heart, one card change moves the win rate less than our CRN fights can resolve. Our setup is about 100
  fights per deck at a per-deck difference SD of 0.21, with keys seen on about 16-27 of 96 decks. The true spread of
  per-key effects is indistinguishable from 0.
- The full design would only have helped if that spread were at least about 2-3 pp.
- This agrees with §396 (card-reward decisions move whole-run win rate < ±3 pp) and with P300's finding that their
  Heart table alone was net 0.
- The HP channel is real and cheap to measure. Deck-change prices are not, at this stage and budget.

**Decision rule outcome:** FAIL by the Stage A futility rule. Per the PREREG, deck effects are not cheaply measurable
at the Heart with our combat. Do not build the act-3 stage. The next candidate is #856 (whole-game forks at boss
relics). Philipp decides.

**Not tested:** other stages (act-3 bosses, elites, S&S); production Heart strength (PPc40); context buckets;
multi-card interventions.
