#!/usr/bin/env bash
# OOC MCTS root-selection x cpuct screen (PREREG.md in this folder). Worker W of 32, 4 CPUs each.
# Copy this file to $HOME first (never run it from /mnt/project-files), from the repo checkout at 648334e3:
#   worker.sh setup W    build one_combat, check every frozen hash, copy candidate CTM files, freeze
#   worker.sh smoke 1    worker 1 only: 8 arms x seed 65009000 -> SMOKE_PASS or SMOKE_FAIL
#   worker.sh run W      waits for SMOKE_PASS, runs this worker's 16 units (4 at a time), writes wWW/DONE.txt
#   worker.sh status W   progress
set -euo pipefail
SHARE=/mnt/project-files/ooc-mcts-q-select-screen
GITSHA=648334e38dc5c92bc57a9b531f2f9f3308a732ff
BIN_SHA=dddb09f099a3a88994b23178b96e70346ac877c4d4deaf2d786df184972c7169
NW=32 J=4 SEED_LO=65000000 NSEED=128 PER=2 SMOKE_SEED=65009000
ARMS=(v05 v10 v15 v30 q05 q10 q15 q30)
declare -A CAND=(
  [FAST-final.native]=90806c25d784f7100b35ec755ad93756bf34d5aa297591891d5d3bb4314ba4f3
  [STD1-escape.native]=b9188de03ed6cc0611094c108f607a8770a5d5c5f367c157851bc6af91f8d9cf
  [candidate-v3.json]=d9d8377e19a37fd3a76dc3ebae0c882706d11d4bd0b4a3df41691e3cf4d39d5d)
MODELS=(
  "e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c selfplay/models/ooc_strategic_tok_final.native"
  "fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70 models/v_win_trees.txt"
  "3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3 models/v_rich_trees.txt"
  "a251b33d4f71c1aa3fca529801da23ea9740dd0ded58abfb1a90fe69da7c9acf models/candidates/v_win_x2b_trees.txt"
  "8e2f9dc78cb31de382c876888a33007efc8a0526103b2c274d3980fc0915e051 models/candidates/screen_leaf_gbm_v1.trees")

die() { echo "STOP: $*" >&2; exit 1; }
sha() { sha256sum "$1" | cut -d' ' -f1; }
cmd=${1:-}; shift || true
WT=$(git rev-parse --show-toplevel 2>/dev/null) || die "run from the repo checkout"
cd "$WT"
case "$WT" in /mnt/project-files*) die "the checkout must not be on /mnt/project-files";; esac
worker() { [[ "${1:-}" =~ ^[0-9]+$ ]] && [ "$1" -ge 1 ] && [ "$1" -le $NW ] || die "W must be 1..$NW"
  W=$1; WW=$(printf %02d "$W"); LAB=$HOME/qscreen-w$WW; OUTS=$SHARE/w$WW; }

arm_env() {   # arm_env ARM BASE -> KEY=VALUE lines for env -i: the #418 live A/B cand arm, plus cpuct/root selection
  local arm=$1 base=$2 sel cp
  case ${arm:0:1} in v) sel=visits ;; q) sel=q ;; *) return 1 ;; esac
  case ${arm:1} in 05) cp=0.5 ;; 10) cp=1.0 ;; 15) cp=1.5 ;; 30) cp=3.0 ;; *) return 1 ;; esac
  printf '%s\n' "PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" STS_EXECUTABLE_GIT_SHA=$GITSHA \
    STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
    OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
    STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
    STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
    STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
    STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3 \
    STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 \
    "STS_OOC_DECISION_TRACE=$base.trace.jsonl" \
    STS_OOC_MCTS=1 STS_OOC_MCTS_SIMS=2048 STS_OOC_MCTS_CPUCT=$cp STS_OOC_MCTS_EARLY_STOP=1 \
    STS_OOC_MCTS_LEAF_COMBATS=0 STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_MAX_DEPTH=32 \
    STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_ROOT_SELECTION=$sel STS_OOC_MCTS_TEMPERATURE=1 \
    STS_OOC_MCTS_WIDEN_ALPHA=0.5 STS_OOC_MCTS_WIDEN_K=2 "STS_OOC_MCTS_TRACE=$base.mcts.csv" \
    "STS_OOC_MCTS_COMBAT_MODEL=$LAB/cand/FAST-final.native" \
    "STS_OOC_MCTS_BREW_FALLBACK_MODEL=$LAB/cand/STD1-escape.native" STS_OOC_MCTS_ACTIVE_LIZARD=1 \
    "STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$LAB/cand/candidate-v3.json" \
    STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=d9d8377e19a37fd3a76dc3ebae0c882706d11d4bd0b4a3df41691e3cf4d39d5d
}

units_all() {   # every unit "ARM LO N", in frozen order; unit i (0-based) belongs to worker i % NW + 1
  local b a; for ((b = 0; b < NSEED / PER; b++)); do for a in "${ARMS[@]}"; do echo "$a $((SEED_LO + PER * b)) $PER"; done; done; }

run_unit() {   # run_unit OUTDIR ARM LO N: one guarded bestbench unit, written locally, copied to the share when done
  local out=$1 arm=$2 lo=$3 n=$4 tag=$2-$3 base=$LAB/work/$2-$3
  [ -f "$out/$tag.done" ] && return 0
  rm -f "$base".*
  mapfile -t E < <(arm_env "$arm" "$base") || { echo "tag=$tag rc=2 bad arm" > "$out/$tag.done"; return 0; }
  local start rc; start=$(date -u +%FT%TZ)
  set +e
  env -i "${E[@]}" timeout 90m bash tools/seed_guard.sh "$LAB/bin/one_combat" \
    bestbench 10000 "$n" 0 "$lo" "$base.csv" > "$base.log" 2>&1
  rc=$?; set -e
  cp "$base".* "$out/"
  echo "tag=$tag rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$out/$tag.done"
}
export -f run_unit arm_env die; export LAB GITSHA

frozen_lines() {
  echo "$(sha "$LAB/bin/one_combat")  one_combat"
  for f in "${!CAND[@]}"; do echo "$(sha "$LAB/cand/$f")  $f"; done | sort
  for m in "${MODELS[@]}"; do echo "${m%% *}  ${m#* }"; done
  echo "$(sha "$SHARE/PREREG.md")  PREREG.md"; echo "$(sha "$SHARE/analyze.py")  analyze.py"
  echo "$(sha "$0")  worker.sh"; echo "build $GITSHA  workers=$NW  J=$J"
}

setup() {
  worker "${1:-}"
  [ "$(nproc)" -ge $J ] || die "need >= $J CPUs"
  [ "$(git rev-parse HEAD)" = "$GITSHA" ] || die "checkout $GITSHA first (git checkout --detach $GITSHA)"
  [ -z "$(git status --porcelain --untracked-files=no)" ] || die "checkout is dirty"
  for m in "${MODELS[@]}"; do [ "$(sha "${m#* }")" = "${m%% *}" ] || die "model ${m#* } differs"; done
  mkdir -p "$LAB"/{bin,cand,work} "$OUTS"
  if [ ! -x "$LAB/bin/one_combat" ] || [ "$(sha "$LAB/bin/one_combat")" != "$BIN_SHA" ]; then
    cmake --preset linux-gcc-release > "$LAB/build.log" 2>&1 || die "configure failed, see $LAB/build.log"
    cmake --build build/linux-gcc-release --target one_combat -j $J >> "$LAB/build.log" 2>&1 || die "build failed, see $LAB/build.log"
    cp build/linux-gcc-release/one_combat "$LAB/bin/one_combat"; chmod +x "$LAB/bin/one_combat"
  fi
  [ "$(sha "$LAB/bin/one_combat")" = "$BIN_SHA" ] || die "binary sha256 $(sha "$LAB/bin/one_combat") != $BIN_SHA ($(g++ --version | head -1))"
  for f in "${!CAND[@]}"; do cp /mnt/project-files/ctm-pathb/live-ab-cloud/candidate/$f "$LAB/cand/$f"
    [ "$(sha "$LAB/cand/$f")" = "${CAND[$f]}" ] || die "candidate $f differs"; done
  units_all | awk -v w=$W -v nw=$NW '(NR - 1) % nw == w - 1' > "$LAB/units.txt"
  [ "$(wc -l < "$LAB/units.txt")" = $(( NSEED / PER * ${#ARMS[@]} / NW )) ] || die "unexpected unit count"
  frozen_lines > "$LAB/FROZEN.lines"
  if [ -f "$OUTS/FROZEN.txt" ]; then
    diff <(tail -n +2 "$OUTS/FROZEN.txt") "$LAB/FROZEN.lines" || die "frozen inputs changed since first setup"
  else { echo "worker $W setup $(date -u +%FT%TZ) $(g++ --version | head -1)"; cat "$LAB/FROZEN.lines"; } > "$OUTS/FROZEN.txt"
    cp "$LAB/units.txt" "$OUTS/units.txt"; fi
  cat "$OUTS/FROZEN.txt"; echo "setup ok: worker $W, $(wc -l < "$LAB/units.txt") units"
}

smoke() {
  worker "${1:-}"; [ "$W" = 1 ] || die "only worker 1 runs the smoke"
  [ -f "$LAB/FROZEN.lines" ] || die "run setup first"
  [ -f "$SHARE/SMOKE_PASS" ] && { echo "smoke already passed"; return 0; }
  [ -f "$SHARE/SMOKE_FAIL" ] && die "smoke already failed: $SHARE/SMOKE_FAIL"
  local out=$SHARE/smoke fail=() a; mkdir -p "$out"
  printf '%s\n' "${ARMS[@]}" | xargs -P $J -I{} bash -c 'run_unit "$1" {} '$SMOKE_SEED' 1' _ "$out"
  for a in "${ARMS[@]}"; do
    grep -q " rc=0 " "$out/$a-$SMOKE_SEED.done" || fail+=("$a rc")
    [ "$(tail -n +2 "$out/$a-$SMOKE_SEED.csv" | wc -l)" = 1 ] || fail+=("$a csv rows")
    grep -q "cpuct=$(case ${a:1} in 05) echo 0.5;; 10) echo 1;; 15) echo 1.5;; 30) echo 3;; esac) " "$out/$a-$SMOKE_SEED.log" || fail+=("$a cpuct banner")
    grep -q "root_selection=$([ ${a:0:1} = q ] && echo q || echo visits) " "$out/$a-$SMOKE_SEED.log" || fail+=("$a selection banner")
    grep -q "\[ctm-research-candidate\] candidate_id=pathb-r2" "$out/$a-$SMOKE_SEED.log" || fail+=("$a candidate line")
  done
  python3 -I "$SHARE/analyze.py" check "$out" --seed-lo $SMOKE_SEED --seed-count 1 --per 1 > "$out/check.txt" 2>&1 || fail+=("integrity")
  if [ ${#fail[@]} -eq 0 ]; then { date -u +%FT%TZ; grep -h "^BEST " "$out"/*.log | sort | uniq -c | head -3; } > "$SHARE/SMOKE_PASS"; cat "$SHARE/SMOKE_PASS"
  else printf '%s\n' "${fail[@]}" > "$SHARE/SMOKE_FAIL"; die "smoke failed: ${fail[*]}"; fi
}

run() {
  worker "${1:-}"; [ -f "$LAB/FROZEN.lines" ] || die "run setup first"
  local waited=0
  until [ -f "$SHARE/SMOKE_PASS" ]; do
    [ -f "$SHARE/SMOKE_FAIL" ] && die "smoke failed: $(cat "$SHARE/SMOKE_FAIL")"
    [ $waited -ge 3600 ] && die "no SMOKE_PASS after 60 min"
    sleep 30; waited=$((waited + 30))
  done
  echo "launch $(date -u +%FT%TZ)" >> "$OUTS/launches.txt"
  xargs -P $J -L 1 bash -c 'run_unit "$0" "$1" "$2" "$3"' "$OUTS" < "$LAB/units.txt"
  local n; n=$(ls "$OUTS"/*.done | wc -l)
  [ "$n" = "$(wc -l < "$LAB/units.txt")" ] || die "only $n units done; rerun the same command to resume"
  { echo "worker=$W finished=$(date -u +%FT%TZ) units=$n"
    cat "$OUTS"/*.done | grep -o " rc=[0-9-]*" | sort | uniq -c
    grep -h "bestbench-seed-failure" "$OUTS"/*.log || echo "no seed failures"; } > "$OUTS/DONE.txt"
  cat "$OUTS/DONE.txt"
}

status() { worker "${1:-}"
  echo "done $(ls "$OUTS"/*.done 2>/dev/null | wc -l)/$(wc -l < "$LAB/units.txt"); running $(pgrep -fc 'bestbench 10000' || true)"
  grep -h "bestbench-seed-failure" "$OUTS"/*.log 2>/dev/null || true; }

case "$cmd" in
  setup) setup "$@" ;; smoke) smoke "$@" ;; run) run "$@" ;; status) status "$@" ;;
  *) die "usage: worker.sh setup W | smoke 1 | run W | status W" ;;
esac
