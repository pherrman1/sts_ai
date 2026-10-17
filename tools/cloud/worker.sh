#!/usr/bin/env bash
# Generic cloud campaign worker. One fixed entry point for every mass cloud run, so the project's permission
# allowlist (.claude/settings.json) covers all campaigns instead of one new wrapper path per campaign.
#
# A campaign is a directory (normally docs/experiments/evidence/<campaign>/) holding:
#   campaign.manifest  frozen keys, one "key value..." per line (see tools/cloud/README.md)
#   units.txt          one unit per line (arguments for run_unit.sh); line i goes to worker (i mod workers) + 1
#   run_unit.sh        bash run_unit.sh REPO RUN UNIT_OUT <unit args...>; exit 0 = unit done
#
# Worker commands (W is unpadded, 1..workers; run from a clean checkout of the run commit):
#   bash tools/cloud/worker.sh setup  CAMPAIGN W   stage the frozen one_combat (binary cache by sha256, else build)
#                                                  and the frozen inputs under $HOME/cw-<name>-wWW
#   bash tools/cloud/worker.sh start  CAMPAIGN W   start `run` detached (setsid nohup) and return
#   bash tools/cloud/worker.sh run    CAMPAIGN W   run this worker's units (resumable), then upload wWW.tar and
#                                                  wWW.DONE.json to the campaign share dir and mark FINISHED
#   bash tools/cloud/worker.sh wait   CAMPAIGN W [MIN]  block until FINISHED, a failure, or MIN minutes (default 110)
#   bash tools/cloud/worker.sh status CAMPAIGN W
#   bash tools/cloud/worker.sh stop   CAMPAIGN W   start no new units (running ones finish); no upload
# Author / reviewer commands:
#   bash tools/cloud/worker.sh publish-binary CAMPAIGN   build at code_commit, check binary_sha256, put it in the cache
#   bash tools/cloud/worker.sh cache-put FILE [COMMIT]   put a binary into the cache (and a commit pointer)
#   bash tools/cloud/worker.sh cache-get SHA256 DEST     copy a cached binary to DEST (outside the share), chmod +x
set -uo pipefail
stop() { echo "STOP: $*"; exit 1; }
CACHE=${CW_BIN_CACHE:-/mnt/project-files/bin-cache}
SHARE_ROOT=$(realpath -m /mnt/project-files)  # /mnt/project-files is a symlink; compare resolved paths
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || stop "run from inside the repository checkout"
REPO=$(realpath "$REPO")
on_share() { case "$(realpath -m "$1")/" in "$SHARE_ROOT"/*) return 0;; esac; return 1; }
cd "$REPO"
BUILD_INPUTS="apps src include extern cmake CMakeLists.txt CMakePresets.json json pybind11 models selfplay/models"

sha() { sha256sum "$1" | cut -d' ' -f1; }
cache_get() {  # cache_get SHA DEST -> 0 if DEST now holds the binary with that sha
  local f="$CACHE/one_combat-$1"
  [ -f "$f" ] || return 1
  on_share "$2" && stop "binary destination must not be on the share"
  cp "$f" "$2.part" && chmod +x "$2.part" && mv "$2.part" "$2" || return 1
  [ "$(sha "$2")" = "$1" ] || { rm -f "$2"; return 1; }
}
cache_put() {  # cache_put FILE [COMMIT]
  local s; s=$(sha "$1"); mkdir -p "$CACHE" || stop "cannot create $CACHE"
  if [ ! -f "$CACHE/one_combat-$s" ] || [ "$(sha "$CACHE/one_combat-$s")" != "$s" ]; then
    cp "$1" "$CACHE/one_combat-$s.part" && mv "$CACHE/one_combat-$s.part" "$CACHE/one_combat-$s" || stop "cache upload failed"
    cmp -s "$1" "$CACHE/one_combat-$s" || stop "cached copy differs (share full?)"
  fi
  [ -n "${2:-}" ] && echo "$s" > "$CACHE/commit-$2.sha256"
  echo "cached one_combat-$s${2:+ for commit $2}"
}
build_one_combat() {  # build_one_combat TARGET -> path of the built binary on stdout
  git submodule update --init --recursive >/dev/null 2>&1 || stop "submodules"
  cmake --preset linux-gcc-release >/dev/null 2>&1 || stop "configure failed"
  cmake --build build/linux-gcc-release --target "$1" -j"$(nproc)" >/dev/null 2>&1 || stop "build failed"
  echo "$REPO/build/linux-gcc-release/$1"
}

case "${1:-}" in
cache-get) [ $# -eq 3 ] || stop "usage: cache-get SHA256 DEST"; cache_get "$2" "$3" || stop "no cached binary $2"; echo "ok $3"; exit 0 ;;
cache-put) [ $# -ge 2 ] || stop "usage: cache-put FILE [COMMIT]"; cache_put "$2" "${3:-}"; exit 0 ;;
esac

CMD=${1:-} C=${2:-} W=${3:-}
[ -n "$C" ] || stop "usage: worker.sh COMMAND CAMPAIGN_DIR [W]"
D=$(realpath -e "$C" 2>/dev/null) || stop "no campaign dir $C"
case "$D/" in "$REPO"/*) ;; *) stop "campaign dir must be inside the repository checkout";; esac
M="$D/campaign.manifest"
CFILES=("$M" "$D/units.txt" "$D/run_unit.sh")
for f in "${CFILES[@]}"; do
  git ls-files --error-unmatch "$f" >/dev/null 2>&1 || stop "$f is not tracked by git (campaign files must be committed)"
done
git diff --quiet HEAD -- "${CFILES[@]}" || stop "campaign files differ from HEAD"
key() { awk -v k="$1" '$1==k{$1=""; sub(/^ /,""); print; exit}' "$M"; }
NAME=$(key name) CODE=$(key code_commit) BIN=$(key binary_sha256) NW=$(key workers) SHARE=$(key share)
PAR=$(key parallel); PAR=${PAR:-4}
TARGET=$(key build_target); TARGET=${TARGET:-one_combat}
[[ "$NAME" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || stop "manifest name must be lowercase [a-z0-9_-]"
[[ "$NW" =~ ^[1-9][0-9]*$ ]] || stop "manifest workers must be a positive integer"
[[ "$CODE" =~ ^[0-9a-f]{40}$ ]] || stop "manifest code_commit must be a full 40-char sha"
[[ "$SHARE" = /* ]] || stop "manifest share must be an absolute path"

if [ "$CMD" = publish-binary ]; then
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  git diff --quiet "$CODE" HEAD -- $BUILD_INPUTS || stop "HEAD's build inputs differ from code_commit $CODE"
  b=$(build_one_combat "$TARGET"); got=$(sha "$b")
  if [[ "$BIN" =~ ^[0-9a-f]{64}$ ]]; then [ "$got" = "$BIN" ] || stop "built $got != manifest binary_sha256 $BIN ($(g++ --version | head -1))"
  else echo "manifest binary_sha256 is not set; the built binary is $got"; fi
  cache_put "$b" "$CODE"; exit 0
fi

[[ "$BIN" =~ ^[0-9a-f]{64}$ ]] || stop "manifest binary_sha256 must be a 64-char sha256"
[[ "$W" =~ ^[1-9][0-9]*$ ]] && [ "$W" -le "$NW" ] || stop "W must be unpadded 1..$NW (got '$W')"
WW=$(printf %02d "$W") TAG=w$(printf %02d "$W")
RUN=$HOME/cw-$NAME-$TAG OUT=$HOME/cw-$NAME-$TAG/out

my_units() {  # this worker's unit lines, in order
  grep -v '^[[:space:]]*\(#\|$\)' "$D/units.txt" | awk -v n="$NW" -v w="$W" '(NR-1)%n+1==w'
}
unit_id() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_'; }
frozen_identity() {  # what must not change between setup, resume and verify
  echo "campaign=$NAME worker=$W run=$(git rev-parse HEAD) code=$CODE binary=$BIN"
  (cd "$D" && sha256sum campaign.manifest units.txt run_unit.sh)
}
is_running() { [ -e "$RUN/lock" ] && ! flock -n "$RUN/lock" true; }

case $CMD in
setup)
  on_share "$REPO" && stop "checkout must not be on the project share"
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  dup=$(grep -v '^[[:space:]]*\(#\|$\)' "$D/units.txt" | while IFS= read -r u; do unit_id "$u"; echo; done | sort | uniq -d | head -1)
  [ -z "$dup" ] || stop "units.txt has two units with the same id $dup"
  if [ -f "$RUN/FROZEN.txt" ] && ! frozen_identity | cmp -s - "$RUN/FROZEN.txt"; then
    stop "$RUN holds a different freeze (other commit, binary or campaign files); use a fresh container"
  fi
  git diff --quiet "$CODE" HEAD -- $BUILD_INPUTS || stop "run commit changes build inputs or models vs code_commit $CODE"
  [ -e "$RUN/FINISHED" ] && stop "$RUN already finished (container reused); report, do not rerun"
  mkdir -p "$RUN" "$OUT" || stop "cannot create $RUN"
  src=cache
  if ! cache_get "$BIN" "$RUN/one_combat"; then
    src=build; b=$(build_one_combat "$TARGET"); cp "$b" "$RUN/one_combat"
  fi
  got=$(sha "$RUN/one_combat")
  [ "$got" = "$BIN" ] || stop "binary sha256 $got != $BIN (source $src; $(g++ --version | head -1))"
  while read -r k f p s; do
    [ "$k" = input ] || continue
    [[ "$f" =~ ^[A-Za-z0-9._-]+$ ]] || stop "bad input name $f"
    cp "$p" "$RUN/$f" || stop "cannot copy input $p"
    [ "$(sha "$RUN/$f")" = "$s" ] || stop "input $f sha256 $(sha "$RUN/$f") != $s"
  done < "$M"
  frozen_identity > "$RUN/FROZEN.txt"
  echo "source=$src $(g++ --version | head -1) host=$(cat /proc/sys/kernel/random/boot_id) nproc=$(nproc)" > "$RUN/SETUP.txt"
  echo "setup ok: $(head -1 "$RUN/FROZEN.txt") source=$src units=$(my_units | wc -l)" ;;
start)
  [ -f "$RUN/FROZEN.txt" ] || stop "run setup first"
  is_running && stop "already running"
  setsid nohup bash "$SELF" run "$C" "$W" > "$RUN/run.log" 2>&1 < /dev/null &
  echo "started; log $RUN/run.log" ;;
run)
  [ -f "$RUN/FROZEN.txt" ] || stop "run setup first"
  frozen_identity | cmp -s - "$RUN/FROZEN.txt" || stop "checkout no longer matches $RUN/FROZEN.txt; use a fresh container"
  [ -e "$RUN/FINISHED" ] && { echo "already finished"; exit 0; }
  exec 9>"$RUN/lock"; flock -n 9 || stop "another run of this worker holds $RUN/lock"
  my_units > "$OUT/units.txt"; mkdir -p "$OUT/units"
  rm -f "$OUT"/units/*.failed
  xargs -d '\n' -n 1 -P "$PAR" bash "$SELF" _unit "$C" "$W" < "$OUT/units.txt"
  n=$(wc -l < "$OUT/units.txt"); d=$(ls "$OUT"/units/*.done 2>/dev/null | wc -l)
  f=$(ls "$OUT"/units/*.failed 2>/dev/null | wc -l)
  echo "units done: $d/$n failed: $f"
  [ -e "$RUN/STOP" ] && { echo "stopped by request; no upload"; exit 0; }
  [ "$d" = "$n" ] || { echo "STOP: not all units done; rerun 'run' to retry failed units"; exit 3; }
  tar -C "$RUN" -cf "$RUN/$TAG.tar" out FROZEN.txt SETUP.txt || stop "tar failed"
  TSHA=$(sha "$RUN/$TAG.tar")
  python3 - "$RUN/$TAG.DONE.json" "$NAME" "$W" "$OUT/units.txt" "$TSHA" "$RUN/FROZEN.txt" <<'PY' || stop "DONE.json"
import json, sys, datetime
out, name, w, units, tsha, frozen = sys.argv[1:]
lines = [l.rstrip("\n") for l in open(units) if l.strip()]
json.dump({"campaign": name, "worker": int(w), "units": lines, "unit_count": len(lines),
           "tar_sha256": tsha, "frozen": open(frozen).readline().strip(),
           "finished_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
          open(out, "w"), indent=1)
PY
  mkdir -p "$SHARE" || stop "cannot create $SHARE"
  cp "$RUN/$TAG.tar" "$SHARE/$TAG.tar.part" && mv "$SHARE/$TAG.tar.part" "$SHARE/$TAG.tar" || stop "upload failed"
  cmp -s "$RUN/$TAG.tar" "$SHARE/$TAG.tar" || stop "uploaded tar differs (share full?)"
  cp "$RUN/$TAG.DONE.json" "$SHARE/$TAG.DONE.json.part" && mv "$SHARE/$TAG.DONE.json.part" "$SHARE/$TAG.DONE.json" \
    || stop "DONE upload failed"
  cmp -s "$RUN/$TAG.DONE.json" "$SHARE/$TAG.DONE.json" || stop "uploaded DONE.json differs (share full?)"
  touch "$RUN/FINISHED"
  echo "WORKER_OK $TAG tar_sha256=$TSHA" ;;
_unit)
  u=${4:-}; id=$(unit_id "$u"); UO="$OUT/units/$id"
  [ -e "$UO.done" ] && exit 0
  [ -e "$RUN/STOP" ] && exit 0
  rm -rf "$UO" "$UO.log" "$UO.failed"  # a retry starts from an empty dir (one_combat appends to its CSVs)
  mkdir -p "$UO"
  set -f  # unit words are passed unquoted (word split) but never glob-expanded
  # shellcheck disable=SC2086
  if bash "$D/run_unit.sh" "$REPO" "$RUN" "$UO" $u > "$UO.log" 2>&1; then touch "$UO.done"
  else echo "rc=$?" > "$UO.failed"; fi
  exit 0 ;;
wait)
  lim=$(( ${4:-110} * 60 )) t=0
  while [ $t -lt "$lim" ]; do
    [ -e "$RUN/FINISHED" ] && { echo "FINISHED"; tail -1 "$RUN/run.log" 2>/dev/null; exit 0; }
    if ! is_running && { sleep 5; ! is_running && [ ! -e "$RUN/FINISHED" ]; }; then echo "NOT RUNNING"; tail -5 "$RUN/run.log" 2>/dev/null; exit 2; fi
    sleep 60; t=$((t + 60))
  done
  echo "still running after $((lim / 60)) min: $(ls "$OUT"/units/*.done 2>/dev/null | wc -l)/$(wc -l < "$OUT/units.txt") units" ;;
status)
  echo "units done $(ls "$OUT"/units/*.done 2>/dev/null | wc -l)/$(wc -l < "$OUT/units.txt" 2>/dev/null || my_units | wc -l)" \
       "failed $(ls "$OUT"/units/*.failed 2>/dev/null | wc -l) one_combat procs $(pgrep -x one_combat | wc -l)" \
       "$([ -e "$RUN/FINISHED" ] && echo FINISHED)" ;;
stop) mkdir -p "$RUN"; touch "$RUN/STOP"; echo "no new units will start" ;;
*) stop "unknown command '$CMD'" ;;
esac
