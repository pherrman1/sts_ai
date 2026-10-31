# Smokes (2026-10-30, author container, binary 0ef572a5…, code bfd45383)
- `act4replay` + `STS_ACT4REPLAY_CHAIN=heart`, learned budget, the first 16 states of `ss_states.tar` as one file
  (planner seeds differ from the campaign's, which plays one state per file), battle seed 111384000 + state, OMP 4.
  Arm off finished all 16; arm on stopped after 12 (the background job ended with the author's shell; not a code
  error). On the 12 paired states: aligned counter at the Heart 8 vs 11, S&S deaths 0 vs 1 (state 2, 70/70 HP off),
  Heart kills 8 vs 7, CPU 40 vs 44 s per S&S + Heart run, S&S turns 4.5 vs 5.0. With the term on, Silver mostly ends
  S&S on counter 3 or 4 (state 0: 3 more turns at the same 71 HP to reach 4). Too few states to read an effect.
- `run_unit.sh` for unit 1 (OMP 1): rc=0, 155 s wall, 8 rows (`budget=learned`, chain columns), all checks pass;
  counter at the Heart off 5/5/4/1, on 4/4/4/4.
- `analyze.py` on that unit: runs, 1 valid state, 0 bad rows.
