#!/usr/bin/env bash
# Cheap rollouts stage 2 (2026-11-13): copy of ../budget_ladder_roots_20261112/run_unit.sh (§797) with
# STS_AZGEN_ROLLOUT_LADDER instead of the budget ladder (record_env.sh): every searched multi-edge prior-playout root is
# searched again by fresh Gumbel searches, one per playout-policy arm; rows add `ladder` (entries with `policy`) and
# `mainCpu`. Same seeds as §797 (the played games are identical; PREREG.md's sentinel checks it).
# usage: run_unit.sh REPO RUN UNIT_OUT VARIANT FIRST_SEED COUNT -- COUNT A20 runs (seeds FIRST_SEED..), variant natural.
# Every searched root is one row (state, edges with visits, mean Q, max-backed Q, root prior, Gumbel pick); every
# fight row carries Silver's end score. Always exits 0 (rc is in .done), except when one_combat was killed by a signal
# (rc 137/143, issue #1001): then exit 3, so the queue re-runs the unit. rc 97 = the manifest does not say it played
# the production out-of-combat chain, production combat with boss prior playouts and the whole-run Gumbel root with
# max backup 4, Act 4 strong and the rollout ladder with its students (manifest "act4Strong": true and the binary's Act 4 strong line); rc 96 = net-0420
# not loaded; rc 98 = seed outside the frozen block.
set -uo pipefail
REPO=$1 RUN=$2 OUT=$3 VARIANT=$4 FIRST=$5 COUNT=$6
[ "$VARIANT" = natural ] || { echo "bad variant $VARIANT" >&2; exit 2; }
[[ "$FIRST" =~ ^[0-9]+$ && "$COUNT" =~ ^[1-9][0-9]*$ ]] || { echo "bad seeds $FIRST $COUNT" >&2; exit 2; }
[ "$(sha256sum < "$RUN/net-0420.bin" | cut -c1-16)" = 8c0bd16c31499270 ] || { echo "bad $RUN/net-0420.bin" >&2; exit 2; }
D=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
CODE=$(awk '$1=="code_commit"{print $2}' "$D/campaign.manifest")
source "$D/record_env.sh"
mkdir -p "$OUT"; base=$OUT/$VARIANT-$FIRST
cd "$REPO" || exit 2
start=$(date -u +%FT%TZ)
rc=0
LAST=$(( FIRST + COUNT - 1 ))
if ! { [ "$FIRST" -ge 111980000 ] && [ "$LAST" -le 111980255 ]; } && ! { [ "$FIRST" -ge 111989990 ] && [ "$LAST" -le 111989999 ]; }; then
  rc=98
else
  env -i PATH=/usr/local/bin:/usr/bin:/bin "HOME=$HOME" "${LADDER_ENV[@]}" "STS_OOC_HEART1=$RUN/net-0420.bin" \
    "STS_EXECUTABLE_GIT_SHA=$CODE" timeout 10h bash tools/seed_guard.sh "$RUN/one_combat" silverazgen "$COUNT" 16000 20 \
    "$base" "$FIRST" "$VARIANT" 8 1 > "$base.log" 2>&1 || rc=$?
fi
[ -s "$base.jsonl" ] && gzip -f "$base.jsonl"
if [ "$rc" = 0 ]; then
  for want in '"oocPlay": "production_chain"' '"combat": "production"' '"prior_playout_rooms": "boss"' \
      '"source": "whole-run STS_SILVER_GUMBEL_ROOT (no override)"' '"maxBackup": 4' '"act4Strong": true' '"rolloutLadder": {' \
      '"ste:16000"' '"THE_HEART": {'; do
    grep -qF "$want" "$base.manifest.json" 2>/dev/null || rc=97
  done
  grep -qF "Act 4 strong (S&S 10k prior playouts, Heart 40k)" "$base.log" || rc=97
  grep -qF "[heart1] loaded $RUN/net-0420.bin " "$base.log" || rc=96
fi
echo "tag=$VARIANT-$FIRST rc=$rc roots=$(grep -o ' roots=[0-9]*' "$base.log" 2>/dev/null | tail -1 | cut -d= -f2) start=$start end=$(date -u +%FT%TZ)" > "$base.done"
case $rc in 137|143) exit 3 ;; esac
exit 0
