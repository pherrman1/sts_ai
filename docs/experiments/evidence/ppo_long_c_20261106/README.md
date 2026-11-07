# LONG_C: LONG_B continued to 420 updates (2026-11-06)

Pre-registration and launch order: [PREREG.md](PREREG.md). Arm: [arms.txt](arms.txt). Actors:
[actors_frozen.env](actors_frozen.env) (combat B, identical to LONG_B's). Binary and store: [screen.manifest](screen.manifest).
The arm is frozen on the PC by [make_arms.sh](make_arms.sh) (`ppo_cloud.py init --fork-dir … --continue`).
Status: launched 2026-11-06 00:49 CET; paused at update 270; from iteration 272 on, actors play with turn cap 100 (binary 63508ecc, see PREREG "Deviation").
Result: [RESULT.md](RESULT.md), ledger §760: net-0420 vs net-0220 +1.46 pp [−0.73, +3.66], INCONCLUSIVE. `screen.manifest` = the actor binary from iteration 272 on; build it from 8219ab8b (or e387fbd4), not from the branch head.
