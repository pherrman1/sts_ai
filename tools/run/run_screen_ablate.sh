#!/bin/bash
# Per-screen OOC gate ablation: which screens contribute to the strategic net's
# winrate? Measures the full gate stack (card + REST/EVENT/SHOP/TREASURE/
# BOSS_RELIC) and then removes one screen at a time. The winrate DROP from
# removing a screen is that screen's isolated contribution.
#
# Uses the corrected honest V4 token net. This harness is diagnostic only;
# it does not promote a model or combine objectives.
#
# Card gate is always ON (no disable flag) and serves as the constant
# background. MAP is off (same as the deployed baseline).
#
# 128 seeds, 1000 sims, fair S3-belief-chain + vnet @64p. Local, 12 threads.
# ~10 min per arm → ~60 min total.
#
# Usage:
#   ./run_screen_ablate.sh                  # 128 seeds, block 126700
#   ./run_screen_ablate.sh 64 126700        # 64 seeds
#   ./run_screen_ablate.sh 128 126700 build # custom output dir
set -euo pipefail
cd "$(dirname "$0")/../.."

NSEEDS=${1:-128}
SEED_OFF=${2:-126700}
SIMS=${3:-1000}
OUTDIR=${4:-build}
BIN=${ONE_COMBAT_BIN:-./build/one_combat}
THREADS=${SCREEN_ABLATE_THREADS:-12}
COLLECT_KEYS=${STS_COLLECT_KEYS:-0}
STOP_AFTER_ACT=${STS_STOP_AFTER_ACT:-3}
if [[ "$COLLECT_KEYS" != 0 && "$COLLECT_KEYS" != 1 ]]; then
  echo "STS_COLLECT_KEYS must be 0 or 1" >&2
  exit 2
fi

# V4 full gate stack: tok net + REST/EVENT/SHOP/TREASURE/BOSS_RELIC, margin 1.0.
# Card gate is always on when the tok net loads (no disable flag). MAP is off.
# When a screen flag is omitted (unset), it defaults to 0 (off).
COMMON=(
  STS_FAIR=1
  STS_SEARCHER3=1
  STS_S3_BELIEF=0
  STS_S3_CHAIN=0
  STS_S3_PARTICLES=64
  STS_S3_LIVE_VALID=1
  STS_VNET=models/v_combat_7k_tuned.txt
  STS_VNET_ALPHA=0.3
  STS_STOP_AFTER_ACT="$STOP_AFTER_ACT"
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
  STS_OOC_STRATEGIC_TOK_CHECK=0
  STS_COLLECT_KEYS="$COLLECT_KEYS"
  STS_OOC_STRATEGIC_MARGIN=1.0
  OMP_NUM_THREADS="$THREADS"
)

echo "== Per-screen OOC gate ablation =="
echo "bin:       $BIN"
echo "threads:   $THREADS"
echo "sims:      $SIMS"
echo "seeds:     $SEED_OFF..$((SEED_OFF+NSEEDS-1))"
echo "gates:     honest V4 tok net + REST/EVENT/SHOP/TREASURE/BOSS_RELIC (card always on, MAP off)"
echo "objective: STS_COLLECT_KEYS=$COLLECT_KEYS (0=Act-3, 1=Heart), STOP_AFTER_ACT=$STOP_AFTER_ACT"
echo

# Verify the net exists
sha256sum selfplay/models/ooc_strategic_tok_final.native

run_arm() {
  local name=$1; shift
  local csv="$OUTDIR/$name"
  rm -f "$csv"
  echo "== $(date +%H:%M:%S) arm $name -> $csv =="
  env OPENBLAS_NUM_THREADS=1 "${COMMON[@]}" "$@" \
    "$BIN" bestbench "$SIMS" "$NSEEDS" 0 "$SEED_OFF" "$csv"
  echo "  done $(date +%H:%M:%S)"
}

# Arm 1: Full stack (card + all 5 screens)
run_arm screen_full_1k_128.csv \
  STS_OOC_STRATEGIC_REST=1 \
  STS_OOC_STRATEGIC_EVENT=1 \
  STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1 \
  STS_OOC_STRATEGIC_BOSS_RELIC=1

# Arm 2: No REST
run_arm screen_no_rest_1k_128.csv \
  STS_OOC_STRATEGIC_EVENT=1 \
  STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1 \
  STS_OOC_STRATEGIC_BOSS_RELIC=1

# Arm 3: No EVENT
run_arm screen_no_event_1k_128.csv \
  STS_OOC_STRATEGIC_REST=1 \
  STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1 \
  STS_OOC_STRATEGIC_BOSS_RELIC=1

# Arm 4: No SHOP
run_arm screen_no_shop_1k_128.csv \
  STS_OOC_STRATEGIC_REST=1 \
  STS_OOC_STRATEGIC_EVENT=1 \
  STS_OOC_STRATEGIC_TREASURE=1 \
  STS_OOC_STRATEGIC_BOSS_RELIC=1

# Arm 5: No TREASURE
run_arm screen_no_treasure_1k_128.csv \
  STS_OOC_STRATEGIC_REST=1 \
  STS_OOC_STRATEGIC_EVENT=1 \
  STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_BOSS_RELIC=1

# Arm 6: No BOSS_RELIC
run_arm screen_no_boss_1k_128.csv \
  STS_OOC_STRATEGIC_REST=1 \
  STS_OOC_STRATEGIC_EVENT=1 \
  STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1

echo
echo "== All arms complete =="
echo

# Quick aggregate (no pandas dependency — pure shell)
for f in "$OUTDIR"/screen_*_1k_128.csv; do
  name=$(basename "$f" .csv)
  if [ -f "$f" ]; then
    won=$(awk -F, 'NR>1{s+=$2} END{printf "%.1f", s/NR*100}' "$f" 2>/dev/null || echo "?")
    n=$(awk -F, 'NR>1{n++} END{print n+0}' "$f" 2>/dev/null || echo "?")
    floor_mean=$(awk -F, 'NR>1{s+=$3;n++} END{printf "%.1f", s/n}' "$f" 2>/dev/null || echo "?")
    printf "%-35s %3s seeds  %5s%%  floor %5s\n" "$name" "$n" "$won" "$floor_mean"
  fi
done

echo
echo "== Paired analysis (each ablation vs full) =="
FULL="$OUTDIR/screen_full_1k_128.csv"
for ablate in rest event shop treasure boss; do
  CSV="$OUTDIR/screen_no_${ablate}_1k_128.csv"
  if [ -f "$CSV" ] && [ -f "$FULL" ]; then
    echo
    python3 paired_analysis.py "$FULL" "$CSV" "full" "no_$ablate"
  fi
done
