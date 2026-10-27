#!/usr/bin/env bash
# usage: run_cohort.sh REPO RUN OUTDIR [LANES]  -- the #884 cohort: §683 MAP seeds 111374100-111374115, N=16,
# every second searched root, top 3 actions, production Silver at base 10000; LANES parallel replays (default 4).
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 LANES=${4:-4}
mkdir -p "$OUT"
# Resumable: seeds with a .done file are skipped. An unfinished seed replays from its start (replays are
# deterministic) and the observer skips roots whose complete audit row is already in A-<seed>.audit.jsonl; the
# audit file is kept (an unterminated last line is dropped), the seed's other files move to OUTDIR/partial-<pid>/.
for s in $(seq 111374100 111374115); do
  [ -f "$OUT/A-$s.done" ] && continue
  a="$OUT/A-$s.audit.jsonl"
  if [ -s "$a" ] && [ "$(tail -c1 "$a" | od -An -c | tr -d ' ')" != '\n' ]; then
    python3 -c 'import sys; p=sys.argv[1]; d=open(p).read(); open(p,"w").write(d[:d.rfind("\n")+1])' "$a"; fi
  for f in "$OUT"/A-$s.*; do
    [ -e "$f" ] || continue; [ "$f" = "$a" ] && continue
    mkdir -p "$OUT/partial-$$"; mv "$f" "$OUT/partial-$$/"
  done
  echo $s
done | xargs -P "$LANES" -I{} bash "$REPO/docs/experiments/evidence/ctm_audit_884_20261027/replay_unit.sh" \
  "$REPO" "$RUN" "$OUT" {} 16 2 10000
