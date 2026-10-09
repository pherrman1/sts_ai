#!/usr/bin/env bash
# #418 live CTM A/B, cloud venue (DEVIATIONS.md). Runs the frozen PREREG.md harness unchanged on worker W (1..4).
# Run from the repo checkout at the run commit, with bash (never from /mnt/project-files).
#   cloud_worker.sh setup  W BINARY   verify inputs, extract the harness from PREREG.md, freeze (idempotent on resume)
#   cloud_worker.sh smoke  W          worker 1 only: PREREG 7.4 on seed 63009000 -> w01/SMOKE_PASS or SMOKE_FAIL
#   cloud_worker.sh run    W          waits for w01/SMOKE_PASS, runs this worker's 12 units (J=4), writes DONE.txt
#   cloud_worker.sh status W          progress
#   cloud_worker.sh combine OUTDIR    gather w01..w04 into OUTDIR/run and run the frozen analysis
set -euo pipefail
EV=docs/experiments/evidence/ctm_live_ab_418_20261009
SHARE=/mnt/project-files/ctm-pathb/live-ab-cloud
GITSHA=648334e38dc5c92bc57a9b531f2f9f3308a732ff          # frozen build commit (STS_EXECUTABLE_GIT_SHA in arm_env.sh)
BIN_SHA=dddb09f099a3a88994b23178b96e70346ac877c4d4deaf2d786df184972c7169
J=4
declare -A PIN=(                                          # files reviewed at 3b5d77c2
  [PREREG.md]=3e62bef76a305e0775c3d2f952e89c66e2c5ccafa84d8e43fbcd2d13800ee081
  [live_ab_analyze.py]=510ccf0dbb35c8caeb1203526a9e4aa8f41d29975eeb392d1e2731d9534d8d3c
  [arm_env.sh]=b9ec0bc4b0767fb16379c9d2dd1cd0c9f47d69be701e44947bd317a5e22cf128
  [run_unit.sh]=980779a44ac4dd19e1fdce7327b6a855218a0c02b8b9f3d90582db03902bd344
  [launch.sh]=d5088563fbd59933ea24872fd084425d7611b22f77795e128a84e9d49e5ce3a4
  [units.all.txt]=7a9b8ba8a6367b6e78a29018e52c2059935096ccda587ba9f9343cd2556a3ffa
  [FAST-final.native]=90806c25d784f7100b35ec755ad93756bf34d5aa297591891d5d3bb4314ba4f3
  [STD1-escape.native]=b9188de03ed6cc0611094c108f607a8770a5d5c5f367c157851bc6af91f8d9cf
  [candidate-v3.json]=d9d8377e19a37fd3a76dc3ebae0c882706d11d4bd0b4a3df41691e3cf4d39d5d)
MODELS=(                                                   # PREREG section 6
  "abb2a9ead6efd6b97ee64192e0459eb08ceff7fd93f2b5f4b87a0bf379e571ab selfplay/models/combat_transition_deepsets_lizard_t2.native"
  "e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd selfplay/models/combat_transition_near_full_except_smoke_v2.native"
  "e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c selfplay/models/ooc_strategic_tok_final.native"
  "fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70 models/v_win_trees.txt"
  "3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3 models/v_rich_trees.txt"
  "a251b33d4f71c1aa3fca529801da23ea9740dd0ded58abfb1a90fe69da7c9acf models/candidates/v_win_x2b_trees.txt"
  "8e2f9dc78cb31de382c876888a33007efc8a0526103b2c274d3980fc0915e051 models/candidates/screen_leaf_gbm_v1.trees")
BUILD_INPUTS=(apps src include CMakeLists.txt CMakePresets.json json pybind11 models selfplay/models
              tools/seed_guard.sh tools/agent/check_benchmark_canary.py)

die() { echo "STOP: $*" >&2; exit 1; }
sha() { sha256sum "$1" | cut -d' ' -f1; }
pin() { [ "$(sha "$2")" = "${PIN[$1]}" ] || die "$1 sha256 $(sha "$2") != ${PIN[$1]}"; }
cmd=${1:-}; shift || true
WT=$(git rev-parse --show-toplevel 2>/dev/null) || die "run from the repo checkout"
cd "$WT"
case "$WT" in /mnt/project-files*) die "the checkout must not be on /mnt/project-files (noexec)";; esac
worker() { [[ "${1:-}" =~ ^[1-4]$ ]] || die "W must be 1..4"; W=$1; WW=$(printf %02d "$W")
  LAB=$HOME/liveab-w$WW; OUTS=$SHARE/w$WW; }

extract() {   # extract DELIM OUT: the body of PREREG.md's `<<'DELIM'` heredoc, byte-exact as bash writes it
  awk -v d="$1" 'f && $0==d {exit} f {print} !f && index($0, "<<'"'"'" d "'"'"'") {f=1}' "$EV/PREREG.md" > "$2"; }

frozen_lines() {   # sha256 + basename of every frozen input, then settings (no paths: identical across workers)
  for f in "$LAB/bin/one_combat" "$LAB/cand/FAST-final.native" "$LAB/cand/STD1-escape.native" \
           "$LAB/cand/candidate-v3.json" "$EV/PREREG.md" "$LAB/live_ab_analyze.py" "$LAB/arm_env.sh" \
           "$LAB/run_unit.sh" "$LAB/launch.sh" "$LAB/units.all.txt"; do echo "$(sha "$f")  $(basename "$f")"; done
  for m in "${MODELS[@]}"; do echo "${m%% *}  ${m#* }"; done
  echo "binary build $GITSHA  J=$J per worker  workers=4"
}

setup() {
  worker "${1:-}"; local bin=${2:-}; [ -f "$bin" ] || die "usage: setup W BINARY"
  [ "$(nproc)" -ge "$J" ] || die "need >= $J CPUs"
  git diff --quiet "$GITSHA" HEAD -- "${BUILD_INPUTS[@]}" || die "build inputs differ from $GITSHA"
  [ -z "$(git status --porcelain -- "${BUILD_INPUTS[@]}" "$EV")" ] || die "checkout is dirty"
  pin PREREG.md "$EV/PREREG.md"; pin live_ab_analyze.py "$EV/live_ab_analyze.py"
  [ "$(sha "$bin")" = "$BIN_SHA" ] || die "binary sha256 $(sha "$bin") != $BIN_SHA (do not run; report)"
  for m in "${MODELS[@]}"; do [ "$(sha "${m#* }")" = "${m%% *}" ] || die "model ${m#* } differs"; done
  mkdir -p "$LAB"/{bin,cand}
  cp "$bin" "$LAB/bin/one_combat"; chmod +x "$LAB/bin/one_combat"     # basename one_combat: seed_guard needs it
  cp "$SHARE"/candidate/{FAST-final.native,STD1-escape.native,candidate-v3.json,SHA256SUMS.txt} "$LAB/cand/"
  (cd "$LAB/cand" && sha256sum -c SHA256SUMS.txt) || die "candidate SHA256SUMS"
  for f in FAST-final.native STD1-escape.native candidate-v3.json; do pin "$f" "$LAB/cand/$f"; done
  extract ARM_ENV "$LAB/arm_env.sh"; extract RUN_UNIT "$LAB/run_unit.sh"; extract LAUNCH "$LAB/launch.sh"
  for f in arm_env.sh run_unit.sh launch.sh; do pin "$f" "$LAB/$f"; done
  cp "$EV/live_ab_analyze.py" "$LAB/live_ab_analyze.py"
  { for b in $(seq 0 15); do lo=$((63000000 + 8 * b))          # PREREG 7.2 generator, verbatim
      if [ $((b % 2)) -eq 0 ]; then echo "prod $lo 8"; echo "cand $lo 8"; else echo "cand $lo 8"; echo "prod $lo 8"; fi
    done
    for b in $(seq 0 15); do echo "off $((63000000 + 8 * b)) 8"; done; } > "$LAB/units.all.txt"
  pin units.all.txt "$LAB/units.all.txt"
  # this worker's share: blocks b with b % 4 == W-1, all three arms, in the frozen order
  awk -v w="$W" '((($2 - 63000000) / 8) % 4) == w - 1' "$LAB/units.all.txt" > "$LAB/units.txt"
  [ "$(wc -l < "$LAB/units.txt")" = 12 ] || die "expected 12 units"
  python3 -I "$LAB/live_ab_analyze.py" selftest | tail -1 | grep -qx "selftest OK" || die "analysis selftest"
  mkdir -p "$OUTS"/{run,logs}; ln -sfn "$OUTS/run" "$LAB/run"; ln -sfn "$OUTS/logs" "$LAB/logs"
  if [ "$W" = 1 ]; then mkdir -p "$OUTS/smoke"; ln -sfn "$OUTS/smoke" "$LAB/smoke"; fi
  frozen_lines > "$LAB/FROZEN.lines"
  if [ -f "$OUTS/PREREG-FROZEN.txt" ]; then                    # resume after a container restart
    diff <(tail -n +4 "$OUTS/PREREG-FROZEN.txt") "$LAB/FROZEN.lines" || die "frozen inputs changed since the first setup"
    echo "resume $(date -u +%FT%TZ) HEAD $(git rev-parse HEAD)" >> "$OUTS/logs/RESUMES.txt"
  else
    { date -u +%FT%TZ; echo "worker $W  run checkout HEAD $(git rev-parse HEAD)"
      python3 -I -c "import numpy, sys; print('python', sys.version.split()[0], 'numpy', numpy.__version__)"
      cat "$LAB/FROZEN.lines"; } > "$OUTS/PREREG-FROZEN.txt"
    cp "$LAB/units.txt" "$OUTS/units.txt"
  fi
  cat "$OUTS/PREREG-FROZEN.txt"; echo "setup ok: worker $W units:"; cat "$LAB/units.txt"
}

smoke() {   # PREREG 7.4, worker 1 only
  worker "${1:-}"; [ "$W" = 1 ] || die "only worker 1 runs the smoke"
  [ -f "$LAB/FROZEN.lines" ] || die "run setup first"
  [ -f "$OUTS/SMOKE_PASS" ] && { echo "smoke already passed"; return 0; }
  [ -f "$OUTS/SMOKE_FAIL" ] && die "smoke already failed: see $OUTS/SMOKE_FAIL"
  local fail=() a
  for a in prod cand off; do bash "$LAB/run_unit.sh" "$WT" "$LAB" "$LAB/smoke" $a 63009000 1 & done; wait
  for a in prod cand off; do
    grep -q " rc=0 " "$LAB/smoke/$a-63009000.done" || fail+=("$a rc")
    python3 -I tools/agent/check_benchmark_canary.py --results "$LAB/smoke/$a-63009000.csv" \
      --meta "$LAB/smoke/$a-63009000.csv.meta.json" --log "$LAB/smoke/$a-63009000.log" --expect-backend native_silver \
      --expect-seeds 1 --expect-sims 10000 --expect-seed-lo 63009000 --expect-asc 0 --expect-threads 1 --expect-fair \
      --no-expect-searcher3 --expect-executable-sha $GITSHA --binary "$LAB/bin/one_combat" \
      --expect-binary-sha256 $BIN_SHA > "$OUTS/logs/smoke.canary.$a.txt" 2>&1 || fail+=("$a canary")
  done
  python3 -I "$LAB/live_ab_analyze.py" check "$LAB/smoke" --seed-lo 63009000 --seed-count 1 --block 1 \
    --git-sha $GITSHA > "$OUTS/logs/smoke.check.txt" 2>&1 || fail+=("integrity")
  grep -q "\[ctm-research-candidate\] candidate_id=pathb-r2" "$LAB/smoke/cand-63009000.log" || fail+=("cand line missing")
  ! grep -q "\[ctm-research-candidate\]" "$LAB/smoke/prod-63009000.log" || fail+=("cand line in prod")
  ! grep -q "startup failure" "$LAB"/smoke/*.log || fail+=("startup failure")
  python3 -I -c "import csv;s={a:float(next(csv.DictReader(open(f'$LAB/smoke/{a}-63009000.csv')))['sec']) for a in ('prod','cand','off')};print(s,'projected_h_per_worker',round(32*sum(s.values())/$J/3600,2))" \
    >> "$OUTS/logs/smoke.check.txt" 2>&1 || fail+=("projection")
  if [ ${#fail[@]} -eq 0 ]; then { date -u +%FT%TZ; tail -1 "$OUTS/logs/smoke.check.txt"; } > "$OUTS/SMOKE_PASS"; cat "$OUTS/SMOKE_PASS"
  else printf '%s\n' "${fail[@]}" > "$OUTS/SMOKE_FAIL"; die "smoke failed: ${fail[*]}"; fi
}

run() {
  worker "${1:-}"; [ -f "$LAB/FROZEN.lines" ] || die "run setup first"
  [ -f "$SHARE/w01/SMOKE_FAIL" ] && die "worker 1 smoke failed"
  [ -f "$SHARE/w01/SMOKE_PASS" ] || die "worker 1 smoke has not passed yet; retry later"
  echo "launch $(date -u +%FT%TZ)" >> "$OUTS/logs/launches.txt"
  bash "$LAB/launch.sh" "$WT" "$LAB" $J > "$OUTS/logs/launch.log" 2>&1 || true
  [ -f "$LAB/run/DONE" ] || die "units not all done; see status, rerun the same command to resume"
  { echo "worker=$W finished=$(date -u +%FT%TZ) units=$(ls "$LAB"/run/*.done | wc -l)"
    cat "$LAB"/run/*.done | grep -o " rc=[0-9-]*" | sort | uniq -c
    grep -h "bestbench-seed-failure" "$LAB"/run/*.log || echo "no seed failures"
    cat "$LAB/logs/RESTARTS.txt" 2>/dev/null || true
    (cd "$OUTS/run" && find . -maxdepth 1 -type f -name '*-630*' | sort | xargs sha256sum)
  } > "$OUTS/DONE.txt"
  head -8 "$OUTS/DONE.txt"
}

status() {
  worker "${1:-}"
  echo "done $(ls "$OUTS"/run/*.done 2>/dev/null | wc -l)/12; running $(pgrep -fc 'bestbench 10000' || true)"
  grep -h "bestbench-seed-failure" "$OUTS"/run/*.log 2>/dev/null || true
  cat "$OUTS"/run/*.done 2>/dev/null || true
}

combine() {   # gather w01..w04 into a fresh local tree and run the frozen analysis
  local out=${1:-}; [ -n "$out" ] && [ ! -e "$out" ] || die "usage: combine NEW_DIR"
  case "$out" in /mnt/project-files*) die "combine into a local dir, then copy the report";; esac
  pin live_ab_analyze.py "$EV/live_ab_analyze.py"; mkdir -p "$out/run"
  local first="" w
  for w in 01 02 03 04; do
    [ -f "$SHARE/w$w/DONE.txt" ] || die "w$w has no DONE.txt"
    if [ -z "$first" ]; then first=w$w; elif ! diff -q <(tail -n +4 "$SHARE/$first/PREREG-FROZEN.txt") \
         <(tail -n +4 "$SHARE/w$w/PREREG-FROZEN.txt") > /dev/null; then die "w$w froze different inputs"; fi
    find "$SHARE/w$w/run" -maxdepth 1 -type f -name '*-630*' -exec cp -t "$out/run" {} +
  done
  [ "$(ls "$out"/run/*.done | wc -l)" = 48 ] || die "expected 48 units"
  python3 -I "$EV/live_ab_analyze.py" analyze "$out/run" --seed-lo 63000000 --seed-count 128 --git-sha $GITSHA \
    --out "$out/report.json" | tee "$out/report.summary.json"
}

case "$cmd" in
  setup) setup "$@" ;; smoke) smoke "$@" ;; run) run "$@" ;; status) status "$@" ;; combine) combine "$@" ;;
  *) die "usage: cloud_worker.sh setup W BINARY | smoke W | run W | status W | combine NEW_DIR" ;;
esac
