# Plan commitment, whole runs (PCH hard, PCS at a 90% visit share, against §792's A4P): result (2026-11-12)

This is the run of [PREREG.md](PREREG.md), frozen in run commit e7d36f17 with code 3c85fb26 and binary ca8d9d0b
(#1038, review K PASS). It was launched about 11:58 CET on 40 workers; the last counted tar arrived about 13:37 CET.

- `verify_campaign.py`: 2,079/2,080 OK, 1 missing, 0 bad, 19 duplicate tars, run e7d36f17 (`results/verify.txt`).
  The claims snapshot is `results/claims.txt`.
- **The missing unit is 111378919 PCS.** It ran about 4 h on W40 and 1.4 h as a local copy (8 h timeout), against
  105 s for A4P and 47 s for PCH on that seed. Both copies were stopped at 17:06 CET on Philipp's word ("just drop it").
  - A backtrace of the local copy shows it inside the ordinary search: `searchGumbelRoot` → `getOrCreateNode` →
    `BattleContext::equalForSearch` → `sameMultiset` sorting card vectors. That is a very slow fight, not a plan-commit
    loop (inference: some state with very many cards).
  - Per the PREREG the seed is a listed drop, not imputed (1 of 20 allowed).
  - One seed moves the PCS mean by at most 0.1 pp. Imputing the worst case (an A4P kill that PCS loses) gives a
    one-sided lower bound of about −2.93 pp, so the verdict below holds whatever that game does.
- `verify_campaign.py --extract` refuses while a unit is missing, so the units were taken from the dashboard's
  extraction of every verified tar (one tar per unit; where duplicates exist, CPU in the third digit can differ by
  which duplicate is unpacked, for example PCS 239.8 vs 240.3 s, against GP16 1.67× vs 1.68×; outcomes are identical).
- Share stall: from about 12:20 CET the share hit its 50,000-file limit and uploads stopped. Deleting the `claims/`
  directories of three merged campaigns (their snapshots are in the repo) freed it, and the lanes uploaded their
  backlog. No game result was lost or counted twice.
- `python3 -I analyze.py UNITS REF_UNITS results/result.json results/claims.txt`, where REF_UNITS is §792's extracted
  tars (`encounter_budget_wholerun_20261112`): 0 bad games, 0 env mismatches, 0 combat aborts; drops PCH 0, PCS 1.
- Cost: 116.2 lane-h of game CPU (PCH 45.8, PCS 68.1, sentinel 2.3; plan 95-130).

## Sentinel

32 of 32 A4P games were identical to §792's, so the verdict is **REUSE_VALID** and §792's 1,024 A4P games are the
control. The same games took 1.02× §792's CPU here.

## Primary (alpha 0.025 per arm)

| | A4P (§792) | PCH (hard) | PCS (share 0.9) |
|---|---|---|---|
| Heart kill | 37.30% | 33.40% | 37.15% |
| Act-4 reach (final floor ≥ 52) | 46.29% | 44.04% | 45.75% |
| Act-4 conversion | 80.6% of 474 | 75.8% of 451 | 81.2% of 468 |
| Mean final floor | 40.75 | 39.84 | 40.49 |
| CPU s per run (mean) | 296.7 | 160.9 | 239.8 |
| CPU s per run median / p90 / p99 / max | 142 / 729 / 1,311 / 3,565 | 57 / 429 / 826 / 1,587 | 111 / 622 / 1,194 / 1,526 |
| Gumbel roots searched / simulations per run | 572 / 9.16M | 252 / 4.23M | 424 / 7.16M |
| Plan-eligible roots / commits per run | – | 301.5 / 301.4 | 297.8 / 141.3 |
| Losses by final floor ≤ 17 / ≤ 34 / ≤ 51 / ≥ 52 | 201 / 209 / 140 / 92 | 204 / 238 / 131 / 109 | 204 / 211 / 140 / 88 |

(PCS's table rows use its 1,023 games; its contrast below uses the 1,023 paired seeds, where A4P has 37.34%.)

- **PCH − A4P: −3.91 pp, 95% CI [−6.74, −1.07]** (= the one-sided 97.5% bounds).
  - 91 seeds kill only with PCH, 131 only with A4P.
  - The nonregression SPRT reached CAP at 1,024 (LLR −2.25). The upper bound is below 0, so the verdict is **WORSE**.
  - Act-4 reach −2.25 pp [−5.18, +0.59]; final floor −0.91 [−1.89, +0.06]. The gainer SPRT says NOT_SHOWN.
  - **Cost: 0.54× CPU [0.51, 0.58]** (0.53× machine-corrected) and 0.46× the Gumbel simulations. Committed roots
    cover 301 of 302 eligible roots, 53% of A4P's 572 searched roots.
- **PCS − A4P: −0.20 pp [−2.83, +2.54]** (n 1,023).
  - 98 seeds kill only with PCS, 100 only with A4P.
  - The nonregression SPRT reached CAP at 1,023 (LLR +0.44). The lower bound is above −3 pp, so the verdict is
    **NOT_WORSE_3PP**.
  - Act-4 reach −0.59 pp [−3.32, +2.15]; final floor −0.25 [−1.11, +0.59]. The gainer SPRT reached CAP (LLR −1.26).
  - **Cost: 0.81× CPU [0.76, 0.86]** (0.79× machine-corrected) and 0.78× the simulations. It commits at 141 of 298
    eligible roots per run (47%), 26% fewer searched roots.

## Secondary

- **PCS − PCH: +3.71 pp [+0.98, +6.45]** at 1.49× CPU. The 53% of eligible roots where the plan edge holds less than 90%
  of the inherited visits carry the loss: PCH commits there, PCS searches.
- **Where PCH loses.** Act 1-2 losses (floor ≤ 34) rise from 410 to 442, and Act-4 conversion drops 4.8 pp. The loss is
  spread over the run, not one encounter class.
- **Against E0's GP16 (§790, same seeds, `gp16_contrast.py` → `results/gp16.json`, not gated):**
  - PCH − GP16 −2.34 pp [−5.18, +0.49] at 1.12× CPU;
  - PCS − GP16 +1.37 pp [−1.37, +4.20] at 1.67× CPU.
  - These CPU ratios compare different days' machines without a sentinel correction.
- **R3 (review): commits per run next to Gumbel roots.** PCH searches 252 roots and commits 301 per run; PCS searches
  424 and commits 141. A4P searches 572, so commits plus searched roots are about A4P's roots (553 and 565); the
  shortfall is roots where fights ended differently.

## Interpretation (Inference)

- **The inherited plan is not free at the margin.** The offline check found that plan and search disagree at 26-39% of
  continuation roots, with near-tied final values. Whole runs show that those near ties still cost about 4 pp of Heart
  kills when they are always played without search. Where the plan is confident (≥ 90% of the visits), it is as good as
  a fresh search to this precision.
- **PCS saves about 57 s per run at no measurable Heart cost.** That is the first cheap-combat cut on A4P that keeps its
  Heart rate. It does not reach the goal on its own: 240 s per run against a target of about 140 s.
- **The savings are smaller than the committed-root share suggests.** PCS skips 26% of the roots but only 19% of the
  CPU, because confident plans sit mostly at cheap roots (late in a turn, few legal actions).
- **Next candidates:**
  - PCS on GP16 + H4, the cheap stack. If plan commitment saves about 20% there too, that is roughly 95-100 s per run
    at about GP16's Heart rate.
  - PCS on G16 (prior playouts in Act 1-3 back), paid by the savings: about 410 s per run, aiming at G16's 41%.
  - A lower share (0.8) or a share that scales with the remaining sim budget, between PCH and PCS.

## Decision

By the pre-registered rule, PCS is NOT_WORSE_3PP and PCH is WORSE. There is no default change; the flag stays unset.

- Plan commitment at a 0.9 share joins the cheap-combat stack at 0.81× CPU. Per the PREREG, the next step is a
  combined arm (PCS with H4 on GP16) or PCS on G16. Both need Philipp's go.
- PCH (always commit) is closed at this budget.
- Review notes from #1038:
  - R1: the run had Philipp's typed go (2026-11-12 11:56 CET, "go mit 40 workern").
  - R2: no unit test for the flag. Covered at run time by run_unit's banner and counter checks (rc 75-77); it stays a
    follow-up.
  - R3: commits per run next to Gumbel roots are reported above.
