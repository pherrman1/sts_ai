#!/usr/bin/env bash
# per-encounter fine-tune of run A (W256p): 3 epochs, lr 2e-4, encounter's train rows only; waits for run C.
T=$HOME/sts-rolloutprior/tools/rollout_prior/train.py; D=$HOME/Documents/sts/train-1053; P=$HOME/Documents/sts/factory-data/factory12_playout.npz
while pgrep -f "train-1053/W256pg " >/dev/null; do sleep 30; done
for e in HEXAGHOST CHAMP SLIME_BOSS THE_GUARDIAN COLLECTOR TIME_EATER DONU_AND_DECA SHIELD_AND_SPEAR THE_HEART AWAKENED_ONE AUTOMATON; do
  s=$(echo $e | tr 'A-Z_' 'a-z-'); o=$D/enc/$s
  [ -f $o/train.json ] && { echo "kept $e"; continue; }
  python3 -P -u $T fit $P $o --target visits --rooms playout --h1 256 --h2 128 --device cuda --threads 8 --init $D/W256/model.pt --encounter $e --epochs 3 --lr 2e-4 > $D/enc/$s.log 2>&1 || { echo "FAILED $e"; exit 1; }
  python3 -P $T export $o/model.pt $D/enc/rp_W256p_$s.txt $D/NAMES.json > /dev/null && echo "DONE $e"
done
echo ENC_DONE
