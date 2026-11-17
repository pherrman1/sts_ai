# Simulation-balanced playout policy SBC instead of V as G16 + mb4's prior-playout policy, against §815's GP (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen with the PREREG in run commit b5d868c7
(88a379be only raised the worker count, before launch), output `results/result.json` and `results/pairs_GS.csv`.

## Run

- Run commit 88a379be (code 432bfae4, binary 85a6cf3e, §815's), 40 workers × 4 lanes, queue. Launched
  2026-11-16 21:30 CET; first unit delivered 21:33 CET, last 02:55 CET on 2026-11-17. The 1,053 finished games sum
  to about 311 lane-hours. The longest finished game took 2.1 h (GS-111378632).
- Worker containers restarted repeatedly from about 23:00 CET. A restart kills the game, and the claim's heartbeat goes
  stale. The author marked stale claims (heartbeat older than 15-20 min) `failed`, so idle workers took the next attempt
  at once instead of after the 90-minute lease. 63 claims are attempts 2-4. Games are deterministic, so a rerun gives the same game.
  Claims snapshot: `results/claims.txt`.
- Three GS units, 111379027, 111379246 and 111379259, died in all four attempts (`worker.sh` QMAX 4). Each had run
  longer than the containers lived. A local rerun in the author's container died in that container's restart too.
  They are **dropped seeds** (the PREREG allows up to 20). Their §815 GP games are one Heart kill (111379027) and two
  early deaths (floors 20 and 33).
- `verify_campaign.py` (`results/verify.txt`): 1,053 of 1,056 units OK, the 3 above missing, 0 bad, 2 duplicates (the
  first tar in name order is used), all on run 88a379be. Its `--extract` runs only when every unit is OK, so the author
  extracted the same tars (first per unit in name order) with a few lines of Python.
- `analyze.py` (NEW_ROOT = these units, REF_ROOT = §815's units, CLAIMS = the snapshot, REF775 = §775's units): 0 bad
  games, 0 env mismatches, 0 combat aborts, 3 dropped seeds.

## Sentinel and control reuse

32 of 32 sentinel GP games are identical to §815's: **REUSE_VALID**. §815's 1,024 GP games are the controls. The
sentinel's CPU per run is 3.6% higher than §815's on the same games (machine speed).

## Primary

| | GP (§815) | GS |
|---|---|---|
| prior playouts (boss rooms, Shield and Spear) | V (`rp_V.txt`, 128/64) | SBC (`rp_SBC.txt`, 256/128) |
| root prior, tree prior, rollout root table | g7f_E | g7f_E |
| Heart kill (1,021 paired seeds) | 43.58% | **44.37%** |
| reach Act 4 (floor ≥ 52; per arm, all its games) | 50.98% | 51.81% (paired d +0.78 pp [−1.57, +3.13]) |
| mean final floor | 42.05 | 41.96 (paired d −0.10 [−0.73, +0.53]) |
| CPU per run | 578 s | 1,080 s (1.87×) |

GS − GP = **+0.78 pp [−1.67, +3.23]** (95% seed bootstrap). On 86 seeds only GS kills the Heart and on 78 only GP
does. The one-sided 95% bounds are [−1.27, +2.84]. Both SPRTs reached CAP (nonregression LLR +1.46, gainer −0.28).
At CAP the lower one-sided bound is below 0, so there is no GAIN. It is above −3 pp, so the verdict is
**NOT_WORSE_3PP**. That is the label `analyze.py` prints, and the PREREG's combined rule gives the same.

With the three dropped seeds counted at either extreme, the difference over all 1,024 seeds would lie between
+0.68 pp and +0.98 pp. The verdict does not depend on them.

Cost (co-primary, 95% CIs):

- CPU per run, GS / GP: **1.87× [1.78, 1.96]**, or 1.81× after correcting for machine speed with the sentinel.
- Gumbel simulations per run: 1.000× [0.979, 1.023] (roots 1.00×). The whole extra cost is SBC's larger network per
  playout step, at equal simulations.
- CPU per run, quantiles (median, p90, p99, max): GS 880 / 2,435 / 4,005 / 7,664 s; GP 464 / 1,258 / 2,124 / 7,822 s.

## Secondary (95%, not gates)

| contrast | Heart (pp) | CPU ratio |
|---|---|---|
| GS − G16 (§775's G16 + mb4) | +3.13 [+0.59, +5.68] | 2.11× |
| GS − GP, first 512 seeds | −0.39 [−4.10, +3.12] | 1.86× |

Act-4 conversion: GP 446 kills from 522 arrivals, GS 453 from 529. On the 449 seeds where both arms reach Act 4,
the rates are 87.5% for GP and 88.0% for GS. The difference is +0.4 pp [−2.9, +3.6].

## Interpretation (Inference)

SBC lowered the debiased playout value error by about 10% against V (617 vs 688, −71 [−125, +20]; PREREG table). In
whole runs that gives +0.78 pp at equal simulations. The sign agrees with the offline measure, but the size is within
noise, and the run costs 1.87× the CPU. The offline value error ranked V over g7f_E, and §815 confirmed that ranking.
SBC's further offline gain over V is smaller and has a heavy tail. This gate cannot resolve a game difference that small.

Review notes carried over:
- F1 (prelaunch review): `analyze.py` has no GAIN-at-CAP branch, so the PREREG's rule was applied by hand. The lower
  one-sided bound is −1.27 pp, so the rule does not give GAIN.
- N1: SBC was selected on the same 30,118 validation roots that the PREREG table reports. The offline numbers are
  therefore slightly optimistic for SBC.

## Decision

**NOT_WORSE_3PP.** By the PREREG, the offline measure's further gain does not show in games at this size, so the
playout value error stays a pre-filter only. It does not select between policies whose offline difference is about
10%. No default change. SBC is not an equal-CPU candidate either. It costs 1.87× the CPU, and an equal-CPU check against
GP was not run. Seeds: none new (§775's). Cost: about 311
lane-hours plus lost attempts.
