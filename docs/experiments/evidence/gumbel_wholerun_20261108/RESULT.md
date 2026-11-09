# Gumbel teacher in whole runs: A20 default combat vs the Gumbel root with max backup at 16k / 32k / 64k (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen, output `results/analysis.json`, claims
snapshot `results/claims.txt`.

## Run

- Run commit 68fe06ba (code 5665d5ae, binary 0eabb014), queue schedule, 4 lanes per worker, net-0420 (sha 8c0bd16c)
  as the whole out-of-combat policy.
- Philipp's go was for 40 workers. W1-W33 started at 04:50-04:56 CET on 2026-11-09. W34-W40 failed at start with the
  session limit and never claimed a unit. They were found at 08:35 CET, when the contiguous seed prefix stayed at 16,
  and restarted at 08:37 CET. Their static shares (from seed 111378272 on) were claimed then or stolen by others.
- First tar 04:53 CET, last 12:38 CET. Game walls add up to 956 lane-hours (D 72, G16 146, G32 248, G64 491).
- No early stop. Philipp (09:27 CET): "die seeds Durchlaufen lassen und nicht stoppen falls sprt Triggert". So every
  seed was claimed, and the claims rule of the PREREG changes nothing.
- 2,047 units were claimed once and one twice (`111379155_low`: the first attempt's container was lost; only the second
  uploaded a tar).
- `tools/cloud/verify_campaign.py`: 2,048 of 2,048 units OK, 0 missing, 0 bad, 0 duplicates, 0 unknown tars, all from
  run 68fe06ba (39 of 40 workers wrote `DONE.json`).
- `analyze.py`: 4,096 games (1,024 per arm), **0 bad** (log checks and env), **0 aborts**, **0 dropped seeds** in every
  contrast. No game ran into the 8 h timeout. The longest walls were D 28 min, G16 51 min, G32 1.7 h and G64 2.4 h.
  G32 had 7 games over 1 h and G64 had 129.

## Per arm

| arm | Heart kill | act 4 reached | mean floor | CPU min / run | CPU ratio |
|---|---|---|---|---|---|
| D (learned stop, 10k) | 31.64% (324) | 41.1% | 38.5 | 4.2 | 1.00 |
| G16 + mb4 | **41.21%** (422) | 49.2% | 41.6 | 8.5 | 2.03 |
| G32 + mb4 | 40.82% (418) | 49.8% | 41.9 | 14.5 | 3.44 |
| G64 + mb4 | 40.43% (414) | 49.7% | 41.5 | 28.8 | 6.83 |

## Primary: X − D per seed (SPRT gainer d1 +2 pp, alpha 0.05/3, beta 0.05, look 64, cap 1,024)

| contrast | n | d (95% CI) | (1 − alpha) CI | SPRT | crossed at | verdict |
|---|---|---|---|---|---|---|
| G16 − D | 1,024 | **+9.57 pp [+6.64, +12.50]** | [+5.96, +13.09] | PASS | 576 seeds | **GO** |
| G32 − D | 1,024 | **+9.18 pp [+6.25, +12.21]** | [+5.47, +12.99] | PASS | 768 seeds | **GO** |
| G64 − D | 1,024 | **+8.79 pp [+5.86, +11.82]** | [+5.27, +12.40] | PASS | 704 seeds | **GO** |

"Crossed at" is `analyze.py`'s SPRT stop (`n_stop`, ascending seed order, looks of 64): the gate decided there, and
the remaining seeds only narrow the intervals. Each contrast's sprt_gate nonregression: NOT_WORSE.

Discordant seeds (X wins only / D wins only): G16 171 / 73, G32 177 / 83, G64 171 / 81.

## Secondary (95% CIs, not gates)

- G32 − G16: −0.39 pp [−3.22, +2.44] (G32 only 109, G16 only 113).
- G64 − G32: −0.39 pp [−3.22, +2.44] (G64 only 111, G32 only 115). The two intervals are equal because both
  differences are 4 of 1,024 seeds and the bootstrap quantiles fall on the same grid of 1/1,024. The discordant
  counts differ.
- Act-4 reach X − D: G16 +8.1 pp [+5.2, +11.0], G32 +8.7 pp [+5.6, +11.7], G64 +8.6 pp [+5.6, +11.6]. Mean final
  floor: G16 +3.1 [+2.1, +4.1], G32 +3.4 [+2.4, +4.5], G64 +3.0 [+2.0, +4.0].
- Halves of the seed block (descriptive): G16 − D +9.6 pp in both halves; G32 +8.4 / +10.0; G64 +9.0 / +8.6.

## Interpretation (Inference)

- Playing every fight of the run with the Gumbel root and max backup raises the A20 Heart kill rate of net-0420's runs
  by about 9-10 pp, from 31.6% to about 41%. That is more than twice the unpaired D0/D1 estimate (+4.4 pp, Gumbel at
  16k without max backup, student_sel OOC, other seeds), and far above the HP-price extrapolation (about +1.5 pp,
  §763). About 8 pp more runs reach act 4, and more of those that reach it kill the Heart (D 324 of 421 = 77%, G16
  422 of 504 = 84%; not tested). In this test, HP per elite or boss fight (§770/§772/§774) undersells the teacher by a wide margin.
- More budget does not pay at the run level. On Baalorlord's states 32k and 64k with max backup lost 0.25 and 0.46 HP
  per fight less than 16k (§774), but in whole runs G32 and G64 are both 0.4 pp below G16, and neither step is
  resolved (±2.8 pp). An effect of about +1 pp per budget doubling is not excluded. G16 + mb4 is the best arm per CPU
  by far: 2.0× D's CPU for +9.6 pp.
- D's 31.6% is not comparable to net-0420's 25.49% in §760, which used other seeds and another setting. Only the
  paired contrasts here are tested.
- Caveats fixed in the PREREG: one Gumbel setting (k 16, c_visit 50, c_scale 1) and one max-backup setting (min 4) at
  every budget; net-0420's out-of-combat play is fixed, so the stronger combat also changes which states it reaches;
  the Gumbel arms use 1.6-6.4× D's nominal budget, so this is the teacher as used, not equal CPU.

## Decision

- **GO for G16 + mb4, G32 + mb4 and G64 + mb4** against the A20 default combat in whole runs with net-0420.
- No default change on this result (PREREG). G16 + mb4 is the candidate for (a) the combat teacher of the AZ loop and
  (b) a production default proposal. (b) needs Philipp's call on 2× combat CPU and its own gate with the production
  out-of-combat stack (student_sel and OOC MCTS).
- The Gumbel tuning scout (#1019) uses g16 + flat16000 + mb4 as its control, which is this campaign's G16 arm.
- Seeds: 111378256-111379279 (1,024) used, smokes 111379280-111379289.
- Cost: 956 lane-hours, 04:53-12:38 CET on 33 then 40 workers.
