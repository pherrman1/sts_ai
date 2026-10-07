#!/usr/bin/env bash
# #418 Stage 0 worker: both teacher arms on one disjoint seed chunk.
# usage: run_worker.sh BINARY REPO_ROOT OUT_DIR WORKER_NAME SEED_LO N_SEEDS
# BINARY must be an executable copy (not on noexec /mnt/project-files).
set -euo pipefail
bin=$1 repo=$2 out=$3 name=$4 lo=$5 n=$6
frozen=46153506cf183adcf422a0877310caa7747c1782
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$out"
cd "$repo"
[ "$(git rev-parse HEAD)" = "$frozen" ] || { echo "repo not at $frozen" >&2; exit 1; }
for arm in exact10k learned; do
  tag="$name-$arm"
  [ -f "$out/$tag.done" ] && continue
  python3 "$here/make_teacher.py" "$arm" "$bin" "$repo" "$out/$tag.teacher.json" >/dev/null
  # Clean STS_* environment, then exactly the frozen teacher environment.
  envargs=(-i PATH="$PATH" HOME="$HOME" OMP_NUM_THREADS=1)
  while IFS='=' read -r k v; do envargs+=("$k=$v"); done < <(
    python3 -c 'import json,sys;[print(f"{k}={v}") for k,v in json.load(open(sys.argv[1]))["environment"].items()]' "$out/$tag.teacher.json")
  env "${envargs[@]}" bash "$repo/tools/seed_guard.sh" "$bin" combattransitiongen "$n" 10000 0 \
      "$out/$tag.jsonl" "$lo" "$out/$tag.teacher.json" > "$out/$tag.log" 2>&1
  touch "$out/$tag.done"
done
