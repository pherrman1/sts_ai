# Rollout prior on G16 targets, stage 2: playout harness (pre-registration, 2026-11-15)

Stage 1 ([PREREG](../rollout_prior_gumbel_20261115/PREREG.md), [RESULT](../rollout_prior_gumbel_20261115/RESULT.md),
ledger §804) found two playout-prior candidates trained on G16 + mb4 visit shares: V (`students/rp_V.txt`, sha256
b366f6af…) and its boss fine-tune X-B (`students/rp_X-B.txt`, 34c1acf4…). Root regret does not show that playouts
improve; this stage measures it. Philipp, this thread, 2026-11-15 21:29 CET: "go auf 32 workers".

## Harness

§798's ([RESULT](../cheap_rollouts_ladder_20261113/RESULT.md)) unchanged: code f9601609, binary 5a659bd8 (x86-64-v3),
`one_combat silverazgen` with `STS_AZGEN_ROLLOUT_LADDER` on §797's 256 games (seeds 111980000-111980255). The
played games are bit-identical to §797 and §798 (sentinel). After each played search at a multi-edge boss / Act-4
root, fresh Gumbel searches are run once per arm; they change only the playout policy:

| arm | playout policy | sims |
|---|---|---|
| asplayed:4000 | g7f_E argmax every step (production; control, arm index 0 = §798's salt) | 4,000 |
| st:4000 | V argmax every step | 4,000 |
| ste:4000 | X-B argmax every step (all 11 playout encounters mapped to X-B) | 4,000 |
| st:16000 | V | 16,000 |

Root prior, tree prior and root table stay g7f_E in every arm. From §797 (same roots): p1:1000 ... p1:16000, g7f_E
playouts. [record_env.sh](record_env.sh), [run_unit.sh](run_unit.sh), [campaign.manifest](campaign.manifest),
32 workers, 4 lanes each.

## Measure

Per root, loss(arm) = the played G16 tree's best max-backed Q among visited edges minus the max-backed Q of the
arm's pick (§798's definition, Silver score units); rows need every arm's pick visited in the played tree.
[analyze.py](analyze.py), 10,000 run-clustered bootstrap resamples.

- **Primary:** V@4k = mean(loss st:4000 − loss asplayed:4000) and XB@4k = mean(loss ste:4000 − loss asplayed:4000),
  99 % CI. **BETTER** if the CI is below 0, **WORSE** if above 0, else **NOT_SHOWN**.
- Secondary: V@16k = st:16000 − p1:16000; each arm's distance to the P1 CPU frontier (caveat: student arms run
  through `nativeSilverPolicyPriorWith`, without g7f_E's argmax hook, so their CPU is overstated); per group
  (Act 1-2 bosses, Act 3 bosses, Act-4 elite, Heart) and per encounter; fold 4 (seed % 5 == 4).
- Checks: sentinel (roots and `chosen` equal to §797; > 8 bad runs = INVALID); students in each run's manifest by
  name and sha256; > 20 dropped runs = INCOMPLETE; calibration p1:1000 − p1:16000 gap, 95 % CI above 0, else
  INVALID_METRIC (labels withheld when not OK). asplayed:4000 picks vs §798's asplayed:4000 (same arm index and
  salt; expected identical).

Reading: the reference tree was built with g7f_E playouts, so it favours g7f_E-like picks (conservative for the
candidates). The asplayed and student arms use different search salts, so their difference includes search noise,
which the bootstrap covers.

## Decisions

- V@4k or XB@4k BETTER: propose stage 3 (a production option for a separate playout-prior model, then a whole-run
  SPRT gate of G16 with it vs §775's G16 and of G8 with it vs G16); needs Philipp's go.
- Both NOT_SHOWN or WORSE: root targets do not transfer to playouts; the line stays parked. The alternative
  (PREREG stage 3) is training on captured playout states labelled by short searches (DAgger-style).
- Negative results go to the ledger either way.

## Cost

§798 took 137 lane-hours for 7 arms including greedy 64k; this ladder has 28k sims per root instead of 164k, so
roughly 70-100 lane-hours: under 1 h of queue on 32 workers × 4 lanes, then the slowest unit (up to ~2.5 h).
