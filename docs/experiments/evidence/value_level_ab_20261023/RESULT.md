# Value-level 2×2 A/B result: M0 IMPROVED, blend NOT_SHOWN (2026-10-23)

1,024 paired A20 seeds (111340000–111341023), RUN_COMMIT `2b1b269d` (code `ee43726f`), v3 binary `56b29bf8…`,
32 workers × 4 lanes, `schedule queue`. `verify_campaign.py` (`verify.txt`): 1,024 of 1,024 units OK, 0 duplicates,
one run commit. Unit tar hashes: `tars.sha256`. Analysis: `analyze.py` on the `--extract` dir → `result.json`. All
4,096 games are valid (rc 0, complete and integrity-checked footers, banners as required).

| arm | Heart kills | reached Act 4 | kills per Act-4 arrival | deaths in act 1 / 2 / 3 / 4 | mean floor | wall s/run (mean, max) |
|---|---|---|---|---|---|---|
| A X2-B leaf (control) | 238 (23.2%) | 417 (40.7%) | 57.1% | 88 / 235 / 284 / 179 | 43.88 | 746, 2,543 |
| M calibrated leaf (M0) | 252 (24.6%) | 415 (40.5%) | 60.7% | 120 / 263 / 226 / 163 | 42.24 | 707, 2,686 |
| S SR_w1 blend, w 0.1 | 224 (21.9%) | 411 (40.1%) | 54.5% | 82 / 254 / 277 / 187 | 43.52 | 806, 2,586 |
| MS both | 254 (24.8%) | 425 (41.5%) | 59.8% | 128 / 255 / 216 / 171 | 42.15 | 774, 2,851 |

- **Primary, M0 main effect** ((M + MS) − (A + S)) / 2: **+2.15 pp [+0.10, +4.25]**, so **IMPROVED** by the
  pre-registered rule. Stage 0 predicted +1.8 pp if M0's calibration holds between siblings and −6.1 pp if X2-B's
  death price were right.
- **Blend main effect** ((S + MS) − (A + M)) / 2: −0.59 pp [−2.25, +1.07], so **NOT_SHOWN**. Interaction
  (MS − S) − (M − A): +1.56 pp [−1.56, +4.79].
- Simple effects (paired; exact McNemar on the discordant seeds):

  | contrast | Heart kills [95% CI] | discordant | p |
  |---|---|---|---|
  | M − A | +1.37 pp [−1.17, +4.00] | 102 / 88 | 0.35 |
  | S − A | −1.37 pp [−3.91, +1.17] | 80 / 94 | 0.32 |
  | MS − A | +1.56 pp [−1.17, +4.30] | 107 / 91 | 0.29 |
  | MS − S | +2.93 pp [+0.29, +5.47] | 107 / 77 | 0.03 |
  | MS − M | +0.20 pp [−1.86, +2.25] | 60 / 58 | 0.93 |

- Reached Act 4: M0 main effect +0.59 pp [−1.81, +2.98], blend +0.20 pp [−1.61, +2.05].
- **Guard:** mean wall over A's is 0.947 (M), 1.081 (S) and 1.037 (MS), all ≤ 1.10.
- The primary CI clears 0 by two steps of the per-seed grid (0.05 pp each). With 1,023 seeds in, a last seed with a
  negative M0 effect (12% of seeds) would have put the lower edge at 0 or below, so NOT_SHOWN. The last seed
  (111340702) was a kill in all four arms.

## Where the kills come from
- **Deaths move from act 3 to acts 1–2.** Under M0, act-1 deaths rise from 88 to 120 and act-2 deaths from 235 to 263,
  while act-3 deaths fall from 284 to 226. With the blend the moves are 82 → 128, 254 → 255 and 277 → 216.
- **Act 4 is reached as often, but won more often.** Arrivals are flat (417 vs 415). Kills per arrival rise from
  57.1% to 60.7% (S → MS: 54.5% to 59.8%).
- This is the direction stage 0 predicted: three quarters of M0's proxy flips went to the sibling that dies more often
  in rollouts. §522's td2 leaf moved deaths the same way at equal Heart kills; M0 also converts.
- **The search follows the prior more under M0.** The pick leaves the prior's argmax at 5.1% of searched roots, against
  6.5% for A (MS 4.5% vs S 6.4%). The learned OOC stop also fires earlier in every act:

  | act | fast-root simulations, A → M | learned-stop share, A → M |
  |---|---|---|
  | 1 | 369 → 345 | 0.62 → 0.65 |
  | 2 | 413 → 391 | 0.54 → 0.58 |
  | 3 | 466 → 440 | 0.46 → 0.51 |
  | 4 | 576 → 555 | 0.30 → 0.34 |

## Corrections to PREREG (reviewer B's non-blocking notes)
- **Stop features.** The learned OOC stop does not use "root Q differences only". Three of its 14 features are Q gaps:
  top − best other, top − second, and best visited − top. The other eleven (`oocLearnedStopFeatures`) are:
  - log2 of the simulations;
  - the top and second visit shares and their gap;
  - the top two priors, and whether the prior's top is the visit top;
  - the number of candidates;
  - act, floor and screen.
- **Stop timing.** PREREG expected the stop to fire later in acts 1–2 and earlier in act 3. It fired earlier in all
  four acts.
- **Exploration scale.** M0 rescales Q, so it also changes PUCT's effective exploration: the prior term c·P·√N/(1 + n)
  now competes with smaller Q gaps. A death-driven gap shrinks from about 0.75 to about 0.2 in act 1. That fits the
  extra prior-following and the earlier stops above. The A/B measures M0 as deployed, this effect included, and
  cannot separate it from the death price.

## Run notes
- **Retries.** Container restarts killed many units: 121 needed a second claim attempt, 15 a third and 4 a fourth. No
  unit ran twice. The deaths clustered at the workers' 2-hour wait boundaries; later briefs tell workers to re-arm the
  wait in the same turn.
- **Wall.** The campaign took 23:07Z → 09:32Z, 10.4 h against 7 h planned.
- **Last unit.** Unit 111340702 needed three attempts. On the third (w16) it ran 2.8 h: all four arms reach and kill
  the Heart, at 2,543–2,851 s each.
- **Determinism check.** A local rerun of that seed (same binary and inputs, the four arms in parallel) gave
  byte-identical decision, state, outcome and CTM records. Only the header line differs, because it records file
  paths.
- **Records.** The four arms' records (policy targets at full-budget roots, CTM rows) stay in the unit tars on the
  share (`/mnt/project-files/value-level-ab/units`, 246 MB).

## Inference
- **M0 helps.** At A20 with today's stack, ending rollout3 leaves in calibrated Heart-kill probability kills the Heart
  more often than raw X2-B. The gain, +2.15 pp, is about what stage 0 predicted from M0's flips alone.
- **Why.** Together with the death shift, this says X2-B's implied death price (3–8× the calibrated one) makes the
  search too cautious in acts 1–2. Accepting more early risk pays off in act 4.
- **How much is uncertain.** The size lies anywhere from about 0 to 4 pp. Part of the gain may come through the
  exploration scale rather than the death price.
- **The SR_w1 blend at w 0.1 does not help** (−0.6 pp). With M0 it is neutral (MS − M +0.2 pp). The newer head
  SR_crn_r2_s2_ep20 has not been played.

## Decision
- No default change from this run alone; Philipp decides (PREREG).
- Before M0 could become a default, PREREG requires two things:
  - the learned OOC stop checked on the new Q scale, since it fires earlier under M0;
  - a confirmation on fresh seeds.
- The stage 1–2 replay (`../value_leaf_compare_20261023`, seeds 111360000–111360255, running) adds the per-root view:
  which of M0's flips the referees score as gains. Its predicted Δ for M0 is the first prospective test of the
  decision metric against this A/B's M − A (+1.37 pp).
