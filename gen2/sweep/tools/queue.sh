#!/bin/bash
# usage: queue.sh JOBFILE -- run each line (NAME args...) sequentially via run.sh, skipping finished runs
cd ~/h1distill/gen2
while read -r name args; do
  [ -z "$name" ] && continue
  grep -q "^EXIT 0" sweep/$name/train.log 2>/dev/null && continue
  ./run.sh $name $args < /dev/null
done < "$1"
echo "QUEUE DONE $1"
