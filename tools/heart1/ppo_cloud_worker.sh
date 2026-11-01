#!/usr/bin/env bash
# Cloud actor worker for a PPO screen (tools/heart1/ppo_cloud.py). The learner runs elsewhere (`ppo_cloud.py serve`).
# SCREEN/screen.manifest names:
#   code_commit   40-char sha whose build inputs the run commit must equal
#   binary_sha256 the actors' one_combat (from the binary cache, else built at the run commit)
#   store         the ppo_cloud store, e.g. git:https://github.com/OWNER/REPO#ppo-xfer/NAME
# SCREEN/arms.txt lists the arms (name games iterations warmup parts ...); workers 1..sum(parts) take the parts in
# file order: W=1 is part 0 of the first arm, and so on.
# usage:
#   bash tools/heart1/ppo_cloud_worker.sh setup SCREEN W     check checkout, stage one_combat  -> "setup ok ..."
#   bash tools/heart1/ppo_cloud_worker.sh start SCREEN W     start (or resume) this worker's actor in the background
#   bash tools/heart1/ppo_cloud_worker.sh wait  SCREEN W M   wait up to M minutes: FINISHED / NOT RUNNING / still running
set -uo pipefail
CMD=${1:-} D=${2:-} W=${3:-}
stop() { echo "STOP: $*"; exit 1; }
[ -n "$CMD" ] && [ -n "$D" ] && [[ "$W" =~ ^[1-9][0-9]*$ ]] || stop "usage: $0 setup|start|wait SCREEN W [MINUTES]"
REPO=$(git rev-parse --show-toplevel 2>/dev/null) || stop "not in a git checkout"
cd "$REPO" || stop "cannot cd $REPO"
M=$D/screen.manifest
[ -f "$M" ] && [ -f "$D/arms.txt" ] || stop "$M or $D/arms.txt missing"
key() { awk -v k="$1" '$1==k{print $2; exit}' "$M"; }
CODE=$(key code_commit) BIN=$(key binary_sha256) STORE=$(key store)
read -r NAME PART < <(awk -v w="$W" '!/^[[:space:]]*(#|$)/{for (k = 0; k < $5; k++) if (++n == w) {print $1, k; exit}}' \
  "$D/arms.txt")
[ -n "${NAME:-}" ] || stop "W=$W is beyond the screen's $(awk '!/^[[:space:]]*(#|$)/{s+=$5} END{print s}' "$D/arms.txt") workers"
RUN=$HOME/ppo-screen-w$W
PID=$RUN/pid LOG=$RUN/actor.log
BUILD_INPUTS="apps src include extern cmake CMakeLists.txt CMakePresets.json json pybind11 models selfplay/models"
sha() { sha256sum "$1" | cut -d' ' -f1; }

case $CMD in
setup)
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  git diff --quiet "$CODE" HEAD -- $BUILD_INPUTS || stop "run commit changes build inputs vs code_commit $CODE"
  mkdir -p "$RUN" || stop "cannot create $RUN"
  if [ ! -f "$RUN/one_combat" ] || [ "$(sha "$RUN/one_combat")" != "$BIN" ]; then
    c=/mnt/project-files/bin-cache/one_combat-$BIN
    if [ -f "$c" ]; then cp "$c" "$RUN/one_combat.tmp" && mv "$RUN/one_combat.tmp" "$RUN/one_combat"; src=cache
    else
      P=$(cat tools/cloud/default_configure_preset 2>/dev/null || echo linux-gcc-release-x86-64-v3)
      cmake --preset "$P" >/dev/null 2>&1 && cmake --build "build/$P" --target one_combat -j"$(nproc)" >/dev/null 2>&1 \
        || stop "build failed"
      cp "build/$P/one_combat" "$RUN/one_combat"; src=build
    fi
    chmod +x "$RUN/one_combat"
  fi
  [ "$(sha "$RUN/one_combat")" = "$BIN" ] || stop "one_combat sha256 $(sha "$RUN/one_combat") != $BIN"
  python3 tools/heart1/ppo_cloud.py status "$STORE" "$NAME" >/dev/null 2>&1 || stop "cannot read the store $STORE"
  echo "setup ok: worker=$W arm=$NAME part=$PART run=$(git rev-parse HEAD) nproc=$(nproc)" ;;
start)
  [ -f "$RUN/one_combat" ] || stop "run setup first"
  grep -q ACTOR_DONE "$LOG" 2>/dev/null && { echo "already done: $NAME part $PART"; exit 0; }
  if [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; then echo "already running: $NAME part $PART"; exit 0; fi
  nohup python3 tools/heart1/ppo_cloud.py actor "$STORE" "$NAME" --part "$PART" --one-combat "$RUN/one_combat" \
    --threads "$(nproc)" --work "$RUN/work" >> "$LOG" 2>&1 < /dev/null &
  echo $! > "$PID"
  echo "started: $NAME part $PART pid $(cat "$PID")" ;;
wait)
  MIN=${4:-110}
  end=$(( $(date +%s) + 60 * MIN ))
  while :; do
    if grep -q ACTOR_DONE "$LOG" 2>/dev/null; then
      echo "FINISHED"; echo "WORKER_OK ppo-screen w$W $NAME part $PART"; exit 0
    fi
    if ! { [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; }; then
      echo "NOT RUNNING"; tail -5 "$LOG" 2>/dev/null; exit 1
    fi
    [ "$(date +%s)" -ge "$end" ] && { echo "still running: $(tail -1 "$LOG")"; exit 0; }
    sleep 30
  done ;;
*) stop "unknown command $CMD" ;;
esac
