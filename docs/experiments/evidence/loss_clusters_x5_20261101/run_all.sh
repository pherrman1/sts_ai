#!/usr/bin/env bash
# X5 loss clusters (README.md). usage: run_all.sh WORKDIR
# Reads the unit tars of nine A20 campaigns and the §698 fight replays from the project share (read-only),
# builds one pickle per campaign and writes every table to results/. No seeds, no games run.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); W=$1; mkdir -p "$W" "$HERE/results"
declare -A C=([vchooser]=value-chooser-ab [r1]=value-clean-labels-run1 [keys]=key-rules-ab [expanch]=expert-anchored-ab
  [maponly]=ooc-map-only-search [ctmcal]=ctm-calibration-ab [qcap]=gumbel-qcap-ab [vlevel]=value-level-ab [cardrule]=card-rule-ab)
for k in "${!C[@]}"; do [ -s "$W/$k.pkl" ] || python3 "$HERE/extract_all.py" "/mnt/project-files/${C[$k]}" "$k" "$W/$k.pkl" & done; wait
[ -s "$W/aivat.pkl" ] || python3 "$HERE/extract_aivat.py" /mnt/project-files/aivat-replay-676 "$W/aivat.pkl"
cd "$HERE"
for s in clusters potential decksig strikes x4_power aivat_luck; do python3 "$s.py" "$W" > "results/$s.txt"; done
