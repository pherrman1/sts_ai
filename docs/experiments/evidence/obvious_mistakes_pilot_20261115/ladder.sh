#!/usr/bin/env bash
# ladder.sh BIN_DIR OUT_DIR SEED -- issue #1056 pilot, pass 2: the same §782 G16 game played by `one_combat silverazgen`
# (binary 97aec5b5 = code ba705ab4; env = ../budget_ladder_roots_20261112/record_env.sh, i.e. §775's G16 arm, which
# silverazgen reproduces: gumbel_distill_d2_20261110/README.md) with STS_AZGEN_BUDGET_LADDER=64000: after the played
# 16k search of every searched multi-edge root, one fresh Gumbel k 16 + max backup 4 search at 64,000 simulations of the
# same root (own Gumbel seed) records its pick; play is bit-identical with the ladder on or off (budget_ladder SMOKE.md).
# Root rows carry the state (wire), the edges (visits, mean Q, max-backed Q, prior), the played pick and the 64k pick.
# No new seeds (the seed must be in the §775 block). Known-RNG replay, diagnosis only (ADR-0002).
set -uo pipefail
BIN=$1 OUT=$2 SEED=$3
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
{ [[ "$SEED" =~ ^[0-9]+$ ]] && [ "$SEED" -ge 111378256 ] && [ "$SEED" -le 111379279 ]; } || { echo "seed $SEED outside the §775 block" >&2; exit 2; }
[ "$(sha256sum < "$BIN/one_combat_lad" | cut -c1-16)" = 97aec5b5449672cb ] || { echo "bad binary" >&2; exit 2; }
[ "$(sha256sum < "$BIN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad net" >&2; exit 2; }
source "$REPO/docs/experiments/evidence/budget_ladder_roots_20261112/record_env.sh"
E=("${LADDER_ENV[@]/STS_AZGEN_BUDGET_LADDER=*/STS_AZGEN_BUDGET_LADDER=64000}")
mkdir -p "$OUT"; base=$OUT/natural-$SEED
cd "$REPO" || exit 2
t0=$(date +%s)
env -i PATH=/usr/local/bin:/usr/bin:/bin "HOME=$HOME" "${E[@]}" "STS_OOC_HEART1=$BIN/net-0420.bin" \
  STS_EXECUTABLE_GIT_SHA=ba705ab40a08adc505fd402a14cae7dc154b77f3 timeout 6h bash tools/seed_guard.sh "$BIN/one_combat_lad" \
  silverazgen 1 16000 20 "$base" "$SEED" natural 8 1 > "$base.log" 2>&1
rc=$?
[ -s "$base.jsonl" ] && gzip -n -f "$base.jsonl"
echo "seed=$SEED rc=$rc wall=$(( $(date +%s) - t0 )) $(grep -o 'whole-run Gumbel roots=[0-9]* sims=[0-9]*' "$base.log" | tail -1)" > "$base.done"
