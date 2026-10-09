#!/usr/bin/env bash
# usage: unit.sh VARIANT START COUNT -- one guarded A20 silversynthgen unit
set -euo pipefail
variant=$1 start=$2 n=$3
W=/home/user/a20synth; OUT=$OUTDIR
tag="$variant-$start-$n"
[ -f "$OUT/$tag.done" ] && exit 0
mkdir -p "$OUT" "$W/raw"
rm -f "$W/raw/$tag.jsonl" "$W/raw/$tag.manifest.json"
cd "$REPO"
envargs=(-i PATH="$PATH" HOME="$HOME" OMP_NUM_THREADS=1)
while IFS='=' read -r k v; do envargs+=("$k=$v"); done < <(python3 -c 'import json,sys;[print(f"{k}={v}") for k,v in json.load(open(sys.argv[1]))["environment"].items()]' "$W/teacher.json")
s=$(date +%s)
env "${envargs[@]}" bash tools/seed_guard.sh "$W/one_combat" silversynthgen "$n" 10000 20 "$W/raw/$tag" "$start" "$W/teacher.json" "$variant" > "$W/raw/$tag.log" 2>&1
echo "wall_s=$(( $(date +%s) - s ))" >> "$W/raw/$tag.log"
gzip -c "$W/raw/$tag.jsonl" > "$OUT/$tag.jsonl.gz.tmp" && mv "$OUT/$tag.jsonl.gz.tmp" "$OUT/$tag.jsonl.gz"
cp "$W/raw/$tag.manifest.json" "$W/raw/$tag.log" "$OUT/"
rm -f "$W/raw/$tag.jsonl"
touch "$OUT/$tag.done"
