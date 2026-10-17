#!/usr/bin/env bash
# Act-4 label unit: run_unit.sh REPO RUN OUT NAME LO N. act4_fork forced setup, ASC 20, 10000 sims, deployed OOC step.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 NAME=$4 LO=$5 N=$6
U="$OUT/$NAME-$LO"
[ -f "$U.done" ] && exit 0
if [ -e "$U.jsonl" ] || [ -e "$U.log" ]; then
  A="$OUT/aborted-$(date -u +%Y%m%dT%H%M%SZ)-$NAME-$LO"; mkdir -p "$A"; mv "$U".* "$A"/ 2>/dev/null
fi
mapfile -t E < <(python3 -c "import json,sys;[print(f'{k}={v}') for k,v in json.load(open(sys.argv[1]))['environment'].items()]" "$RUN/teacher.json")
cd "$REPO"
st=$(date +%s)
env -i PATH="$PATH" HOME="$HOME" OMP_NUM_THREADS=1 "${E[@]}" bash tools/seed_guard.sh "$RUN/one_combat" \
  combattransitionforcedgen "$N" 10000 20 "$U.jsonl" "$LO" "$RUN/teacher.json" act4_fork > "$U.log" 2>&1
rc=$?
echo "unit=$NAME-$LO n=$N rc=$rc sec=$(( $(date +%s) - st )) $(grep -h '^combattransition' "$U.log" | tail -1 | grep -o 'completed=[^ ]* quarantined=[^ ]* no_act4=[^ ]* rows=[0-9]* ooc_heart1=[0-9]* ooc_deployed=[0-9]*')" > "$U.done"
