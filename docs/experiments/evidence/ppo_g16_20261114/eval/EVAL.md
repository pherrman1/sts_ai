# PG16H24 evaluation: net-0046 against net-0420 on §775's G16 + mb4 stack (pre-registration addendum)

Philipp, 2026-11-15 19:18 CET: "lets stop the ppo here. do a comparison with gumbel g16 and max backup 4 as usual on
32 workers against the starting net." The training run stopped after **46 updates** (preregistered: 48 h); the final
net is `net-0046.bin` (sha256 c42c8725eb6388b73653edf9bce888ad9d52d15a870f79e409d62ed3d28baa1c, copied to
/mnt/project-files/ppo-g16/nets/). This file carries out `../PREREG.md` § Evaluation, written before any eval game.

## Arms
| Arm | Out of combat | Combat |
|---|---|---|
| P46 | net-0046, PPO mode, temperature 0, no OOC MCTS | §775's G16 + mb4 exactly: Gumbel root k 16, max backup min 4 visits, 16,000 simulations, Act 4 strong (S&S 10k prior playouts, Heart 40,000), turn cap unset |
| G16 | LONG_C's net-0420 (the PPO start net), same mode | same |

`run_unit.sh` builds one environment for both arms; only the net file differs (sha-checked: net-0420 8c0bd16c…,
net-0046 c42c8725…). Each log must show the arm's own `[heart1] loaded …/<net>` line and no
`research act4 heart budget` line (the training run's Heart 24k is not used in the eval).

## Seeds and units
§775's 1,024 seeds 111378256-111379279 (used; replays). `units.txt`: 32 sentinel units `SEED G16`
(111378256-111378287), then 1,024 units `SEED P46`. One game per unit.

## Deviation from PREREG: binary
PREREG names binary 97aec5b5 (code ba705ab4) and reuses the G12H24 sentinel. The eval runs on **dae7894a** (code
950b53fc, the exact #1046/#1047 combat kernel), the binary that played most of the training run
(`../rebin_sentinel.txt`: identical play on the training stack, about 0.75x time per game). Because the binary
differs from §775's, this campaign plays its **own 32-seed sentinel** (ADR-0064): 32 of 32 games identical to §775's G16
games (rc, abort flag, the whole log except timing lines) = REUSE_VALID, then §775's 1,024 G16 games are the controls.
Anything else = CONTROL_INVALID, no verdict; a net-0420 rerun needs Philipp's go.

## Gate (unchanged from PREREG)
d = Heart kill P46 − G16 per seed. `tools/sprt_gate.py` gainer (d0 0, d1 +2 pp), alpha 0.05, beta 0.05, look 64, cap
1,024. PASS = GO, NOT_SHOWN = STOP; at CAP the 95% seed bootstrap (seed 20261115) decides GO (lo > 0), STOP
(mean ≤ 0) or INCONCLUSIVE. The non-regression SPRT is reported alongside (descriptive). Failed-game, abort and drop
rules as §775 (`analyze.py`, MAX_DROPPED as §799). Secondary, descriptive: Act-4 reach, Heart conversion on seeds
both arms reach, Act-1/2/3 deaths, CPU per run, first and second 512 seeds.

Skipped from PREREG's secondary list: checkpoints 20/40/60/80 on the first 256 seeds (the run stopped at 46; they
can be added later on Philipp's request).

**Expectation (inference, before any eval game).** In-sample Heart rate over the last 10 updates was about 36-37%
against 39.7% in the warm-up, so no learning signal is visible; expected gain 0.3-1.4 pp at the PPO rates of
§760/§756 against a ±2.7 pp 95% resolution, so STOP or INCONCLUSIVE is the likely outcome.

## Cost
About 0.75x §775's 512 s per G16 run on this binary, so about 1,056 × 390 s ≈ 115 lane-h; on 32 workers × 4 lanes
about 55-65 min plus the slowest game.

## Decision
As PREREG: GO makes net-0046 the PPO baseline for the G16 stack; otherwise a ledger entry and the next step with
Philipp. No default changes in any case.
