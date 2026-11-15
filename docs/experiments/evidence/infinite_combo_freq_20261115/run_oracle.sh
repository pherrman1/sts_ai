#!/usr/bin/env bash
# usage: run_oracle.sh ORACLE OUT_DIR [NODE_CAP] -- combat_infinity_oracle --snapshots (natural mode) on every
# finished replay G16-SEED.states.jsonl.gz in OUT_DIR that has no O-SEED.jsonl yet.
set -uo pipefail
ORACLE=$1 OUT=$2 CAP=${3:-2000}
for d in "$OUT"/G16-*.done; do
  seed=${d##*/G16-}; seed=${seed%.done}
  grep -q "rc=0 " "$d" || continue
  [ -s "$OUT/O-$seed.jsonl" ] && continue
  zcat "$OUT/G16-$seed.states.jsonl.gz" | "$ORACLE" --snapshots - natural "$CAP" > "$OUT/O-$seed.jsonl.part" \
    && mv "$OUT/O-$seed.jsonl.part" "$OUT/O-$seed.jsonl" || echo "oracle failed on $seed" >&2
done
