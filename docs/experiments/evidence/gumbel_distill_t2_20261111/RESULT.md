# Gumbel distillation T2: result

[PREREG](PREREG.md) · code 966de5f7, RUN 9896e76c, binary 7f2800f0 · 40 cloud workers, 2026-11-11 18:45-20:25 CET ·
`analyze.py NEW_ROOT REF_ROOT results/result.json results/claims.txt` (NEW_ROOT = `verify_campaign.py --extract`,
REF_ROOT = §775's extracted `gumbel-wholerun` units); pairs `results/pairs_T2P.csv`.

## Campaign

- `verify_campaign.py`: units OK 1,056 / 1,056, missing 0, bad 0, duplicates 0, worker DONE.json 40 / 40, one run commit.
- Sentinel: **32 of 32** G16 games identical to §775's by fingerprint → **REUSE_VALID**. §775's 1,024 G16 games are the
  control.
- 1,024 T2P games, all rc 0 with every log check; 0 dropped, 0 env mismatches, 0 combat aborts. Longest game 45 min.

## Primary: Heart kill T2P − G16 (1,024 paired seeds)

| | G16 (§775) | T2P | d (95% seed bootstrap) |
|---|---|---|---|
| Heart kill | 41.21% | 39.84% | **−1.37 pp [−4.30, +1.46]** |
| act-4 reach | 49.22% | 49.41% | +0.20 pp [−2.64, +3.03] |
| mean final floor | 41.58 | 40.95 | −0.63 [−1.60, +0.31] |

Discordant seeds: T2P only 109, G16 only 123.

**Gate (gainer SPRT, H0 0, H1 +2 pp): NOT_SHOWN.** The LLR crossed the lower bound at the look at 896 seeds
(LLR −3.17). Secondary nonregression SPRT (−1.5 pp): CAP at 1,024 (LLR −0.42); one-sided 95% bounds [−3.81, +1.07] pp.

## Cost

- CPU per run T2P / G16: **1.049 [0.997, 1.103]**; corrected for machine speed by the sentinel (this campaign's G16
  CPU 1.061x §775's on the 32 seeds): **0.99**.
- Gumbel simulations per run 0.981 [0.950, 1.012] and Gumbel roots per run 0.980 (slightly shorter runs).
- Net forwards per run: 12,387 tree, 6.1 root (21.6 per Gumbel root); roots with ≥ 17 actions are rare, as expected.
- The smoke's 1.2-1.4x per root was measured on a loaded 4-core container; the campaign's cost is ≈ 5% at most.

## Reading

The distilled net (T1's best per-boss nets and the generalist) as Silver's prior at heavy tree nodes (≥ 256 visits)
and at wide roots does not improve §775's G16 + mb4 teacher: the point estimate is −1.4 pp, and +2 pp is excluded by
the SPRT. A small regression (to about −4 pp) is not excluded. Together with §773 (net root prior NO_GAIN) this says
the net's policy does not add information the 16k-simulation search lacks; at nodes with ≥ 256 visits the search's
own statistics dominate the prior bonus anyway (weight 400 / (n + 1)).

Not tested here: the net's value head as leaf value / Q-init (the larger lever, §656/§675 risk), the net prior at
lower K (cheaper nodes, where the prior matters more), the net in cheaper search (e.g. D's 10k learned-stop combat,
where a better prior should matter more than under G16).

## Decision

Per PREREG: NOT_SHOWN, no default change. The leaf-value test is the next candidate (needs calibration first and
Philipp's go).
