# Fixture ablation matrix

KILL = CERTIFIED_KILL; CANDIDATE = PRODUCTIVE_CYCLE_CANDIDATE. All arms use the same bounds and fixture roots. Final extra diagnostics preserve every arm-B detector/replay result.

| Fixture | Merged #839 | Exhaust only | Exhaust + energy |
| --- | --- | --- | --- |
| minimal_dropkick | KILL | KILL | KILL |
| static_exhaust_dropkick | NONE | KILL | KILL |
| broken_dropkick | NONE | NONE | NONE |
| energy_positive_no_exhaust | NONE | NONE | KILL |
| energy_positive_exhaust | NONE | NONE | KILL |
| energy_negative_exhaust | NONE | NONE | NONE |
| time_eater | NONE | NONE | NONE |
| awakened_one_phase1 | CANDIDATE | CANDIDATE | CANDIDATE |
| heart_invincible_and_beat | NONE | NONE | NONE |
| heart_low_hp | NONE | NONE | NONE |

Final focused-regression run below. CPU is one Release process-CPU measurement per fixture; setup, diagnostic traces and JSON output excluded. Dashes indicate no candidate/witness/replay, not an inferred zero.

| Fixture | Reach | Witness | Nodes | Enemy HP delta | Energy delta | Replay result | Periods/actions | CPU ms |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: |
| minimal_dropkick | 4 | 2 | 7 | -14 | 0 | VICTORY | 13/25 | 0.224 |
| static_exhaust_dropkick | 4 | 2 | 7 | -14 | 0 | VICTORY | 13/25 | 0.129 |
| broken_dropkick | — | — | 2 | — | — | not attempted | — | 0.008 |
| energy_positive_no_exhaust | 4 | 6 | 11 | -42 | 7 | VICTORY | 5/25 | 0.247 |
| energy_positive_exhaust | 4 | 6 | 11 | -42 | 7 | VICTORY | 5/25 | 0.184 |
| energy_negative_exhaust | — | — | 13 | — | — | not attempted | — | 0.124 |
| time_eater | — | — | 12 | — | — | not attempted | — | 0.065 |
| awakened_one_phase1 | 4 | 2 | 7 | -14 | 0 | witness_illegal_or_identity_changed | 12/25 | 0.097 |
| heart_invincible_and_beat | — | — | 25 | — | — | not attempted | — | 0.623 |
| heart_low_hp | — | — | 7 | — | — | not attempted | — | 0.058 |

The cost-negative engine has a simulator-verified six-play period with enemy HP −42 and energy −2, but no admissible cycle candidate. It exhausts energy at 12 plays. Heart discovery has no repeated control state because player HP and Invincible change; a separate two-play forced-replay probe rejects control_state_changed. The unchanged full trace hits Invincible 0 after 29 plays and player death after 40 plays, with 600 enemy HP remaining. Low-HP Heart dies after 6 plays. Time Eater forces the turn after 11 plays. Awakened One rejects after 25 replay actions (12 complete periods plus one action).

For every arm, the complete metrics, reasons and explicit nulls are in matrix.json; exact witnesses and diagnostic traces are in the raw JSONL.
