#!/usr/bin/env bash
# Generic cloud campaign worker. One fixed entry point for every mass cloud run, so the project's permission
# allowlist (.claude/settings.json) covers all campaigns instead of one new wrapper path per campaign.
#
# A campaign is a directory (normally docs/experiments/evidence/<campaign>/) holding:
#   campaign.manifest  frozen keys, one "key value..." per line (see tools/cloud/README.md)
#   units.txt          one unit per line (arguments for run_unit.sh); line i goes to worker (i mod workers) + 1,
#                      or, with "schedule queue" in the manifest, to whichever worker claims it first (see README)
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
cache_put() {  # cache_put FILE [COMMIT [POINTER_SUFFIX]]
  local s; s=$(sha "$1"); mkdir -p "$CACHE" || stop "cannot create $CACHE"
  if [ ! -f "$CACHE/one_combat-$s" ] || [ "$(sha "$CACHE/one_combat-$s")" != "$s" ]; then
    cp "$1" "$CACHE/one_combat-$s.part" && mv "$CACHE/one_combat-$s.part" "$CACHE/one_combat-$s" || stop "cache upload failed"
    cmp -s "$1" "$CACHE/one_combat-$s" || stop "cached copy differs (share full?)"
  fi
  [ -n "${2:-}" ] && echo "$s" > "$CACHE/commit-$2${3:-}.sha256"
  echo "cached one_combat-$s${2:+ for commit $2${3:-}}"
}
build_one_combat() {  # build_one_combat TARGET -> path of the built binary on stdout (preset $PRESET)
  git submodule update --init --recursive >/dev/null 2>&1 || stop "submodules"
  cmake --preset "$PRESET" >/dev/null 2>&1 || stop "configure failed"
  cmake --build "build/$PRESET" --target "$1" -j"$(nproc)" >/dev/null 2>&1 || stop "build failed"
  echo "$REPO/build/$PRESET/$1"
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
SCHED=$(key schedule); SCHED=${SCHED:-static}
LEASE=$(key lease_minutes); LEASE=${LEASE:-30}
[[ "$SCHED" =~ ^(static|queue)$ ]] || stop "manifest schedule must be static or queue"
[[ "$LEASE" =~ ^[1-9][0-9]*$ ]] || stop "manifest lease_minutes must be a positive integer"
TARGET=$(key build_target); TARGET=${TARGET:-one_combat}
# Without the key, the preset is the one tools/cloud/default_configure_preset names at code_commit, so a
# changed default only reaches campaigns frozen after it; commits without that file use linux-gcc-release.
PRESET=$(key configure_preset)
if [ -z "$PRESET" ]; then
  git cat-file -e "$CODE^{commit}" 2>/dev/null || stop "code_commit $CODE is not in this checkout (fetch it)"
  PRESET=$(git show "$CODE:tools/cloud/default_configure_preset" 2>/dev/null | head -1)
fi
PRESET=${PRESET:-linux-gcc-release}
[[ "$PRESET" =~ ^(linux-gcc-release|linux-gcc-release-x86-64-v3)$ ]] \
  || stop "manifest configure_preset must be linux-gcc-release or linux-gcc-release-x86-64-v3"
if [ "$PRESET" = linux-gcc-release-x86-64-v3 ]; then
  grep -qw avx2 /proc/cpuinfo && grep -qw bmi2 /proc/cpuinfo || stop "configure_preset $PRESET needs an AVX2 CPU"
fi
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
  # Only the default preset writes the plain commit pointer that reviewers read for base binaries;
  # another preset gets its own pointer so it never replaces the default build's.
  if [ "$PRESET" = linux-gcc-release ]; then cache_put "$b" "$CODE"; else cache_put "$b" "$CODE" ".$PRESET"; fi
  exit 0
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

# Queue schedule: units are claimed on the share instead of assigned by line number. A claim is the directory
# $SHARE/claims/<id>.a<n>; its owner rewrites hb ("TAG EPOCH") every minute while the unit runs. A claim whose
# heartbeat is older than lease_minutes, or that holds `failed`, may be superseded by attempt n+1 (at most QMAX
# attempts). A finished unit is uploaded at once as $SHARE/units/<id>.<TAG>.tar, so a worker that dies later loses
# nothing.
# mkdir is atomic only within one container: the share's other containers see a new claim dir late, so two of them
# can both create it. Each worker therefore takes its static units (line i -> worker i mod workers + 1) first, in
# order, and only then takes other workers' unclaimed units, from the end. Each claimer also writes a candidate
# file cand.<KEY>.<TAG>.<pid> into the claim dir. KEY is 0 for the static owner's first attempt, so that claim
# needs no wait. Every other claimer waits claim_settle_seconds, lists the candidates, and runs the unit only if
# its own candidate sorts first (KEY = claim epoch). A duplicate is still possible when a candidate stays
# invisible for longer than the settle time; verify_campaign.py then reports it and keeps the first tar.
QMAX=4
QDIR=$SHARE/claims UDIR=$SHARE/units
SETTLE=$(key claim_settle_seconds); SETTLE=${SETTLE:-60}
[[ "$SETTLE" =~ ^[0-9]+$ ]] || stop "manifest claim_settle_seconds must be a non-negative integer"
pending_units() {  # unit lines without an uploaded tar: this worker's static units in order, then the others reversed
  local have; have=$(ls "$UDIR" 2>/dev/null | sed -n 's/\.w[0-9][0-9]*\.tar$//p' | sort -u)
  grep -v '^[[:space:]]*\(#\|$\)' "$D/units.txt" | awk -v n="$NW" -v w="$W" \
      '{ printf "%d %d %s\n", (NR-1)%n+1!=w, (NR-1)%n+1==w ? NR : -NR, $0 }' | sort -k1,1n -k2,2n | cut -d' ' -f3- \
    | while IFS= read -r u; do
    grep -qxF -- "$(unit_id "$u")" <<< "$have" || printf '%s\n' "$u"
  done
}
is_mine() {  # is_mine UNIT_LINE -> 0 if the static schedule gives the unit to this worker
  local i; i=$(grep -v '^[[:space:]]*\(#\|$\)' "$D/units.txt" | grep -nxF -m1 -- "$1" | cut -d: -f1)
  [ -n "$i" ] && [ $(( (i - 1) % NW + 1 )) = "$W" ]
}
try_claim() {  # try_claim ID MINE -> prints the claim dir; 1 = claimed by another worker, 2 = out of attempts
  local id=$1 mine=$2 n=1 c hb age key cand first
  # CW_TEST_SPLIT_SHARE (tests only) plays a container that sees none of the others' claims yet.
  [ -n "${CW_TEST_SPLIT_SHARE:-}" ] || while [ -d "$QDIR/$id.a$n" ]; do n=$((n + 1)); done
  if [ "$n" -gt 1 ]; then
    c="$QDIR/$id.a$((n - 1))"
    if [ ! -e "$c/failed" ]; then
      hb=$(cut -d' ' -f2 "$c/hb" 2>/dev/null); [[ "$hb" =~ ^[0-9]+$ ]] || hb=$(stat -c %Y "$c" 2>/dev/null || echo 0)
      age=$(( $(date +%s) - hb )); [ "$age" -lt $((LEASE * 60)) ] && return 1
    fi
    [ "$n" -gt "$QMAX" ] && return 2
  fi
  c="$QDIR/$id.a$n"
  if [ -n "${CW_TEST_SPLIT_SHARE:-}" ]; then mkdir -p "$c" || return 1   # tests: every claimer "wins" the mkdir
  else mkdir "$c" 2>/dev/null || return 1; fi
  key=$(date +%s); [ "$n" = 1 ] && [ "$mine" = 1 ] && key=0
  cand="cand.$key.$TAG.$BASHPID"
  : > "$c/$cand" || return 1
  if [ "$key" != 0 ]; then
    sleep "$SETTLE"
    first=$(ls "$c" | grep '^cand\.' | sort -t. -k2,2n -k3,3 -k4,4n | head -1)
    [ "$first" = "$cand" ] || return 1
  fi
  echo "$TAG $(date +%s)" > "$c/hb"
  echo "$c"
}
# Central stop (queue only): the lead ends an open-ended campaign for all workers at once by creating SHARE/STOP,
# or SHARE/STOP_AT holding an epoch (no lane claims a new unit at or after it). Running units finish and upload;
# `run` then writes DONE.json and FINISHED as for a complete queue. A missing or unreadable file means "go on".
central_stop() {
  [ -e "$SHARE/STOP" ] && return 0
  local t; t=$(head -c 32 "$SHARE/STOP_AT" 2>/dev/null | tr -dc 0-9)
  [ -n "$t" ] && [ "$(date +%s)" -ge "$t" ]
}
upload_unit() {  # upload_unit ID -> $UDIR/<id>.<TAG>.tar (unit dir, markers, FROZEN.txt, SETUP.txt)
  local id=$1 t="$RUN/q/$1.$TAG.tar"
  mkdir -p "$RUN/q" "$UDIR" || return 1
  tar -C "$RUN" -cf "$t" "out/units/$id" "out/units/$id.done" "out/units/$id.log" FROZEN.txt SETUP.txt || return 1
  cp "$t" "$UDIR/$id.$TAG.tar.part" && mv "$UDIR/$id.$TAG.tar.part" "$UDIR/$id.$TAG.tar" || return 1
  cmp -s "$t" "$UDIR/$id.$TAG.tar"
}

case $CMD in
setup)
  on_share "$REPO" && stop "checkout must not be on the project share"
  [ -z "$(git status --porcelain --untracked-files=no)" ] || stop "checkout not clean"
  dup=$(grep -v '^[[:space:]]*\(#\|$\)' "$D/units.txt" | while IFS= read -r u; do unit_id "$u"; echo; done | sort | uniq -d | head -1)
  [ -z "$dup" ] || stop "units.txt has two units with the same id $dup"
  bad=$(grep -v '^[[:space:]]*\(#\|$\)' "$D/units.txt" | while IFS= read -r u; do unit_id "$u"; echo; done | grep -m1 '^\.')
  [ -z "$bad" ] || stop "unit id '$bad' starts with a dot; unit lines must not start with '.'"
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
  echo "setup ok: $(head -1 "$RUN/FROZEN.txt") source=$src units=$([ "$SCHED" = queue ] && echo queue || my_units | wc -l)" ;;
start)
  [ -f "$RUN/FROZEN.txt" ] || stop "run setup first"
  is_running && stop "already running"
  setsid nohup bash "$SELF" run "$C" "$W" >> "$RUN/run.log" 2>&1 < /dev/null &  # append: keep earlier attempts' log
  echo "started; log $RUN/run.log" ;;
run)
  [ -f "$RUN/FROZEN.txt" ] || stop "run setup first"
  frozen_identity | cmp -s - "$RUN/FROZEN.txt" || stop "checkout no longer matches $RUN/FROZEN.txt; use a fresh container"
  [ -e "$RUN/FINISHED" ] && { echo "already finished"; exit 0; }
  exec 9>"$RUN/lock"; flock -n 9 || stop "another run of this worker holds $RUN/lock"
  if [ "$SCHED" = queue ]; then
    mkdir -p "$OUT/units" "$QDIR" "$UDIR" || stop "cannot create $OUT/units or the share's claims/units dirs"
    grep -v '^[[:space:]]*\(#\|$\)' "$D/units.txt" > "$OUT/units.txt"   # all units: any worker may run any of them
    rm -f "$OUT"/units/*.failed
    for l in $(seq 0 $((PAR - 1))); do bash "$SELF" _qlane "$C" "$W" "$l" & done
    wait
    [ -e "$RUN/STOP" ] && { echo "stopped by request; no upload"; exit 0; }
    cstop=0; central_stop && cstop=1
    left=$(pending_units | wc -l)
    [ "$left" = 0 ] || [ "$cstop" = 1 ] || { echo "STOP: $left units failed $QMAX times (claims/<id>.a*/failed); report them, do not rerun"; exit 3; }
    ls "$UDIR" | sed -n "s/\.$TAG\.tar\$//p" > "$OUT/uploaded.txt"
    python3 - "$RUN/$TAG.DONE.json" "$NAME" "$W" "$OUT/uploaded.txt" "$RUN/FROZEN.txt" "$cstop" <<'PY' || stop "DONE.json"
import json, sys, datetime
out, name, w, units, frozen, cstop = sys.argv[1:]
ids = [l.strip() for l in open(units) if l.strip()]
json.dump({"campaign": name, "worker": int(w), "schedule": "queue", "uploaded_unit_ids": ids, "unit_count": len(ids),
           "frozen": open(frozen).readline().strip(), "central_stop": cstop == "1",
           "finished_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
          open(out, "w"), indent=1)
PY
    cp "$RUN/$TAG.DONE.json" "$SHARE/$TAG.DONE.json.part" && mv "$SHARE/$TAG.DONE.json.part" "$SHARE/$TAG.DONE.json" \
      || stop "DONE upload failed"
    touch "$RUN/FINISHED"
    echo "WORKER_OK $TAG queue units_uploaded=$(wc -l < "$OUT/uploaded.txt")$([ "$cstop" = 1 ] && echo " central_stop")"
    exit 0
  fi
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
  case "$id" in ''|.*) echo "rc=bad-id" > "$OUT/units/_bad_id.failed"; exit 0;; esac  # never rm -rf "$OUT/units/.."
  [ -e "$UO.done" ] && exit 0
  [ -e "$RUN/STOP" ] && exit 0
  rm -rf "$UO" "$UO.log" "$UO.failed"  # a retry starts from an empty dir (one_combat appends to its CSVs)
  mkdir -p "$UO"
  set -f  # unit words are passed unquoted (word split) but never glob-expanded
  # shellcheck disable=SC2086
  if bash "$D/run_unit.sh" "$REPO" "$RUN" "$UO" $u > "$UO.log" 2>&1; then touch "$UO.done"
  else echo "rc=$?" > "$UO.failed"; fi
  exit 0 ;;
_qlane)  # one queue lane: claim the first claimable pending unit, run it, upload it; idle-poll until none is left
  sleep $(( ${4:-0} * 3 ))   # stagger the lanes' first scans
  while :; do
    [ -e "$RUN/STOP" ] && exit 0
    central_stop && exit 0
    mapfile -t todo < <(pending_units)
    [ "${#todo[@]}" -eq 0 ] && exit 0
    ran=0 exhausted=0
    for u in "${todo[@]}"; do
      id=$(unit_id "$u"); UO="$OUT/units/$id"
      case "$id" in ''|.*) continue;; esac
      if [ -e "$UO.done" ]; then upload_unit "$id" || echo "upload of $id failed" >&2; ran=1; break; fi  # resumed worker
      mine=0; is_mine "$u" && mine=1
      c=$(try_claim "$id" "$mine"); rc=$?
      [ "$rc" = 2 ] && exhausted=$((exhausted + 1))
      [ "$rc" = 0 ] || continue
      ( while sleep 60; do echo "$TAG $(date +%s)" > "$c/hb.part" && mv "$c/hb.part" "$c/hb"; done ) & hbp=$!
      rm -rf "$UO" "$UO.log" "$UO.failed"; mkdir -p "$UO"
      set -f
      # shellcheck disable=SC2086
      if bash "$D/run_unit.sh" "$REPO" "$RUN" "$UO" $u > "$UO.log" 2>&1; then touch "$UO.done"
      else echo "rc=$?" > "$UO.failed"; fi
      set +f
      kill "$hbp" 2>/dev/null; wait "$hbp" 2>/dev/null
      if [ -e "$UO.done" ] && upload_unit "$id"; then echo "$TAG $(date +%s) done" > "$c/hb"
      else cp "$UO.failed" "$c/failed" 2>/dev/null || echo "rc=upload" > "$c/failed"; fi
      ran=1; break
    done
    [ "$exhausted" -eq "${#todo[@]}" ] && exit 0   # only units that failed QMAX times are left
    [ "$ran" = 1 ] || sleep 120   # every pending unit is claimed by a live worker: wait for it or for its lease
  done ;;
_claim)  # tests: _claim CAMPAIGN W ID MINE -> try_claim's output and exit code
  mkdir -p "$QDIR" || exit 1
  try_claim "$4" "$5"; exit $? ;;
wait)
  lim=$(( ${4:-110} * 60 )) t=0
  while [ $t -lt "$lim" ]; do
    [ -e "$RUN/FINISHED" ] && { echo "FINISHED"; tail -1 "$RUN/run.log" 2>/dev/null; exit 0; }
    if ! is_running && { sleep 5; ! is_running && [ ! -e "$RUN/FINISHED" ]; }; then echo "NOT RUNNING"; tail -5 "$RUN/run.log" 2>/dev/null; exit 2; fi
    sleep 60; t=$((t + 60))
  done
  [ -e "$RUN/FINISHED" ] && { echo "FINISHED"; tail -1 "$RUN/run.log" 2>/dev/null; exit 0; }
  echo "still running after $((lim / 60)) min: $(ls "$OUT"/units/*.done 2>/dev/null | wc -l)/$(wc -l < "$OUT/units.txt") units" ;;
status)
  [ "$SCHED" = queue ] && { echo "queue: pending $(pending_units | wc -l)/$(grep -cv '^[[:space:]]*\(#\|$\)' "$D/units.txt")" \
       "this worker done $(ls "$OUT"/units/*.done 2>/dev/null | wc -l) one_combat procs $(pgrep -x one_combat | wc -l)" \
       "$([ -e "$RUN/FINISHED" ] && echo FINISHED)"; exit 0; }
  echo "units done $(ls "$OUT"/units/*.done 2>/dev/null | wc -l)/$(wc -l < "$OUT/units.txt" 2>/dev/null || my_units | wc -l)" \
       "failed $(ls "$OUT"/units/*.failed 2>/dev/null | wc -l) one_combat procs $(pgrep -x one_combat | wc -l)" \
       "$([ -e "$RUN/FINISHED" ] && echo FINISHED)" ;;
stop) mkdir -p "$RUN"; touch "$RUN/STOP"; echo "no new units will start" ;;
*) stop "unknown command '$CMD'" ;;
esac
