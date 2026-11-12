# Plan commitment on the cheap stack (HPS = H4 + PCS, against §792's H4): result (2026-11-12)

This is the run of [PREREG.md](PREREG.md), frozen in run commit b293a1ba with code 3c85fb26 and binary ca8d9d0b (#1039,
review K PASS). It was launched about 17:45 CET on 40 workers; the last tar arrived about 18:02 CET.

- `verify_campaign.py`: 1,056/1,056 OK, 0 missing, 0 bad, 0 duplicate tars, run b293a1ba, worker DONE 40/40
  (`results/verify.txt`). The claims snapshot is `results/claims.txt`.
- `python3 -I analyze.py UNITS REF_UNITS results/result.json results/claims.txt`, where REF_UNITS is §792's extracted
  tars (`encounter_budget_wholerun_20261112`): 0 bad games, 0 env mismatches, 0 combat aborts, 0 dropped seeds. No game
  needed a manual drop.
- Cost: 25.3 lane-h of game CPU (HPS 24.3, sentinel 1.0; plan 28-36).

## Sentinel

32 of 32 H4 games were identical to §792's, so the verdict is **REUSE_VALID** and §792's 1,024 H4 games are the
control. The same games took 0.96× §792's CPU here.

## Primary (alpha 0.05)

| | H4 (§792) | HPS |
|---|---|---|
| Heart kill | 36.13% | 32.42% |
| Act-4 reach (final floor ≥ 52) | 43.85% | 41.70% |
| Act-4 conversion | 82.4% of 449 | 77.8% of 427 |
| Mean final floor | 40.27 | 39.78 |
| CPU s per run (mean) | 116.8 | 85.4 |
| CPU s per run median / p90 / p99 / max | 88 / 248 / 423 / 3,865 | 62 / 186 / 354 / 567 |
| Gumbel roots searched / simulations per run | 565 / 6.18M | 430 / 4.79M |
| Plan-eligible roots / commits per run | – | 295.8 / 124.2 |
| Losses by final floor ≤ 17 / ≤ 34 / ≤ 51 / ≥ 52 | 198 / 217 / 160 / 79 | 204 / 221 / 172 / 95 |

- **HPS − H4: −3.71 pp, 95% CI [−6.54, −0.88]**; the one-sided 95% bounds are [−6.05, −1.27].
  - 93 seeds kill only with HPS, 131 only with H4.
  - The nonregression SPRT reached CAP at 1,024 (LLR −2.09). The upper bound is below 0, so the verdict is **WORSE**.
  - Act-4 reach −2.15 pp [−4.88, +0.59]; final floor −0.50 [−1.30, +0.33]. The gainer SPRT says NOT_SHOWN.
  - **Cost: 0.73× CPU [0.68, 0.78]** (0.76× machine-corrected) and 0.78× the Gumbel simulations. It commits at 124
    of 296 eligible roots per run (42%), with 24% fewer searched roots. H4's single 3,865 s game raises its mean by
    about 3.7 s; the median ratio is 0.70×.

## Secondary

- **HPS − GP16 (§790, E0's tree, `gp16_contrast.py` → `results/gp16.json`, not gated):** −3.32 pp [−6.15, −0.49] at
  0.60× CPU (machines not corrected).
- **HPS − A4P (§792):** −4.88 pp [−7.71, −1.95] at 0.29× CPU.
- **Where HPS loses.** Losses rise in every act, most in Act 3 (160 → 172) and Act 4 (79 → 95). Act-4 conversion drops
  4.6 pp, about as much as PCH's drop on A4P (§793).
- **Against §793.** The same rule on A4P cost −0.20 pp [−2.83, +2.54] (NOT_WORSE_3PP). The per-seed difference of
  the two contrasts, (HPS − H4) − (PCS − A4P), is −3.52 pp [−7.23, +0.20] on 1,023 seeds (ad hoc, not pre-registered).
  So the cost on the cheap stack is larger, but not significantly larger, than on A4P.

## Interpretation (Inference)

- **A 90% visit share means less in a weaker tree.** On A4P, Act-4 roots are searched with prior playouts. On H4, all
  roots use greedy playouts, and Act 1-3 hallway roots have 4,000 simulations. A share of 90% of fewer or noisier
  visits is less often the edge a fresh search would choose. That may be why the same rule that held on A4P loses
  about 3.7 pp here. It is not tested, and the difference to §793 is itself not significant (CI [−7.23, +0.20]).
- **The saving is real but too costly.** HPS saves about 31 s per run (0.73×), but at about 3.7 pp it trades Heart
  kills worse than the per-encounter budget did: H4 saved about 27 s from GP16 at +0.4 pp.
- **What this means for the cheap stack.** H4 stays the candidate at 117 s and 36.1%. Plan commitment is useful only
  where the inherited tree is strong (A4P and up); there it saves about 19% of the CPU.
- **Possible follow-ups (not proposed for now):**
  - a share threshold that scales with the inherited visit count, for example committing only with at least 8,000
    inherited visits;
  - plan commitment only in Act 4 on a stack whose Act 4 is strong.

## Decision

By the pre-registered rule, HPS is WORSE. There is no default change; the flag stays unset. H4 stays the cheap-combat
candidate. Plan commitment stays an A4P-only result (§793).

Review notes from #1039:
- R1: the gate's control is §792's H4, with GP16 as a secondary contrast. Philipp was told so in the thread at launch.
- R2: there were no manual drops, so there are no dropped seeds whose control outcomes need reporting.
