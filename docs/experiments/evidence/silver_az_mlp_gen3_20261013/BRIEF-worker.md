# Silver AZ MLP loop, generation-3 self-play worker W (4 cores)

W is your worker number (1..N) and N the total worker count the coordinator
gives you (4, 8 or 16); WW is W zero-padded (01..16). Design:
`/mnt/project-files/silver-az-mlp/PLAN.md` §2.2-2.3. This is data generation
only (no evaluation). Do not post anything to GitHub and do not change any
setting.

1. `cd /home/user/sts_ai && git fetch origin main &&
   git checkout --detach 37b7d33eb1ab342eeb6fbe701b54f1d05b7d5a08 && git submodule update --init --recursive`
2. Release build of only `one_combat`:
   `cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4`
3. Start the run detached, output in your home directory (not on the share):
   `setsid nohup bash /mnt/project-files/silver-az-mlp/gen3/worker.sh W N $HOME/gen3-out-wWW > $HOME/worker-W.log 2>&1 &`
   It refuses a checkout that is not `37b7d33e`, a binary whose sha256 is not
   the one in `BINARY_SHA256` (`9098ee11…b0f7`) or a model that is not
   `7eef7ce1…a471`, then runs 4 lanes of `one_combat silverazgen` (2k Silver,
   gen-2 MLP tree prior K=8, weight 400, root bonus off). Together the N
   workers cover 1,024 full A0 runs: natural seeds 88000000-88000511 and
   perturbed seeds 88001000-88001511, in units of 4 seeds (256/N units per
   worker). Expected run time (gen 2's longest lane took 23 min at N = 4): about 25 min
   with N = 4, 12 min with N = 8, 6 min with N = 16, plus the build.
4. Mandatory: keep a background watcher running the whole time, re-armed until
   the run ends, so the container is not reclaimed while idle. Use a background
   Bash loop that waits until `$HOME/gen3-out-wWW/lanes.txt` has 4 lines
   (check every 30 s, give up after 2 h). If your watcher ever ends while
   `lanes.txt` has fewer than 4 lines and the run is still going
   (`pgrep -f silverazgen`), start a new one immediately. Do not end your turn
   without a watcher running.
5. When `lanes.txt` has 4 lines, upload exactly two files:
   `tar -C $HOME -cf /mnt/project-files/silver-az-mlp/gen3/wWW.tar gen3-out-wWW`
   then write `/mnt/project-files/silver-az-mlp/gen3/wWW.DONE.txt` containing
   the tar's `sha256sum`, the contents of `units.txt`, `DONE.txt` (missing if
   any unit failed) and the last line of `$HOME/worker-W.log`.
6. If the script stops with a sha256 mismatch, a wrong checkout or a bad W/N,
   or any unit has rc != 0, report the message and do not retry with changed
   settings. Keep the watcher until the coordinator says you can stop.
