#!/usr/bin/env bash
# usage: score.sh BIN ROWS_DIR OUT_DIR MODE [TABLE] -- `one_combat ctmscorerows` of ROWS_DIR/{A,M,S,MS,LC}.jsonl with the
# pathb-a20 stack (Lizard correction on), as used for the README's numbers. MODE: off (STS_CTM_CALIBRATION unset),
# off0 (=0), table (=TABLE; the zero table from `tools/ctm_calibration.py zero` or the fitted one). Run from the repo.
#   A M S MS  the real-combat rows of the stage-3 A/B's four arms: out/units/*/<arm>-*.ctm.jsonl.gz of the 1,024
#             tars in /mnt/project-files/value-level-ab/units/, in path order
#   LC        the rows of the 256 stage 1-2 games: out/units/*/LC-*.ctm.jsonl.gz of the verified value_leaf_compare
#             extraction, in path order
set -euo pipefail
BIN=$1; ROWS=$2; OUT=$3; MODE=$4; TABLE=${5:-}
FAST=selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native
STD=selfplay/models/combat_transition_near_full_escape_pathb_a20.native
mkdir -p "$OUT"
for set in A M S MS LC; do
  case "$MODE" in
    off) env -u STS_CTM_CALIBRATION "$BIN" ctmscorerows "$ROWS/$set.jsonl" "$OUT/$set.csv" "$FAST" "$STD" 1 2> "$OUT/$set.err" ;;
    off0) STS_CTM_CALIBRATION=0 "$BIN" ctmscorerows "$ROWS/$set.jsonl" "$OUT/$set.csv" "$FAST" "$STD" 1 2> "$OUT/$set.err" ;;
    table) STS_CTM_CALIBRATION="$TABLE" "$BIN" ctmscorerows "$ROWS/$set.jsonl" "$OUT/$set.csv" "$FAST" "$STD" 1 2> "$OUT/$set.err" ;;
    *) echo "bad MODE $MODE" >&2; exit 2 ;;
  esac
done
