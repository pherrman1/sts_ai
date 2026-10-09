#!/usr/bin/env bash
set -euo pipefail
f=$1; out=$2; tag=$(basename "$f" .jsonl.gz)
[ -f "$out/$tag.summary.json" ] && exit 0
cd /home/user/sts_ai
envargs=(-i PATH="$PATH" HOME="$HOME" OMP_NUM_THREADS=1)
while IFS='=' read -r k v; do envargs+=("$k=$v"); done < <(python3 -c 'import json,sys;[print(f"{k}={v}") for k,v in json.load(open(sys.argv[1]))["environment"].items() if k!="STS_EXECUTABLE_GIT_SHA"]' /home/user/a20synth/teacher.json)
zcat "$f" | env "${envargs[@]}" /home/user/a20synth/one_combat-main silversynthfeatures "$out/$tag" > "$out/$tag.featlog" 2>&1
