# Clean value labels, stage 4: act-end capture on 256 replays (2026-10-30)

Plan: [doc](https://claude.ai/artifact/GpnikPukaCYWFwn7VLVj6V) (uniform scheme, Philipp 2026-10-29 22:36Z). Go: Philipp
2026-10-30 11:59Z, "Stufe 4 auf 44 workern".

## What runs
`run_unit.sh` and `a4_fork.py` are run 1's files verbatim
([`../value_clean_labels_run1_20261029`](../value_clean_labels_run1_20261029/README.md), §720), same code commit and
binary, with CAPTURE = 1 and K = 0: one base game per unit at today's A20 default, with the stage-1 act-end capture
(`STS_OOC_CAMPFIRE_PRICE` + `_RECORDS=1 _ACT_END_ONLY=1 _SCREENS=all _TOP=3 _N=64`, observer only). No forks.

## Seeds
256 replays of used seeds, the run-1 base games not yet captured: 111387032-111387255 and 111384000-111384031.
Capture does not change play (run-1 smoke and the 32 pilot units), so each game here is the run-1 base game with
the same seed. Its real outcome and its states are already in run 1, which is what the per-act level calibration
uses. No new seeds.

## Cost
Pilot units averaged about 21 min wall per capture game, so about 256 × 21 min ≈ 90 lane-h. On 44 workers × 4 lanes
that is about 30 min plus setup. Storage is about 3.6 MB gzip per game, about 1 GB in total, on the share (10 GB
quota; the share currently uses about 6 GB).

## Analysis (stage 5, offline, after verify)
Data: these 256 games plus the 32 pilot games make 288 captured games.
1. **V_A4:** §720's GC model refit on all Act-4 data, plus the act-4 roots' rollout labels (to the game's end).
2. **Backward fits, k = 3, 2, 1:**
   - Act-k label = mean over 64 act-end rollouts, with 0 after a death and V_{k+1}(end record) otherwise.
   - Fit V_k as a GBM on the public record, with screen features dropped for end-record scoring.
   - Then calibrate the level per act on run 1's real outcomes at act-k states.
   - The split is by seed % 4 as before.
3. **Gate** (plan stage 5, fixed before this run), on TEST seeds:
   - Map roots: concordance ≥ +0.02 over X2-B+M0 (CI > 0).
   - Real log loss not worse than X2-B+M0 on run-1 states.
   - 0 HP inversions, upgrade mispricing < 29.7% (§705).
   - The exact scripts are written and committed before the data is read.
