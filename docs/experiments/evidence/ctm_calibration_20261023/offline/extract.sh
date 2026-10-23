#!/usr/bin/env bash
# Rebuild the row sets of rows.txt from the two campaigns' verified unit tars: extract.sh OUT_DIR
# A M S MS: the stage-3 A/B (§661); LC: the stage 1-2 games (§663, held out). Prints "set rows sha256" per set.
set -euo pipefail
OUT=$1
mkdir -p "$OUT/ab" "$OUT/lc"
for t in /mnt/project-files/value-level-ab/units/*.tar; do tar xf "$t" -C "$OUT/ab" --wildcards '*.ctm.jsonl.gz'; done
for t in /mnt/project-files/value-leaf-compare/units/*.tar; do tar xf "$t" -C "$OUT/lc" --wildcards '*.ctm.jsonl.gz'; done
for arm in A M S MS; do
  (for f in "$OUT"/ab/out/units/*/"$arm"-*.ctm.jsonl.gz; do zcat "$f"; done) > "$OUT/$arm.jsonl"
done
(for f in "$OUT"/lc/out/units/*/LC-*.ctm.jsonl.gz; do zcat "$f"; done) > "$OUT/LC.jsonl"
for s in A M S MS LC; do echo "$s $(wc -l < "$OUT/$s.jsonl") $(sha256sum < "$OUT/$s.jsonl" | cut -d' ' -f1)"; done
