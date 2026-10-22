# Shield and Spear: greedy vs prior playouts (paired, act4replay)

Started in the exact-combat research thread on 2026-10-22 and handed over to its own thread unanalysed (Philipp,
15:25Z). Research only; nothing changes live play.

- Question: since ADR-0056, elite rooms (Shield and Spear included) use greedy root-table playouts; the Heart (boss)
  keeps prior-argmax playouts. Do prior playouts cut the HP lost on Shield and Spear (about 32 HP per fight in §530),
  right before the Heart?
- States: the 32 recorded A20 Act-4 Shield and Spear entry states of the A20 loss audit F1
  (`/mnt/project-files/audit-2026-10-17/f1-act4replay/ss32.jsonl`, sha256 85f8bf35..., copy in `/mnt/project-files/shield-spear-prior-playouts/`), 4 copies each.
- Seeds: battle seed = 111149768 + state * 4 + copy, so 111149768-111149895 (from the exact-research block 111149600-899;
  now used). Both arms use the same seeds and planner seeds, so they are paired per (state, copy).
- Binary: `one_combat` built at commit f8831b48 of branch claude/project-thread-kgjoid (main 165b5060 merged in, so it lacks main's later PRs #810-#811;
  sha256 b73033a5910e6f13...). `act4replay` needs the flat exact-budget Silver env of §528 (learned stop off).
- Arms (both with the production g7f_E root prior, weight 400, tree prior K = 8, default g7f_E rollout root table):
  `ss_greedy` = default (greedy playouts in elite rooms); `ss_prior` = `STS_SILVER_PRIOR_PLAYOUT_ELITE=1` (prior
  playouts, ADR-0050's rooms). Flat 10,000 simulations.
- Files: `run_ss.sh` (the exact commands), `ss_greedy.csv/.log`, `ss_prior.csv/.log`, `ss_paired.py A.csv B.csv`
  (B − A: HP lost incl. full HP on death, wins, potions left, turns, CPU per fight; per-state bootstrap CI).
- Not done: any analysis (the new thread owns it), learned-stop budgets, whole-run effect.

Analysis: ledger §642 (`paired.txt` is the output of `python3 ss_paired.py ss_greedy.csv ss_prior.csv`). The input
states `ss32.jsonl` stay on the share (sha256 85f8bf35..., also at the audit path above); they are not copied here.
