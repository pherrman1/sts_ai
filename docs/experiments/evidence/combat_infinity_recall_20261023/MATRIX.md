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

Final focused-regression search metrics. CPU is one retained Release process-CPU measurement per fixture; setup, diagnostic traces and JSON output excluded. Dashes mean no candidate or witness, not an inferred zero.

| Fixture | Nodes | Max depth | Reach depth | Cycle length | CPU ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| minimal_dropkick | 7 | 6 | 4 | 2 | 0.224 |
| static_exhaust_dropkick | 7 | 6 | 4 | 2 | 0.129 |
| broken_dropkick | 2 | 1 | — | — | 0.008 |
| energy_positive_no_exhaust | 11 | 10 | 4 | 6 | 0.247 |
| energy_positive_exhaust | 11 | 10 | 4 | 6 | 0.184 |
| energy_negative_exhaust | 13 | 12 | — | — | 0.124 |
| time_eater | 12 | 11 | — | — | 0.065 |
| awakened_one_phase1 | 7 | 6 | 4 | 2 | 0.097 |
| heart_invincible_and_beat | 25 | 24 | — | — | 0.623 |
| heart_low_hp | 7 | 6 | — | — | 0.058 |

Period deltas and replay outcomes from the same retained run:

| Fixture | Enemy HP delta | Player HP delta | Energy delta | Replay result | Repetitions | Actions |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| minimal_dropkick | -14 | 0 | 0 | VICTORY | 13 | 25 |
| static_exhaust_dropkick | -14 | 0 | 0 | VICTORY | 13 | 25 |
| broken_dropkick | — | — | — | not attempted | — | — |
| energy_positive_no_exhaust | -42 | 0 | 7 | VICTORY | 5 | 25 |
| energy_positive_exhaust | -42 | 0 | 7 | VICTORY | 5 | 25 |
| energy_negative_exhaust | — | — | — | not attempted | — | — |
| time_eater | — | — | — | not attempted | — | — |
| awakened_one_phase1 | -14 | 0 | 0 | witness_illegal_or_identity_changed | 12 | 25 |
| heart_invincible_and_beat | — | — | — | not attempted | — | — |
| heart_low_hp | — | — | — | not attempted | — | — |

The cost-negative engine has a simulator-verified six-play period with enemy HP −42 and energy −2, but no admissible cycle candidate. It exhausts energy at 12 plays. Heart discovery has no repeated control state because player HP and Invincible change; a separate two-play forced-replay probe rejects control_state_changed. The unchanged full trace hits Invincible 0 after 29 plays and player death after 40 plays, with 600 enemy HP remaining. Low-HP Heart dies after 6 plays. Time Eater forces the turn after 11 plays. Awakened One rejects after 25 replay actions (12 complete periods plus one action).

For every arm, the complete metrics, reasons and explicit nulls are in matrix.json; exact witnesses and diagnostic traces are in the raw JSONL.
