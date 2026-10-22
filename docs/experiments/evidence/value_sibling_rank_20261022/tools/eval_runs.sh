#!/bin/bash
# usage: V=<work dir> DATA=<clone of claude/az-gen2-data> REPO=<sts_ai checkout> eval_runs.sh NAME...
# Cloud evaluation of sibling-ranking-round heads pushed to gen2/value-sr/ on the data branch (value-head research,
# 2026-10-22). V holds one_combat (sha256 193b0000…), the §494 siblings (s494/), the round-2 TRAIN+VALIDATION delivery
# (r2/), the prices set (prices/: records.jsonl, meta.json, prices.py, gate.py) and the control's outputs (work/,
# M0.3 seed 0 from gen2/value-cf). Per head: prices gate, value_leaf_check.py check (raw value logits on r2 and s494
# rows), then sr_eval.py against the control. sr_eval_<names>.json lands in the directory the script is called from.
# one_combat reads model files relative to the repository, so the scoring steps run from REPO.
set -eu
T=$(cd "$(dirname "$0")" && pwd); OUT=$PWD; P=$V/prices
cd "$REPO"
nets=()
for n in "$@"; do
  cp "$DATA/gen2/value-sr/weights/$n/student.bin" "$V/$n.bin"
  echo "$n bin $(sha256sum "$V/$n.bin" | cut -c1-16)"
  nets+=("$n=$V/$n.bin")
  "$V/one_combat" heart1score "$V/$n.bin" "$P/records.jsonl" "$P/$n.scores.jsonl" > /dev/null 2>&1
  python3 "$P/prices.py" analyze "$P/meta.json" "$P/$n.scores.jsonl" "$P/$n-prices.json" > /dev/null
done
(cd "$P" && python3 gate.py M0.3 "$@")
mkdir -p "$V/work3"
python3 tools/heart1/value_leaf_check.py check "$V/one_combat" "$V/sr_check_$(echo "$@" | tr ' ' '_').json" \
  "$V/work3" "$V/s494" "$V/r2" "${nets[@]}" > /dev/null
args=(); for n in "$@"; do args+=("$n=$V/work3"); done
python3 "$T/sr_eval.py" "$V/r2" "$V/s494" "$OUT/sr_eval_$(echo "$@" | tr ' ' '_').json" M0.3="$V/work" "${args[@]}"
