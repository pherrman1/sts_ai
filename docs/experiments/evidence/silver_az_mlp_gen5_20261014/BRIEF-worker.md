# Silver AZ MLP loop, generation-5 self-play worker W (4 cores)

W is your worker number (1..N) and N the total worker count the coordinator
gives you (4, 8 or 16); WW is W zero-padded (01..16). Design:
`/mnt/project-files/silver-az-mlp/PLAN.md` §2.2-2.3. This is data generation
only (no evaluation). Do not post anything to GitHub and do not change any
setting.

1. `cd /home/user/sts_ai && git fetch origin main &&
   git checkout --detach f73e6ad709439ceb5c39164ae07836339dd20c92 && git submodule update --init --recursive`
2. Release build of only `one_combat`:
   `cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4`
3. Start the run detached, output in your home directory (not on the share):
   `setsid nohup bash /mnt/project-files/silver-az-mlp/gen5/worker.sh W N $HOME/gen5-out-wWW > $HOME/worker-W.log 2>&1 &`
   It refuses a checkout that is not `f73e6ad7`, a binary whose sha256 is not
   the one in `BINARY_SHA256` (`b4586cfc…95e1`) or a model that is not
   `3ebeab9d…52d6`, then runs 4 lanes of `one_combat silverazgen` (20k Silver,
   gen-4 MLP tree prior K=8, weight 400, root bonus off). Together the N
   workers cover 1,024 full A0 runs: natural seeds 94000000-94000511 and
   perturbed seeds 94001000-94001511, in units of 4 seeds (256/N units per
   worker). Expected run time at 20k: gen 4 (10k) averaged 6.5 min per unit; 20k is
   about 2x, so roughly 2 h with N = 8, plus the build. A unit that runs longer than
   9,000 s is killed by the script (rc 124 or 137) and counts as a failed unit; the watcher
   in step 4 must be re-armed.
4. Mandatory: keep a background watcher running the whole time, re-armed until
   the run ends, so the container is not reclaimed while idle. Use a background
   Bash loop that waits until `$HOME/gen5-out-wWW/lanes.txt` has 4 lines
   (check every 30 s, give up after 2 h). If your watcher ever ends while
   `lanes.txt` has fewer than 4 lines and the run is still going
   (`pgrep -f silverazgen`), start a new one immediately. Do not end your turn
   without a watcher running.
5. When `lanes.txt` has 4 lines, upload exactly two files:
   `tar -C $HOME -cf /mnt/project-files/silver-az-mlp/gen5/wWW.tar gen5-out-wWW`
   then write `/mnt/project-files/silver-az-mlp/gen5/wWW.DONE.txt` containing
   the tar's `sha256sum`, the contents of `units.txt`, `DONE.txt` (missing if
   any unit failed) and the last line of `$HOME/worker-W.log`.
6. If the script stops with a sha256 mismatch, a wrong checkout or a bad W/N,
   or any unit has rc != 0, report the message and do not retry with changed
   settings. Keep the watcher until the coordinator says you can stop.
