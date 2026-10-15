# E3 cloud worker brief (25 workers × 4 cores)

The task is one slice of the E3 counterfactual corpus. The frozen code is
commit `8edf724ca700a4d4bd4f25645fed60381529d862` (PR #434, merged into main
as 91fa8038). The pre-registration is `/mnt/project-files/ooc-cf-pilot/E3-PREREG.md`.
Philipp authorized the run on 2026-10-07 21:17 UTC: "can you try 25 cloud
engines, each with 4 threads?"

Your worker index is **W** (0..24). Your seeds are
**55000000 + 40·W .. 55000000 + 40·W + 39**.

## Steps (run from the repo root, nothing from /mnt/project-files)

```bash
git fetch origin main && git checkout --detach 8edf724ca700a4d4bd4f25645fed60381529d862
git submodule update --init --recursive
cmake --preset linux-gcc-release
cmake --build build/linux-gcc-release --target one_combat -j4     # ~2-25 min
sha256sum build/linux-gcc-release/one_combat
# Expected: 224a1a4291464d4f16e21bc178a6c7ca019054337c06a58586634c11598196fa
# (a release build at the same source in another cloud container). If yours
# differs, record it in NOTES.txt and continue; the run still uses YOUR sha.
B=build/linux-gcc-release/one_combat; S=$(sha256sum $B | cut -d' ' -f1)
OUT=/mnt/project-files/ooc-cf-pilot/e3/w$(printf %02d W)
for c in 0 1; do
  bash docs/experiments/evidence/ooc_cf_pilot_20261007/run_corpus.sh "$B" "$S" \
    8edf724ca700a4d4bd4f25645fed60381529d862 "$OUT/chunk$c" \
    $((55000000 + 40*W + 20*c)) 5 4 2 2 1 2 CARD_REWARD,BOSS_RELIC
done
```

- Each chunk is 4 parts × 5 seeds, one part per core. Two chunks run one
  after the other, which covers 40 seeds, about 80 states and roughly
  10,000 CPU-s.
- Launch the loop detached (nohup or a background shell) and wait on
  `chunk1/DONE`. Never use foreground sleep.
- Rerunning the same command resumes: parts that already have a manifest are
  skipped.

## Rules

- Write only under your own `w<WW>/` directory. Never touch other workers'
  directories.
- **Stall:** a part counts as stalled when its `.labels.csv` has not grown for
  45 minutes while `one_combat` is still running.
  - Kill only that part's process.
  - Write the seed range of that part to `w<WW>/STALLED.txt`.
  - Leave the part's files in place.
  - Do not regenerate it with other seeds.
- **Finish:** write `w<WW>/DONE.txt` containing your binary sha256, the
  `ooc cf pilot ... labels=X/Y` lines from every part log, and any stalled
  ranges.
- **Do not:**
  - analyze, train or merge data;
  - change code, open a PR or commit;
  - run anything other than these commands.
- **Reply in the thread** in one line: worker W done, labels valid/total,
  stalls.
