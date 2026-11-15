#!/usr/bin/env bash
# replay.sh BIN_DIR SRC_DIR OUT_DIR SEED -- issue #1056 pilot: replays one §782 G16 game (its own .env, binary
# 112c0f3a = code ebd446b3, which reproduces §775/§782, gumbel_stop_trace_20261110/SMOKE.md) with three read-only
# traces: STS_OOC_DECISION_TRACE (as §782), STS_OOC_HEART1_PPO_TRAJ (per out-of-combat decision: logits, critic
# value, chosen) and STS_SILVER_GUMBEL_STOP_TRACE (per Gumbel root: candidates and scores at each halving boundary).
# No new seeds: the seed must be one of §782's (the §775 block). Known-RNG replay for diagnosis only (ADR-0002).
set -uo pipefail
BIN=$1 SRC=$2 OUT=$3 SEED=$4
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
{ [[ "$SEED" =~ ^[0-9]+$ ]] && [ "$SEED" -ge 111378256 ] && [ "$SEED" -le 111379279 ]; } || { echo "seed $SEED outside the §775 block" >&2; exit 2; }
[ "$(sha256sum < "$BIN/one_combat" | cut -c1-16)" = 112c0f3a84f077ea ] || { echo "bad binary" >&2; exit 2; }
[ "$(sha256sum < "$BIN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad net" >&2; exit 2; }
mkdir -p "$OUT"; b=$OUT/G16-$SEED
rm -f "$b".trace.jsonl* "$b".ppo.jsonl* "$b".roots.csv*
mapfile -t E < <(grep '^STS_' "$SRC/G16-$SEED.env" | grep -v '^STS_OOC_DECISION_TRACE=' | sed "s#^STS_OOC_HEART1=.*#STS_OOC_HEART1=$BIN/net-0420.bin#")
E+=("PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE
    "STS_OOC_DECISION_TRACE=$b.trace.jsonl" "STS_OOC_HEART1_PPO_TRAJ=$b.ppo.jsonl" "STS_SILVER_GUMBEL_STOP_TRACE=$b.roots.csv")
cd "$REPO" || exit 2
t0=$(date +%s)
env -i "${E[@]}" timeout 3h bash tools/seed_guard.sh "$BIN/one_combat" bestbench 16000 1 20 "$SEED" > "$b.log" 2> "$b.err"
rc=$?
for f in "$b.trace.jsonl" "$b.ppo.jsonl" "$b.roots.csv"; do [ -f "$f" ] && gzip -n -9 "$f"; done
echo "seed=$SEED rc=$rc wall=$(( $(date +%s) - t0 ))" > "$b.done"
