#!/usr/bin/env bash
# heart1 distillation students on a CUDA machine. Run from a checkout of branch claude/heart1-distill-data:
#   PY=/path/to/python-with-cuda-torch bash tools/run_gpu.sh [ARM ...]
# Builds daniel-ziegler/sts_lightspeed @84ab3ea's `slaythespire` module (their encoder and NN), collates the captured
# rows once into tensor shards under $WORK, trains the arms in order, and commits + pushes results/<arm>/ after each.
set -euo pipefail
PY=${PY:-python3}
ROOT=$(git rev-parse --show-toplevel); cd "$ROOT"
[ "$(git rev-parse --abbrev-ref HEAD)" = claude/heart1-distill-data ] || { echo "STOP: not on claude/heart1-distill-data"; exit 1; }
WORK=${WORK:-$HOME/h1distill}; SB=$WORK/silverbot-84ab3ea
mkdir -p "$WORK"
"$PY" -c "import torch; assert torch.cuda.is_available(), 'no CUDA'; print('torch', torch.__version__, torch.cuda.get_device_name(0))"
if ! ls "$SB"/build/slaythespire*.so >/dev/null 2>&1; then
  [ -d "$SB/.git" ] || git clone -q https://github.com/daniel-ziegler/sts_lightspeed.git "$SB"
  git -C "$SB" checkout -q 84ab3ea
  git -C "$SB" submodule update --init json pybind11
  cmake -S "$SB" -B "$SB/build" -DCMAKE_BUILD_TYPE=Release -DPYTHON_EXECUTABLE="$(command -v "$PY")" \
        -DPython_EXECUTABLE="$(command -v "$PY")" > "$WORK/sb-cmake.log" 2>&1
  cmake --build "$SB/build" --target slaythespire -j"$(nproc)" > "$WORK/sb-build.log" 2>&1
fi
(cd "$WORK" && "$PY" -c "import sys; sys.path[:0]=['$SB','$SB/build']; import slaythespire; from silverbot import network; print('silverbot ok')")
sha256sum -c tools/data.sha256 --quiet || { echo "STOP: data sha mismatch"; exit 1; }
NP=$(( $(nproc) > 2 ? $(nproc) - 1 : 1 ))
for v in full trim; do
  if [ ! -f "$WORK/shards-$v/DONE" ]; then
    flag=""; [ $v = trim ] && flag=--trim-map
    "$PY" tools/distill.py prep "$SB" "$WORK/shards-$v" --data data/*.capture.jsonl.gz $flag --procs $NP 2>&1 | grep -v Warning | tail -2
    touch "$WORK/shards-$v/DONE"
  fi
done
arm_args() {
  case $1 in
    B_d128_trim) echo "--shards $WORK/shards-trim --dim 128 --layers 2 --mult 2 --heads 4" ;;
    C_d64_trim)  echo "--shards $WORK/shards-trim --dim 64 --layers 2 --mult 4 --heads 4" ;;
    D_d256_trim) echo "--shards $WORK/shards-trim --dim 256 --layers 2 --mult 2 --heads 8" ;;
    A_d128_full) echo "--shards $WORK/shards-full --dim 128 --layers 2 --mult 2 --heads 4" ;;
    *) echo "unknown arm $1" >&2; return 1 ;;
  esac
}
ARMS=("$@"); [ ${#ARMS[@]} -gt 0 ] || ARMS=(B_d128_trim C_d64_trim D_d256_trim A_d128_full)
for arm in "${ARMS[@]}"; do
  [ -f "results/$arm/summary.json" ] && { echo "$arm already done"; continue; }
  mkdir -p "results/$arm"
  "$PY" tools/distill.py train "$SB" "results/$arm" $(arm_args $arm) --epochs 8 --device cuda 2>&1 | grep -v Warning | tee "results/$arm/log.txt"
  git add "results/$arm" && git commit -qm "heart1 distill: results $arm" && git push -q origin claude/heart1-distill-data
  echo "$arm pushed"
done
echo "ALL DONE"
