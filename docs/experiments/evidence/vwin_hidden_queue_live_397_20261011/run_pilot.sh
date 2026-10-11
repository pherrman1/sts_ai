#!/usr/bin/env bash
cd /tmp/claude-0/vw397
P=/tmp/claude-0/vw397/pilot
{ for a in legacy public8; do for k in 0 1 2 3; do echo "$a $((74015000+32*k)) 32 $P/$a-$((74015000+32*k))"; done; done; } > $P/units.txt
xargs -P 4 -L 1 ./arm.sh < $P/units.txt
echo "finished=$(date -u +%FT%TZ)" > $P/ALLDONE
