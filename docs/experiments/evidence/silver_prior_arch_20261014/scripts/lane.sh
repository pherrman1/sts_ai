#!/bin/bash
# usage: lane.sh QUEUEFILE ; each line: NAME ARGS...
while read -r name args; do
  [ -z "$name" ] && continue
  [ -f runs/$name/train.json ] && continue
  mkdir -p runs/$name
  python3 arch.py $name --threads 2 $args > runs/$name/log.txt 2>&1
done < "$1"
