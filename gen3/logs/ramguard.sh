#!/bin/bash
# kill sweep python processes if available RAM drops below 1.5 GB (protects the live canary)
while true; do
  av=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
  if [ "$av" -lt 1500 ]; then
    for p in $(pgrep -f "h1distill/silverbot-84ab3ea"); do kill $p; done
    echo "$(date -u +%FT%TZ) KILLED sweep python, avail ${av}MB"
  fi
  sleep 2
done
