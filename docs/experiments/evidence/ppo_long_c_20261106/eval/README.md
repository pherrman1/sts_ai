# LONG_C evaluation campaign (frozen 2026-11-07 after SERVE_DONE)

Plays LONG_C's checkpoints net-0270/0320/0370/0420 against L220 (LONG_B's net-0220) on G1's 2,048 seeds
(../PREREG.md, "Evaluation"). It uses LONG_B's evaluation runner, flags and analysis rules, with the arms replaced.
L220 is reused from LONG_B's evaluation (`control_l220.csv` = the L220 rows of
`../../ppo_long_b_20261104/eval/games.csv` on main, blob 71ed856d). Before that, a 32-seed sentinel replay must
pass: `sentinel_expected.csv` holds LONG_B's L220 Heart kill, final floor and decisions= for seeds
111520000-111520031, from LONG_B's evaluation unit tars, and agrees with control_l220.csv.

Engine: binary 78849fcf, code_commit bc33e470, turn cap 500. This is the same engine as LONG_B's evaluation, and
not LONG_C's actor binary 63508ecc with cap 100 (PREREG "Deviation", J D2). Nets: from the PC via store ref
ppo-xfer/longc-nets (commit 91721cff), sha checked against loop.json's next_sha256 of updates 270/320/370/420.
They are copied to /mnt/project-files/ppo-long-c/nets/. net-0220 is copied from /mnt/project-files/ppo-long-b/nets/.

Primary: d = Heart kill L420 − L220 per seed, sprt_gate gainer (d1 = +2 pp), look 64, cap = min(2,048, analysed
seeds), then the bootstrap fallback. Secondary: L270, L320, L370 vs L220. `python3 analyze.py --self-test` covers
drops, an abort and a sentinel mismatch (CONTROL_INVALID).
Cost: 4 × 2,048 + 32 games × ~27 s ≈ 62 core-h. 26 workers: Philipp 2026-11-06 23:43 CET "Ja go auf 40 workern", then 23:47 CET split fairly with the MAX_BACKUP gate (26 eval, 14 gate). claim_settle_seconds 60.

Run commit: the branch with the cap-100 commits reverted (212020ff, 315d7706, 4b7a9139; J M1). Its build inputs
are then equal to bc33e470 again, which `tools/cloud/worker.sh setup` requires.
