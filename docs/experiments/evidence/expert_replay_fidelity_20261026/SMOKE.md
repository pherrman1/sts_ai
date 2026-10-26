# Expert-replay smoke (2026-10-26)

`run_unit.sh` on 4 expert seeds, both arms, 4 lanes on one 4-CPU cloud container, binary `b8b5268`, student_sel
`cf6bf7fb…`. All 8 games exited 0 and passed the banner checks (OOC learned stop, Act-4 CTM, heart1 loaded,
`screens_a20_default=map_full_budget`, M0 leaf calibration, no value-head leaf). Seeds chosen to cover a fully
reproduced won run, an old log without Neow sub-choices, and two expert deaths. A smoke, not a result: 4 seeds say
nothing about win rates.

| run (expert result) | X: expert decisions, then bot | B: bot alone | replay stop (X) | X wall / B wall |
|---|---|---|---|---|
| 1686772695 (won, Heart) | **Heart killed**, floor 56 | died floor 51 | Act 4 (replayed all of acts 1-3) | 998 s / 537 s |
| 1649959168 (won, Heart, old log) | **Heart killed**, floor 56 | died floor 33 | floor 12: elite relic Unceasing Top, log Captain's Wheel | 2,354 s / 562 s |
| 1668535738 (died floor 33) | died floor 33 | died floor 33 | never (run ended inside the log) | 49 s / 245 s |
| 1671655439 (died floor 48) | died floor 56 | died floor 30 | floor 29: card offer differs | 299 s / 278 s |

Replayed decisions per run (X): up to 48 map moves, 85 reward steps, 12 shop steps, 7 campfires, 8 card selects;
unlogged selects (Bottled cards, Astrolabe, old Neow sub-choices) went to the bot (0-3 per run). Both stops match
the fidelity probe's first mismatch for those runs (relic at floor 12 after an unlogged Neow transform; card offer at
floor 29), so the replay stops where the engine's offers stop matching, as designed.

Wall time follows how far a game gets: Heart games with Act 4 strong cost 1,000-2,400 s. Mean 925 s (X) and 405 s
(B) per game here.
