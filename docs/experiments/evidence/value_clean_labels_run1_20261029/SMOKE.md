# Smoke (2026-10-29, binary 44188a46…, this container, 2 lanes at once)

Two units on the used seed 111387001 (a pilot seed), K = 1: `111387001 1 1` (capture) and `111387001 0 1`.

| check | result |
|---|---|
| both units | rc 0; entry = decision 170 (act-4 map root, floor 52), `a4-111387001.json` written |
| capture on vs off, base game | identical, 391/391 rows after the header |
| fork, capture unit vs plain unit | identical (salt 1 is deterministic) |
| fork vs base | identical up to the entry; first difference at state 199 (act 4, after the entry's decision); prefix check passed |
| outcome | base and fork both died at floor 56 (Heart), heartKilled false |
| wall | base 1,009 s plain / 1,279 s with capture; fork 910 s / 908 s (replay of acts 1-3 included) |
| capture | 181 roots (acts 1-4), N 64, top 3: 27,520 act-end entries; every end record one act later; 3,911 act-1-3 entries end in a death (no record), act-4 entries end the game (no record); 3 rows with `OOC MCTS actions requested at leaf` (act-boss map roots, as in stage 0); 3.6 MB gzip per game |

Note: `games[].file` in `a4-SEED.json` names the jsonl before the unit gzips it (`.jsonl` → `.jsonl.gz`).
