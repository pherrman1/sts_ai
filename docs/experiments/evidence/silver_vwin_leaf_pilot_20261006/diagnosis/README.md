# §385 diagnosis: audit replay of 16 pilot seeds (2026-10-06)

Binary: PR #422 head plus the `STS_SILVER_VWIN_LEAF_AUDIT` hook (records each
combat's price surface at the root; does not change play). Seeds
49000001..49000016, same configuration as the pilot. Both replays reproduce the
pilot rows exactly (16/16 control, 16/16 v_win). Raw JSONL:
`/mnt/project-files/silver-vwin-leaf-367/audit/` (not committed, ~10 MB).

Control trajectories, 420 fights (404 non-flat):
- HP curves: 257/372 non-healed sweeps fully monotone; largest drop within
  ±20 HP of the real HP max 1.4 HP-eq. Not a cause.
- Sampling noise (two independent 4-future pricers): base price median 0.00,
  p90 0.15 HP-eq; potion value median 0.27, p90 1.53. Not a cause.
- Potion value (HP-eq, handcrafted 11): normal act 1/2/3 median 1.9/7.9/5.1,
  negative in 35%/8%/15%; elite 5.1/8.6/4.8 (negative 32%/5%/14%); act 1/2 boss
  15.2/13.2.
- Escape gap (reward value, HP-eq): normal median 1.9/3.1/2.7, elite 6.1/6.4/3.9.
- 25 gold: median 0.0 HP-eq in every room (handcrafted 6.25).

Behavior (same seeds, v_win on vs control): potions held at fight start 1.59
vs 1.97 (paired same seed+floor: −0.42, n=351), HP −0.2; at the Act 1 boss
1.40 vs 2.19 potions, Act 2 boss 1.86 vs 2.31, HP about equal.
