#!/bin/bash
# usage: lane2.sh WAITPID QUEUEFILE
while kill -0 $1 2>/dev/null; do sleep 20; done
while read -r name args; do
  [ -z "$name" ] && continue
  [ -f runs/$name/train.json ] && continue
  mkdir -p runs/$name
  python3 arch.py $name --threads 2 $args > runs/$name/log.txt 2>&1
done < "$2"
