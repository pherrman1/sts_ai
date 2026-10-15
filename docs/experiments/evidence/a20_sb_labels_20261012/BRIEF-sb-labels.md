# Worker brief: A20 short-branch label run (§432 follow-up)

You are worker W (W = 0..24, given in your start message). Philipp chose "Label run" on 2026-10-11 20:59Z:
25 workers x 8 h of short-branch A20 labels (Philipp 21:20Z: 8 h per worker). Owning thread: "open issues for win rate".
Do not change code, do not open PRs, and write only the one output file below.

## Frozen inputs
- Repo https://github.com/pherrman1/sts_ai, main at commit `07a93e367185b242fe2670f2baf3bce5eee76d91` (#486 + #488 merged).
- The Release one_combat sha256 must be `ea307e30c3a5b15df72d23058e65224440a54b2ed90a9d8db039460cfaab123f`. If it differs, STOP and report.
- Silver prior: `/mnt/project-files/v4-a20-retrain/inputs/prior-natpert.compact.txt` (sha256 573305c4...).
- A20 bootstrap trees: `/mnt/project-files/v4-a20-retrain/inputs/v_rich_a20_full.txt` (sha256 d8ab1349e07eb891bbdc443bb6848562e725f24908fa2d7dd0b8dbc9042da140) and `/mnt/project-files/v4-a20-retrain/inputs/v_win_a20_full.txt` (sha256 6f5fbfd0550ec1ec926a0ebf3518f95d7fa7fb77f5f5ba9795e5ff24698be592). Copy both locally and check their sha256 before you start.
- Seeds: 75000000 + 10000*W + k for k = 0, 1, 2, ... in order. Fresh block; nothing else uses it.

## STEP 1: setup (once)
```bash
cd ~ && ( [ -d sts ] || git clone https://github.com/pherrman1/sts_ai.git sts ) && cd ~/sts
git fetch -q origin main && git checkout --detach 07a93e367185b242fe2670f2baf3bce5eee76d91
git submodule update --init --recursive
cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4    # ~5 min
sha256sum build/linux-gcc-release/one_combat     # must be ea307e30...
mkdir -p ~/sb/out && cd ~/sb && cp ~/sts/build/linux-gcc-release/one_combat . && ln -sfn ~/sts/models models && ln -sfn ~/sts/selfplay selfplay
cp /mnt/project-files/v4-a20-retrain/inputs/prior-natpert.compact.txt /mnt/project-files/v4-a20-retrain/inputs/v_rich_a20_full.txt /mnt/project-files/v4-a20-retrain/inputs/v_win_a20_full.txt .
sha256sum prior-natpert.compact.txt v_rich_a20_full.txt v_win_a20_full.txt
```

## STEP 2: write ~/sb/run1.sh exactly as below
```bash
#!/usr/bin/env bash
# one seed per process: bash run1.sh SEED
set -u
cd $HOME/sb
S=$1
[ -f STOP ] && exit 0
[ -s out/s-$S.csv ] && exit 0
export STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_ADAPTIVE=0 STS_COLLECT_KEYS=0 OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE STRATEGIC_SAMPLE_ALL=1 STRATEGIC_BRANCH_FIGHTS=3 STRATEGIC_BRANCH_FUTURES=8 STRATEGIC_BRANCH_SIMS=2000 STRATEGIC_BRANCH_RESEED=1 STS_SILVER_ROOT_PRIOR=$PWD/prior-natpert.compact.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 STS_CF_ALT_BOOT_FLOOR_TREES=$PWD/v_rich_a20_full.txt STS_CF_ALT_BOOT_WIN_TREES=$PWD/v_win_a20_full.txt
timeout 14400 bash $HOME/sts/tools/seed_guard.sh ./one_combat strategicgen2 1 2000 20 out/stmp-$S.csv $S > out/s-$S.log 2>&1 && mv out/stmp-$S.csv out/s-$S.csv
exit 0
```

## STEP 3: run in the background, with a stop time
Start time T0 = now. No new seed may start after T0 + 7.5 h. Every seed is killed at T0 + 8 h.
```bash
cd ~/sb && W=<your W> && seq 0 999 | awk -v w=$W '{print 75000000+10000*w+$1}' > my_seeds.txt
nohup bash -c '(sleep 27000; touch STOP) & (sleep 28800; for p in $(pgrep -x one_combat); do kill $p; done) & xargs -P4 -n1 bash run1.sh < my_seeds.txt; date -u > out/DONE' > run.log 2>&1 &
```
Keep a background Bash watcher running at all times: `run_in_background`, timeout 7200000 ms. Re-arm it every time it exits, until `out/DONE` exists. Otherwise the idle container gets reclaimed and the run dies.
```bash
for i in $(seq 1 115); do [ -f ~/sb/out/DONE ] && break; sleep 60; done; ls ~/sb/out | grep -c '^s-.*csv$'
```

## STEP 4: when out/DONE exists
```bash
cd ~/sb && tar czf /mnt/project-files/v4-a20-retrain/sblabels-w$W.tar.gz out && ls -la /mnt/project-files/v4-a20-retrain/sblabels-w$W.tar.gz && tar tzf /mnt/project-files/v4-a20-retrain/sblabels-w$W.tar.gz | grep -c csv
```
Then reply in your thread:
```
W=..  seeds finished=..  csv ok=..  binary sha ok: yes/no  tree sha ok: yes/no
output: /mnt/project-files/v4-a20-retrain/sblabels-wW.tar.gz
```

## Expected
Smoke seed 75009001 (same config, frozen binary): 114 labelled decisions in 5,173 s on one core; that run died on floor 32. Expect about 15-25 seeds per worker and about 1.5 h per seed. A seed that runs longer than 4 h is killed, and that is fine.
