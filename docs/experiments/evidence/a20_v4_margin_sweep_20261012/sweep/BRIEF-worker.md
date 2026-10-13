# §448 V4 margin sweep at A0 — cloud worker brief

YOUR WORKER NUMBER is given in the header of your instructions as W (1..8).
Requested by Philipp ("do a margin sweep, use 8 cloud workers", 2026-10-12 19:14Z).

You execute a frozen run. Do not change code, commit, push or open a PR. Do not post results anywhere
except the files named below; the lead thread analyzes them.

## Steps
1. In your sts_ai checkout (cloud container, not under /mnt/project-files):
   `bash /mnt/project-files/a20-v4-at-a0-448/sweep/worker.sh setup W`
   It checks out frozen commit 4a407a0c, builds one_combat, and checks the binary hash (f085352b…) and
   both V4 model hashes. If it prints STOP, report the exact line in your thread and stop.
2. MANDATORY watcher: start the run as a background Bash task so the container is not reclaimed:
   `bash $HOME/sweep-wWW/worker.sh run W` (WW = W zero-padded; the script derives paths itself),
   run_in_background, timeout 7200000 ms. It runs 13 units (one per arm, 16 seeds each, 4 at a time),
   about 50-60 minutes. Keep that background task alive until it exits; do not end your turn idle while
   it runs (check `bash $HOME/sweep-wWW/worker.sh status W` if you want). If the run is still going
   when the 2 h task limit nears, start a new background watcher (e.g. a loop on `worker.sh status`) before it expires.
3. When it exits, confirm it printed `uploaded wWW.tar.gz OK` and that
   `/mnt/project-files/a20-v4-at-a0-448/sweep/DONE-wWW.txt` exists. Reply in your thread with the
   DONE file contents (13 lines with rc, any seed-failure lines, tar_sha256). Then stay available;
   the lead may ask you to rerun a unit.

## Frozen config (for reference)
Seeds 81000000+16(W-1) .. +15, A0, §422 "off" base (exact-10k Silver, keys off, act-3 stop, OOC MCTS off),
all V4 gates including map. Arms: A20 V4 (v4_a20_r12.native 08d239f9) and A0 V4
(ooc_strategic_tok_final.native e62abd83) each at margins 0, 0.25, 0.5, 1, 2, 4, plus `heur`
(margin 1e6 = heuristic only).
