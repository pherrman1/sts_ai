# Rollout prior stage 3: §775's G16 + mb4 with candidate V in all four prior roles (GV) against §775's G16 + mb4 (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen with the PREREG in the run commit 44a25e76
(before any unit had run), output `results/result.json` and `results/pairs_GV.csv`. Descriptive breakdown:
`breakdown.py` (not pre-registered; §799's with the arm renamed and the bootstrap seed 20261115), output
`results/breakdown.json`. Prelaunch review: K, PASS (N1: read the CPU ratio also as "V changes the game path").

## Run

- Run commit 44a25e76 (code ba705ab4, binary 97aec5b5 from the share's binary cache), 32 workers × 4 lanes, queue. The
  first game started at 22:58 CET on 2026-11-15 and the last finished game ended at 00:44 CET on 2026-11-16. The 1,055
  finished games sum to 158.2 lane-hours. The median game took 5.2 min and the longest 52.5 min (GV-111378543).
- 1,056 claims, each unit claimed once (no `.a2`). Claims snapshot: `results/claims.txt` (taken 05:17 CET).
- **One drop: 111378919_GV.** Worker 32 claimed it at 00:06 CET. Its heartbeat kept coming until 04:33 CET, so the game
  ran for at least 4.5 h against a longest finished game of 52.5 min; then the heartbeat stopped and no tar arrived.
  It is a claim without a result and counts as dropped (PREREG: listed, never imputed; the bound is 20). §775's G16
  game on this seed lost (final floor 50), so a GV win there would move d by +0.1 pp; the verdict below holds either way.
- `verify_campaign.py`: 1,055 of 1,056 units OK, 1 missing (111378919_GV, above), 0 bad, 0 duplicates, 0 tars for
  unknown units, all on run 44a25e76. Worker DONE files: 0/32, since the workers' queue still saw the one open claim
  when they moved on to the next campaign (`results/verify.txt`).
- `analyze.py` (NEW_ROOT = this campaign's units, newest tar per unit, REF_ROOT = §775's D, G16 and G32 units,
  CLAIMS_LIST = the snapshot): 0 bad games, 0 env mismatches, 0 combat aborts, 1 dropped seed.

## Sentinel and control reuse

32 of 32 sentinel G16 games are identical to §775's: **REUSE_VALID**. §775's 1,024 G16 games are the control. The
sentinel's CPU per run is 6.0% higher than §775's on the same games (machine speed).

## Primary

| | G16 + mb4 (§775) | GV |
|---|---|---|
| root prior, tree prior, prior playouts, rollout root table | g7f_E | V (`students/rp_V.txt`) |
| Heart kill | 41.25% | **37.83%** |
| reach Act 4 (floor ≥ 52) | 49.27% | 46.24% |
| mean final floor | 41.58 | 40.13 |
| CPU per run | 512 s | 543 s (1.06×) |

(G16's numbers are on the 1,023 analysed seeds; on all 1,024 its Heart kill is 41.21%.)

GV − G16 = **−3.42 pp [−6.26, −0.59]** (95% seed bootstrap, 10,000 resamples). On 92 seeds only GV kills the Heart and
on 127 only G16 does. The one-sided 95% bounds are [−5.77, −0.98]. The nonregression SPRT reached CAP at 1,023 seeds
(LLR −1.92; it touched −2.12 at 896 seeds, short of −2.944). The upper bound is below 0, so the verdict is **WORSE**.
The gainer SPRT accepted H0 at 640 seeds (NOT_SHOWN).

Cost (co-primary, 95% CIs):

- CPU per run, GV / G16: **1.060× [1.005, 1.118]**, or 0.999× after correcting for machine speed with the sentinel.
- Gumbel simulations per run: 0.978× [0.947, 1.010] (roots 0.98×). V costs about what g7f_E costs; GV's games are a
  little shorter because they die earlier (K's N1: the ratio is game path, not only kernel cost).
- CPU per run, quantiles (median, p90, p99, max): GV 311 / 1,304 / 2,391 / 3,147 s; G16 379 / 1,163 / 1,955 / 3,036 s.

## Secondary (95%, not gates)

| contrast | Heart (pp) | Act-4 reach (pp) | only first / only second | CPU ratio |
|---|---|---|---|---|
| GV − D (§775's A20 default) | +6.16 [+3.23, +9.09] | +5.08 [+2.15, +8.02] | 148 / 85 | 2.15× |
| GV − G16, the budget curve's 512 seeds (111378256-111378767) | −2.54 [−6.45, +1.37] | −2.93 [−7.03, +1.17] | 46 / 59 | 1.10× |
| GV − G16, the other 511 seeds (`breakdown.py`) | −4.31 [−8.41, −0.20] | | | |

**Act-4 conversion** (Heart kills per arrival, arrival = final floor ≥ 52):

| | Act-4 arrivals | Heart kills | kills per arrival |
|---|---|---|---|
| G16 | 504 | 422 | 83.7% |
| GV | 473 | 387 | 81.8% |

On the 371 seeds where both arms reach Act 4, the rates are 88.4% for G16 and 86.0% for GV. The difference is
−2.4 pp [−6.2, +1.6].

## Where GV loses (descriptive, not pre-registered)

`breakdown.py`: deaths by section of the final floor, hazard = deaths among runs reaching the section, GV − G16 with a
95% seed bootstrap (4,000 resamples).

| section | GV | G16 | GV − G16 (pp) |
|---|---|---|---|
| act 1, floors 1-15 | 106 / 1,023 | 96 / 1,023 | +1.0 [−0.6, +2.5] |
| act-1 boss (16) | 90 / 917 | 89 / 927 | +0.2 [−1.7, +2.1] |
| act 2, floors 17-32 | 160 / 827 | 129 / 838 | **+4.0 [+1.2, +6.8]** |
| act-2 boss (33) | 68 / 667 | 63 / 709 | +1.3 [−1.1, +3.7] |
| act 3, floors 34-49 | 56 / 599 | 60 / 646 | +0.1 [−2.7, +2.8] |
| act-3 boss 1 (50) | 34 / 543 | 42 / 586 | −0.9 [−3.4, +1.6] |
| act-3 boss 2 (51) | 36 / 509 | 40 / 544 | −0.3 [−3.2, +2.6] |
| act 4 (52-56) | 86 / 473 | 82 / 504 | +1.9 [−2.3, +6.1] |

Act-4 runs that did not kill the Heart, by final floor: 52 (no three keys) GV 8 / G16 7; 55 (Shield and Spear) 6 / 2;
56 (the Heart) 72 / 73. Heart kills by which arm reached Act 4: both 371 seeds (G16 328, GV 319); only G16 133 (94
kills); only GV 102 (68 kills).

## Reading (Inference)

- V in all four roles is worse than g7f_E: −3.42 pp [−6.26, −0.59] at equal CPU. Stage 1's root-regret gain on G16's
  own roots (2.449 → 1.884 Q, §804) does not reach the game, in line with stage 2 (§807, V as playout policy +0.29 Q
  worse).
- The loss sits in the hallway, not in the bosses: act 2's normal fights lose +4.0 pp [+1.2, +6.8] more runs; the boss
  sections and Act 4 are within noise. One possible reason (not measured): V was trained only on G16 + mb4 roots, the
  states of the played path, while as tree prior and in playouts it is asked about deeper states it never saw. This
  is a reading of the breakdown, not a role attribution: GV swaps all four roles at once (PREREG, K's N1).
- The early dashboard numbers (47.8 vs 34.8% after 23 seeds) were noise from a short, biased prefix, as said then.
- §785's caveat (every arm against these 1,024 G16 games came out 2-5 pp below them) applies here too, but GV − G16 is
  the most negative of them, and its upper bound is below 0.

## Decision

**WORSE** (Heart kill −3.42 pp [−6.26, −0.59] at 1.00× machine-corrected CPU). No default change (PREREG: none in any
case). g7f_E stays the prior in all four roles. Following the PREREG, the next step is training on captured tree and
playout states labelled by short searches (DAgger-style): the prior data factory (`prior_factory_20261116`, Philipp's
go 2026-11-16 00:46 CET) collects them. The single-role arms are not run.

Seeds: §775's 111378256-111379279 reused (no new seeds). Cost: 158.2 lane-hours plus the dropped game's ≥ 4.5 h.
