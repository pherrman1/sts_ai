#!/usr/bin/env bash
# #418 Stage 0 part launcher. usage: run_part.sh PART BINARY REPO_ROOT OUT_DIR
# PART: local | cloud1..cloud5. Starts one worker per chunk, waits, writes DONE.
set -euo pipefail
part=$1 bin=$2 repo=$3 out=$4
here=$(cd "$(dirname "$0")" && pwd)
# name:first_seed:count  (disjoint, union = 50000000..50000127)
case "$part" in
  local)  chunks="w0:50000000:5 w1:50000005:5 w2:50000010:5 w3:50000015:4 w4:50000019:4 w5:50000023:4 w6:50000027:4 w7:50000031:4 w8:50000035:4 w9:50000039:4" ;;
  cloud1) chunks="w0:50000043:5 w1:50000048:4 w2:50000052:4 w3:50000056:4" ;;
  cloud2) chunks="w0:50000060:5 w1:50000065:4 w2:50000069:4 w3:50000073:4" ;;
  cloud3) chunks="w0:50000077:5 w1:50000082:4 w2:50000086:4 w3:50000090:4" ;;
  cloud4) chunks="w0:50000094:5 w1:50000099:4 w2:50000103:4 w3:50000107:4" ;;
  cloud5) chunks="w0:50000111:5 w1:50000116:4 w2:50000120:4 w3:50000124:4" ;;
  *) echo "unknown part $part" >&2; exit 2 ;;
esac
mkdir -p "$out"
[ -f "$out/DONE" ] && { echo "already DONE"; exit 0; }
sha256sum "$bin" > "$out/binary.sha256"
pids=()
for c in $chunks; do
  IFS=: read -r name lo n <<<"$c"
  bash "$here/run_worker.sh" "$bin" "$repo" "$out" "$part-$name" "$lo" "$n" > "$out/$part-$name.worker.log" 2>&1 &
  pids+=($!)
done
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
[ $fail -eq 0 ] || { echo "a worker failed; see *.worker.log and *.log; rerun this command to resume" >&2; exit 1; }
{ echo "part=$part finished=$(date -u +%FT%TZ)"
  grep -h "combattransitiongen teacher=" "$out"/*-exact10k.log "$out"/*-learned.log | sed 's/ -> .*//'
  (cd "$out" && sha256sum *.jsonl *.jsonl.manifest.json)
} > "$out/DONE"
cat "$out/DONE"
