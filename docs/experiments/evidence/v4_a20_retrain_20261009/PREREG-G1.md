# G1: V4 constant-input guard at A20 (pre-registration)

Question: does feeding the deployed V4's training-constant glob inputs (ascension,
blueKey, greenKey; exported inv 1e6) at x = 0 instead of the clamped +8 change A20
play, and if so, is it non-inferior?

- Code: `3971fe8e` (flag `STS_OOC_STRATEGIC_TOK_CONST_GUARD`, default off), release
  `one_combat`, V4 `selfplay/models/ooc_strategic_tok_final.native` (sha e62abd83…).
- Stack: `silver_learned_stop/live_env.sh` gates (REST/EVENT/SHOP/TREASURE/BOSS_RELIC,
  margin 1.0), `STS_SILVER_LEARNED_STOP=1`, keys off, `STS_STOP_AFTER_ACT=3`
  (A20 second Act-3 boss played), `bestbench 10000 128 20 67100000`, one thread per run.
- Arms: G0 guard off (current), G1 guard on. Seeds 67100000..67100127 paired.
- Sanity already run: A0 seeds 67009100-101 identical rows guard on/off; A20 same
  seeds identical rows.
- Primary: mean paired floor difference G1 - G0, 95% paired bootstrap CI (10,000
  reps, RNG 20261009). Secondary: wins, first Act-3 boss reached, seeds whose row
  differs at all.
- Decision: if fewer than 8 of 128 seeds differ, report `NO_MATERIAL_EFFECT` (the
  +8 shift rarely flips a gate). Otherwise `GUARD_NONINFERIOR` if CI lower bound
  > -0.5 floors, `GUARD_BETTER` if lower bound > 0, else `GUARD_WORSE_OR_UNCLEAR`.
  No default change in any case; the retrain gate (G2) uses the better arm as control.
