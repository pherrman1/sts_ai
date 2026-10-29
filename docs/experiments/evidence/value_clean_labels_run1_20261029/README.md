# Clean value labels, run 1: Act-4 entry forks + pilot act-end capture (2026-10-29)

Follows [stages 0-2](../value_clean_labels_20261029/README.md) (§719). Stage 2 failed: V_A4 learned from 2,337
single-outcome Act-4 entries did not beat the recalibrated Act-4 CTM. Philipp chose "both in parallel" and gave
the go for this run with up to 44 workers (2026-10-29 16:44Z).

## What runs
One unit per used seed, at today's A20 default (§712 arm A environment, verbatim from
[`../ooc_root_quality_20261028/run_unit.sh`](../ooc_root_quality_20261028/run_unit.sh)), `heartoutcomegen`:

1. **Base game.** On the 32 pilot seeds it also runs the stage-1 capture: `STS_OOC_CAMPFIRE_PRICE` with
   `_RECORDS=1 _ACT_END_ONLY=1 _SCREENS=all _TOP=3 _N=64`. This is an observer only and play is unchanged.
2. **Act-4 entry forks.** If the base game reaches Act 4, the unit plays K = 4 more games from its first Act-4
   decision, with `STS_OOC_FORCE_DECISION=INDEX:SALT:-`. That is the production choice, SALT 1-4, and the hidden
   future redrawn exactly as in the §710 forks (#882). Forks run without capture. Each fork has to replay the
   base game's states and decisions identically up to INDEX (`a4_fork.py prefix`). A mismatch fails the unit
   (rc 87).
3. **Output.** `a4-SEED.json` holds the entry record (heart1-public-record-v2) and the outcome of every game from
   that entry (salt 0 = base). The game jsonls are kept too, so every state inside Act 4 can be used later.

No new code. The binary is main at `code_commit`, and both research flags are existing, reviewed and default off.

## Seeds
Replays of used seeds only, no new seeds: card-rule-ab 111387000-111387255 (the pilot capture is 111387000-031)
and expert-anchored-ab 111384000-111385023. That is 1,280 units ([`units.txt`](units.txt)). Today's main is not
bit-exact with those campaigns' games (FREEZE note of `ooc_root_quality_20261028`), so the trajectories are new.
The split for every fit stays by seed % 4, as in stage 2.

## Cost (estimate)
- Arm A of card-rule-ab took 14.3 min mean wall per game (4 lanes on a 4-CPU container).
- About 45% of games reach Act 4, so each one adds 4 forks of about 15 min (replay up to the entry plus Act 4).
- That gives about 41 lane-min per unit, 1,280 × 41 ≈ 870 lane-h. On 44 workers × 4 lanes, that is about 5 h
  plus the tail.
- A unit can take up to about 5.5 h (base game 65 min max × 5).
- The capture adds about 5-15 core-h over the 32 pilot units.
- Storage: about 30 kB gzip per game, about 5 MB per capture game. 1,280 tars and the claims total roughly
  0.4 GB and about 6k files.

## Analysis (after verify; offline, nothing more to launch)
- **V_A4 refit.** Use the same features, model family and split as stage 2 (`fit_a4.py`). The label for each run-1
  entry is its mean over 5 games. The stage-2 entries stay, each with one label. The run-1 TEST set is again
  seed % 4 = 3, and the comparison is against the recalibrated Act-4 CTM on those entries (the CTM gets the base
  game's S&S row). Stage 2's gate applies: GC − CTM BCE CI below 0 means PASS. The single-label TEST BCE is also
  reported, to stay comparable with stage 2.
- **Label noise.** The within-entry variance of the 5 outcomes, against p(1 − p), gives how much of Act-4 is luck
  the entry state does not decide. That is the ceiling for any V_A4.
- **Pilot capture.** Check that act-end records cover acts 1-3 for every searched root, that the deaths share
  matches the games, and the storage per root. This is the go/no-go for the full capture (stage 4).

## Smoke
See [SMOKE.md](SMOKE.md).
