#!/usr/bin/env bash
# Loss mining (README.md). usage: run_all.sh WORKDIR
# Reads the unit tars of the two campaigns from the project share, extracts game + CTM records, builds per-game
# pickles and runs every analysis on arm A (§727), run-1 base games (§720) and both pooled. Outputs in results/.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); W=$1; mkdir -p "$W/vc" "$W/r1"
for t in /mnt/project-files/value-chooser-ab/units/*.tar; do tar xf "$t" -C "$W/vc" --wildcards '*/A-*.jsonl.gz'; done
for t in /mnt/project-files/value-clean-labels-run1/units/*.tar; do tar xf "$t" -C "$W/r1" --wildcards '*/base-*.jsonl.gz'; done
python3 "$HERE/extract.py" "$W/vc/out/units" '*/A-*.jsonl.gz' A "$W/A.pkl"
python3 "$HERE/extract.py" "$W/r1/out/units" '*/base-*.jsonl.gz' R1 "$W/R1.pkl"
for s in basic boss rest2 cluster act3 heart potflow bossreg deckfeat iv lowhp bosscond; do
  for set in A R1 pooled; do
    case $set in pooled) args=("$W/A.pkl" "$W/R1.pkl");; *) args=("$W/$set.pkl");; esac
    python3 "$HERE/$s.py" "${args[@]}" > "$HERE/results/$s.$set.txt" 2>/dev/null
  done
done
