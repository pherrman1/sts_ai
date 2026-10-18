# OOC MCTS prior temperature 3: full-run A20 confirmation of §532 (pre-registered 2026-10-18, before T3 data)

**Question:** does `STS_OOC_MCTS_TEMPERATURE=3` (the §532 Act-1 screen pass, +3.1 HP [−2.1, +8.3]) win more full A20
runs than the current default temperature 1?
Authorization: Philipp 2026-10-18 13:08Z ("set up full run test of temp 3, but wait for some speed up") and 22:10Z
("do the newest speedup we have. 256 seeds on 16 workers is fine").

**Control (reused, not rerun):** the A20 winrate check (`a20_winrate_check_20261018`, code 64b38c88, binary 9daffbd4,
student_sel cf6bf7fb), runs from its uploaded tars. **Seeds:** the first 256 seeds, ascending, of that campaign with
an rc=0 unit and a CSV row in the 28 tars uploaded at freeze time (workers 7, 10, 23, 31 not yet uploaded), i.e.
`units.txt` (111194580-111194871 without the four missing workers' seeds). Seeds are selected without looking at
outcomes.

**Candidate (T3):** the same `run_unit.sh` env as the control, with `STS_OOC_MCTS_TEMPERATURE=3` and nothing else
different in play: current main (with the exact student-forward speedups #662 and #670) plus a PIN block that
restores the control code's behaviour of every play-changing default merged since 64b38c88:
`STS_DEAD_TARGET_DEBUFF_FIX=0` (#656), `STS_ACTIVE_POWER_FEATURES=0` (#659), `STS_CURL_UP_LETHAL_FIX=0` (#669),
`STS_CTM_ACT4_SURVIVAL_MODEL=0` (#667, ADR-0048), `STS_SILVER_ROLLOUT_ROOT_TABLE=models/combat_policy_mlp_g6_E.txt`
(#668, ADR-0049). OOC stop flags as the control (`EARLY_STOP=1`, gap stop and any learned OOC stop unset/off);
`STS_SILVER_LEARNED_STOP=0` as the control.
**Identity gate (before launch):** arm C (temperature 1, same PIN block, new binary) replays control seeds
111194603, 111194710, 111194840 and 111194582 with identical CSV rows (except `sec`) and identical OOC decision logs.
If any differs, the control is not reusable and this plan is withdrawn.

**Primary:** wins (Heart kills) T3 vs control on the 256 paired seeds, paired difference with McNemar exact test and
a seed bootstrap 95% CI. **Secondary:** Act-4 reached (= Act-3 boss cleared), floor reached, OOC CPU per run (the binaries
differ: CPU is descriptive only).
**Failed T3 units (added 22:3xZ, before any T3 data, after pre-launch review):** a T3 unit whose `.done` rc is not 0
(crash, abort, 24 h timeout rc 124) or that has no CSV row counts as a T3 loss (won = 0) in the primary; their number
and seeds are reported, with a sensitivity analysis that drops those seeds from both arms. A worker that never
uploads is relaunched; its seeds are not dropped silently.
**Rule:** CONFIRMED if the win difference CI lower bound > 0; WORSE if the CI upper bound < 0; else NOT_SHOWN.
No default change without Philipp's word in any case.
**Known limits:** T3 runs ~13% more OOC sims per root (the lock fires later; §532); not CPU-matched.
