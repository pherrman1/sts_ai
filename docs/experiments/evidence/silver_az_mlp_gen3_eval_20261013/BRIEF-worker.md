# §460 worker W (Silver AZ MLP prior gen-3 milestone, CPU-matched check, 4 cores)

W is your worker number (1..N) and N the total worker count the coordinator
gives you (8 or 16); WW is W zero-padded (01..16). Pre-registration:
`/mnt/project-files/silver-az-mlp/gen3-eval/PREREG.md`. Do not post anything
to GitHub and do not change any setting.

1. `cd /home/user/sts_ai && git fetch origin main &&
   git checkout --detach 37b7d33eb1ab342eeb6fbe701b54f1d05b7d5a08 && git submodule update --init --recursive`
2. Release build of only `one_combat`:
   `cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4`
3. Start the run detached, output in your home directory (not on the share):
   `setsid nohup bash /mnt/project-files/silver-az-mlp/gen3-eval/worker.sh W N $HOME/gen3eval-out-wWW > $HOME/worker-W.log 2>&1 &`
   It refuses a binary whose sha256 is not `9098ee11…b0f7` or models that are not
   `f57b7fdd…5315` (gen 3) and `a5f4505a…64d2` (gen 1), then runs 4 shards of 128/(4N) seeds each (together all of
   90000000-90000127 across the N workers). Expected wall time (smoke: 48-267 s per source seed
   per core): about 10-20 min with N = 16, 20-40 min with N = 8, plus the build.
4. Mandatory: keep a background watcher running the whole time, re-armed until
   the run ends, so the container is not reclaimed while idle. Use a background
   Bash loop that waits until `$HOME/gen3eval-out-wWW/shards.txt` has 4 lines
   (check every 30 s, give up after 2 h). If your watcher ever ends while
   `shards.txt` has fewer than 4 lines and the run is still going
   (`pgrep -f "ctmsilvergen"`), start a new one immediately. Do not end your turn
   without a watcher running.
5. When `shards.txt` has 4 lines, upload exactly two files:
   `tar -C $HOME -cf /mnt/project-files/silver-az-mlp/gen3-eval/wWW.tar gen3eval-out-wWW`
   then write `/mnt/project-files/silver-az-mlp/gen3-eval/wWW.DONE.txt` containing
   the tar's `sha256sum`, the contents of `shards.txt`, and the last line of each
   `shardI.log`.
6. If the script stops with a sha256 mismatch, a bad W/N, or any shard has
   rc != 0, report the message and do not retry with changed settings. Keep the
   watcher until the coordinator says you can stop.
