#!/usr/bin/env bash
G=$(dirname "$(realpath "$0")")
cd "$G"
while read -r S O SEED; do
  tag="s${S}_o${O}_seed${SEED}"
  [ -s "runs/$tag.csv" ] && [ "$(wc -l < runs/$tag.csv)" -ge 2 ] && continue
  echo "$S $O $SEED"
done < jobs.txt | xargs -P 4 -L 1 bash -c 'st=$(date +%s); '"$G"'/run_one.sh "$0" "$1" "$2" '"$G"'/runs; echo "{\"S\":$0,\"O\":$1,\"seed\":$2,\"rc\":$?,\"wall\":$(( $(date +%s)-st ))}" >> '"$G"'/status.jsonl'
echo GRID_DONE
