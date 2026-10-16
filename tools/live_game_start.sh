#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage: tools/live_game_start.sh [options] [-- driver-options]

Ensure the stable runtime, then start or verify ModTheSpire + MCPTheSpire.

  --check                  validate without starting the game
  --probe                  run the direct driver's read-only MCP dry-run
  --run                    start the driver immediately when MCP is ready
  --super-fast             enable the installed SuperFastMode mod
  --refresh-runtime        build and atomically publish this worktree's advisor
  --arm-c PATH             install the frozen Arm C OOC prior (also refreshes runtime)
  --qualified-ctm          install the qualified A0 and calibrated A20 stacks
  --deploy-inspector       build and atomically deploy the Java inspector JAR
  --restart-game           safely restart the expected ModTheSpire process
  --foreground             keep a newly started ModTheSpire attached
  --allow-missing-advisor  explicit MCP-only escape hatch
  --allow-missing-ooc      allow Silver-only debugging without an OOC model
  --wait SECONDS           startup wait limit (default: 45)
  -h, --help               show this help

Environment: STS_LIVE_RUNTIME_DIR, STS_GAME_DIR, STS_MODTHESPIRE_JAR,
STS_MCP_THE_SPIRE_JAR, STS_MODEL_INSPECTOR_JAR, STS_MODEL_INSPECTOR_CONFIG,
STS_MODEL_INSPECTOR_ADVISOR, STS_CTM_MODEL, STS_LIVE_OOC_MODEL, STS_MCP_PORT,
STS_LIVE_OOC_WIN_MODEL, STS_LIVE_OOC_FLOOR_MODEL, STS_LIVE_GAME_LOG.
EOF
}

die() { echo "live-game-start: $*" >&2; exit 2; }
warn() { echo "live-game-start: warning: $*" >&2; }

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
runtime_tool=${STS_LIVE_RUNTIME_TOOL:-$repo_root/tools/live_game_runtime.py}
check_only=0 probe=0 foreground=0 allow_missing_advisor=0 refresh_runtime=0
deploy_inspector=0 restart_game=0 allow_missing_ooc=0 wait_seconds=45
run_driver=0 super_fast=0
arm_c_source=
qualified_ctm=0
driver_args=()
while (($#)); do
  case "$1" in
    --check) check_only=1 ;;
    --probe) probe=1 ;;
    --run) run_driver=1 ;;
    --super-fast) super_fast=1 ;;
    --) shift; driver_args=("$@"); break ;;
    --foreground) foreground=1 ;;
    --allow-missing-advisor) allow_missing_advisor=1 ;;
    --allow-missing-ooc) allow_missing_ooc=1 ;;
    --refresh-runtime) refresh_runtime=1 ;;
    --arm-c)
      (($# >= 2)) || die "--arm-c requires a weights path"
      [[ -n "$2" ]] || die "--arm-c requires a nonempty weights path"
      arm_c_source=$2; refresh_runtime=1; shift
      ;;
    --qualified-ctm) qualified_ctm=1; refresh_runtime=1 ;;
    --deploy-inspector) deploy_inspector=1 ;;
    --restart-game) restart_game=1 ;;
    --wait)
      (($# >= 2)) || die "--wait requires seconds"
      wait_seconds=$2; shift
      [[ "$wait_seconds" =~ ^[0-9]+$ ]] || die "--wait must be a non-negative integer"
      ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (use --help)" ;;
  esac
  shift
done
((run_driver || ${#driver_args[@]} == 0)) || die "driver options require --run"
((!run_driver || (!check_only && !foreground))) || die "--run cannot be combined with --check or --foreground"

home_dir=${HOME:?HOME is not set}
game_dir=${STS_GAME_DIR:-}
if [[ -z "$game_dir" ]]; then
  for candidate in \
    "$home_dir/.local/share/Steam/steamapps/common/SlayTheSpire" \
    "$home_dir/.steam/steam/steamapps/common/SlayTheSpire" \
    "$home_dir/.var/app/com.valvesoftware.Steam/data/Steam/steamapps/common/SlayTheSpire"; do
    [[ -d "$candidate" ]] && { game_dir=$candidate; break; }
  done
fi
[[ -d "$game_dir" ]] || die "SlayTheSpire directory not found; set STS_GAME_DIR"

java_bin=${STS_JAVA_BIN:-$(command -v java || true)}
[[ -z "$java_bin" && -x "$game_dir/jre/bin/java" ]] && java_bin="$game_dir/jre/bin/java"
[[ -n "$java_bin" && -x "$java_bin" ]] || die "Java runtime not found; set STS_JAVA_BIN"

modthespire_jar=${STS_MODTHESPIRE_JAR:-}
if [[ -z "$modthespire_jar" ]]; then
  for candidate in \
    "$home_dir/.local/share/Steam/steamapps/workshop/content/646570/1605060445/ModTheSpire.jar" \
    "$home_dir/.steam/steam/steamapps/workshop/content/646570/1605060445/ModTheSpire.jar"; do
    [[ -f "$candidate" ]] && { modthespire_jar=$candidate; break; }
  done
fi
[[ -f "$modthespire_jar" ]] || die "ModTheSpire.jar not found; set STS_MODTHESPIRE_JAR"
mcp_jar=${STS_MCP_THE_SPIRE_JAR:-$game_dir/mods/MCPTheSpire.jar}
inspector_jar=${STS_MODEL_INSPECTOR_JAR:-$game_dir/mods/sts-model-inspector.jar}
[[ -f "$mcp_jar" ]] || die "MCPTheSpire.jar not found: $mcp_jar"
enabled_mods=basemod,MCPTheSpire,stsmodelinspector
if ((super_fast)); then
  [[ -f "$game_dir/mods/SuperFastMode.jar" ]] || die "SuperFastMode.jar not installed in $game_dir/mods"
  enabled_mods+=,superfastmode
fi

runtime_command=ensure
((refresh_runtime)) && runtime_command=install
runtime_available=1
runtime_args=()
[[ -z "$arm_c_source" ]] || runtime_args+=(--arm-c-source "$arm_c_source")
((!qualified_ctm)) || runtime_args+=(--qualified-ctm)
if ! python3 "$runtime_tool" "$runtime_command" "${runtime_args[@]}"; then
  ((allow_missing_advisor)) || die "stable runtime $runtime_command failed"
  runtime_available=0
  warn "stable runtime unavailable; continuing in explicit MCP-only mode"
fi
if ((deploy_inspector)); then
  python3 "$runtime_tool" deploy-inspector --game-dir "$game_dir" --modthespire-jar "$modthespire_jar"
fi
[[ -f "$inspector_jar" ]] || die "sts-model-inspector.jar not found: $inspector_jar"

runtime_root=${STS_LIVE_RUNTIME_DIR:-${XDG_DATA_HOME:-$home_dir/.local/share}/sts-ai/live-runtime}
if ((runtime_available)); then
  export STS_MODEL_INSPECTOR_ADVISOR=${STS_MODEL_INSPECTOR_ADVISOR:-$runtime_root/current/one_combat_advisor}
  if [[ ! ${STS_LIVE_OOC_ARM_C+x} ]] && python3 - "$runtime_root/current/manifest.json" <<'PY_ARM_C'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    selected = "armCModelSha256" in json.load(stream)
raise SystemExit(0 if selected else 1)
PY_ARM_C
  then
    export STS_LIVE_OOC_ARM_C="$runtime_root/current/models/arm_c_student.bin"
  fi
  # ensure/install validated this manifest; use its primary so legacy releases
  # remain usable and explicit model overrides retain precedence.
  use_manifest_ctm=0
  if [[ ! ${STS_CTM_MODEL+x} ]]; then
    use_manifest_ctm=1
    ctm_primary=$(python3 - "$runtime_root/current/manifest.json" <<'PY_CTM'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    manifest = json.load(stream)
print(manifest.get("ctmPrimary", "combat_transition_near_full_except_smoke_v2.native"))
PY_CTM
    )
    export STS_CTM_MODEL="$runtime_root/current/models/$ctm_primary"
  fi
  qualified_names=$(python3 - "$runtime_root/current/manifest.json" <<'PY_CTM_STACK'
import json, sys
with open(sys.argv[1], encoding="utf-8") as stream:
    m = json.load(stream)
if m.get("ctmStackVersion") == 2:
    print(m["ctmFallback"], m["ctmA20Primary"], m["ctmA20Fallback"])
PY_CTM_STACK
  )
  if [[ -n "$qualified_names" && "$use_manifest_ctm" == 1 ]]; then
    read -r ctm_fallback ctm_a20 ctm_a20_fallback <<< "$qualified_names"
    [[ ${STS_CTM_BREW_FALLBACK_MODEL+x} ]] || export STS_CTM_BREW_FALLBACK_MODEL="$runtime_root/current/models/$ctm_fallback"
    [[ ${STS_LIVE_CTM_A20_MODEL+x} ]] || export STS_LIVE_CTM_A20_MODEL="$runtime_root/current/models/$ctm_a20"
    [[ ${STS_LIVE_CTM_A20_FALLBACK_MODEL+x} ]] || export STS_LIVE_CTM_A20_FALLBACK_MODEL="$runtime_root/current/models/$ctm_a20_fallback"
  fi
  if [[ -f "$runtime_root/current/models/v_win_trees.txt" ]]; then
    export STS_LIVE_OOC_WIN_MODEL=${STS_LIVE_OOC_WIN_MODEL:-$runtime_root/current/models/v_win_trees.txt}
  fi
  if [[ -f "$runtime_root/current/models/v_rich_trees.txt" ]]; then
    export STS_LIVE_OOC_FLOOR_MODEL=${STS_LIVE_OOC_FLOOR_MODEL:-$runtime_root/current/models/v_rich_trees.txt}
  fi
  if [[ -f "$runtime_root/current/models/ooc_strategic_tok_final.native" ]]; then
    export STS_LIVE_OOC_MODEL=${STS_LIVE_OOC_MODEL:-$runtime_root/current/models/ooc_strategic_tok_final.native}
  fi
  [[ -x "$STS_MODEL_INSPECTOR_ADVISOR" ]] || die "stable advisor missing or not executable: $STS_MODEL_INSPECTOR_ADVISOR"
  [[ -f "$STS_CTM_MODEL" ]] || warn "CTM model unavailable: $STS_CTM_MODEL"
  if [[ -z "${STS_LIVE_OOC_MODEL:-}" || ! -f "$STS_LIVE_OOC_MODEL" ]]; then
    ((allow_missing_ooc)) || die "OOC model unavailable: ${STS_LIVE_OOC_MODEL:-<unset>}; use --allow-missing-ooc for Silver-only debugging"
    warn "OOC model unavailable; live OOC policy will report MODEL_UNAVAILABLE"
  fi
  if [[ -z "${STS_LIVE_OOC_WIN_MODEL:-}" || ! -f "$STS_LIVE_OOC_WIN_MODEL" ]]; then
    warn "OOC win model unavailable; live OOC MCTS will report OOC_WIN_MODEL_UNAVAILABLE"
  fi
  if [[ -z "${STS_LIVE_OOC_FLOOR_MODEL:-}" || ! -f "$STS_LIVE_OOC_FLOOR_MODEL" ]]; then
    warn "OOC floor model unavailable; live OOC MCTS will report OOC_FLOOR_MODEL_UNAVAILABLE"
  fi
else
  warn "advisor validation and active-runtime recording are disabled for MCP-only startup"
fi

mcp_port=${STS_MCP_PORT:-8080}
[[ "$mcp_port" =~ ^[0-9]+$ ]] || die "STS_MCP_PORT must be numeric"
mcp_url=${STS_MCP_URL:-http://127.0.0.1:${mcp_port}/mcp}
log_path=${STS_LIVE_GAME_LOG:-$home_dir/.cache/sts-live-driver/modthespire.log}
port_is_open() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltnH | awk -v port=":$mcp_port" '$4 ~ port "$" || $4 ~ "\\]:" port "$" { found=1 } END { exit !found }'
  else
    timeout 1 bash -c ": </dev/tcp/127.0.0.1/$mcp_port" >/dev/null 2>&1
  fi
}
find_modthespire_pids() {
  python3 - "$modthespire_jar" <<'PY'
import os, sys
jar = sys.argv[1]
for entry in os.scandir("/proc"):
    if not entry.name.isdigit():
        continue
    try:
        argv = open(entry.path + "/cmdline", "rb").read().split(b"\0")
        argv = [value.decode(errors="surrogateescape") for value in argv if value]
    except (OSError, PermissionError):
        continue
    if any(argv[index] == "-jar" and argv[index + 1] == jar for index in range(len(argv) - 1)):
        print(entry.name)
PY
}
refresh_game_pids() { mapfile -t game_pids < <(find_modthespire_pids); }
refresh_mcp_owner_pids() {
  mcp_owner_pids=()
  command -v ss >/dev/null 2>&1 || die "ss is required to verify MCP listener process ownership"
  local listeners pid
  listeners=$(ss -ltnpH | awk -v port=":$mcp_port" '$4 ~ port "$" || $4 ~ "\\]:" port "$"')
  for pid in "${game_pids[@]}"; do
    [[ "$listeners" == *"pid=$pid,"* ]] && mcp_owner_pids+=("$pid")
  done
}

show_runtime_identity() {
  if ((!runtime_available)); then
    echo "running runtime: unavailable (MCP-only mode)"
    echo "current installed runtime: unavailable"
    return
  fi
  local status
  status=$(python3 "$runtime_tool" status --json 2>/dev/null || true)
  python3 - "$status" <<'PY'
import json, sys
try: status=json.loads(sys.argv[1])
except Exception: print("runtime identity: unavailable"); raise SystemExit
current=status.get("manifest", {}).get("runtimeId", "unavailable")
active=status.get("activeRuntime", {}).get("runtimeId", "unknown") if status.get("activeProcessMatches") else "unknown"
print("running runtime: " + active)
print("current installed runtime: " + current)
if active == "unknown": print("warning: running runtime identity is unknown; restart before claiming the current runtime is loaded")
elif active != current: print("warning: runtime change requires game restart")
PY
}
print_ready() {
  echo "MCP endpoint: $mcp_url"
  echo "Inspector snapshot: $home_dir/.cache/sts-model-inspector/latest.json"
  if ((runtime_available)); then
    echo "Stable runtime: $runtime_root/current"
    echo "OOC model: ${STS_LIVE_OOC_MODEL:-<unavailable>}"
  else
    echo "Stable runtime: unavailable (MCP-only mode)"
  fi
  echo "Driver: (cd $repo_root && uv run --extra live-driver python tools/live_game_driver.py --strict-silver --max-steps 10)"
  echo "Log: $log_path"
}
run_probe() {
  local probe_log="$home_dir/.cache/sts-live-driver/start-probe.log"
  mkdir -p "$(dirname "$probe_log")"
  for ((attempt=0; attempt<wait_seconds; attempt++)); do
    if (cd "$repo_root" && uv run --extra live-driver python tools/live_game_driver.py --dry-run --max-steps 1) >"$probe_log" 2>&1; then
      cat "$probe_log"; return 0
    fi
    sleep 1
  done
  cat "$probe_log" >&2; return 1
}
run_requested_driver() {
  if ((run_driver)); then
    echo "Starting autonomous driver immediately."
    cd "$repo_root"
    exec bash tools/seed_guard.sh uv run --extra live-driver python tools/live_game_driver.py \
      --mcp-url "$mcp_url" "${driver_args[@]}"
  fi
  if ((probe)); then run_probe; fi
}

if port_is_open; then
  refresh_game_pids
  refresh_mcp_owner_pids
  ((${#mcp_owner_pids[@]})) || die "port $mcp_port is not owned by the expected ModTheSpire process: $mcp_url"
  show_runtime_identity
  if ((refresh_runtime || deploy_inspector)) && ((!restart_game)); then
    die "runtime change requires game restart; rerun with --restart-game when safe"
  fi
  if ((!restart_game)); then
    if ((super_fast)); then
      python3 - "${mcp_owner_pids[0]}" <<'PY' || die "running game lacks SuperFastMode; use --restart-game"
import sys
args = open('/proc/' + sys.argv[1] + '/cmdline', 'rb').read().decode().split('\0')
mods = args[args.index('--mods') + 1].split(',') if '--mods' in args else []
raise SystemExit(0 if 'superfastmode' in mods else 1)
PY
    fi
    echo "MCPTheSpire is already running; reusing the existing modded game."
    print_ready
    run_requested_driver
    exit 0
  fi
  echo "Stopping MCP-owning ModTheSpire process for explicit restart: ${mcp_owner_pids[*]}"
  kill -TERM "${mcp_owner_pids[@]}"
  for ((attempt=0; attempt<100; attempt++)); do
    port_is_open || break
    sleep 0.1
  done
  port_is_open && die "ModTheSpire did not stop cleanly; save state was not modified"
fi

if ((check_only)); then
  echo "MCPTheSpire is not running."
  if ((runtime_available)); then
    python3 "$runtime_tool" status
  fi
  print_ready
  exit 1
fi

mkdir -p "$(dirname "$log_path")"
python3 "$runtime_tool" clear-active >/dev/null
if ((foreground)); then
  echo "Starting ModTheSpire in the foreground..."; print_ready
  cd "$game_dir"
  exec "$java_bin" -jar "$modthespire_jar" --skip-launcher --mods "$enabled_mods"
fi

echo "Starting ModTheSpire in the background; log=$log_path"
(
  cd "$game_dir"
  if command -v setsid >/dev/null 2>&1; then
    exec nohup setsid -f "$java_bin" -jar "$modthespire_jar" --skip-launcher --mods "$enabled_mods"
  fi
  exec nohup "$java_bin" -jar "$modthespire_jar" --skip-launcher --mods "$enabled_mods"
) >>"$log_path" 2>&1 </dev/null &
game_pid=$!
echo "ModTheSpire PID: $game_pid"
for ((elapsed=0; elapsed<wait_seconds*10; elapsed++)); do
  if port_is_open; then
    refresh_game_pids
    refresh_mcp_owner_pids
    ((${#mcp_owner_pids[@]})) || die "port $mcp_port opened without the expected ModTheSpire listener"
    if ((runtime_available)); then
      python3 "$runtime_tool" record-active --inspector-jar "$inspector_jar" --process-pid "${mcp_owner_pids[0]}"
    fi
    echo "MCPTheSpire is ready."; print_ready
    run_requested_driver
    exit 0
  fi
  refresh_game_pids
  if ((${#game_pids[@]} == 0)) && ! kill -0 "$game_pid" 2>/dev/null; then
    echo "ModTheSpire exited before MCP became ready. Recent log:" >&2
    tail -40 "$log_path" >&2 || true
    exit 1
  fi
  sleep 0.1
done
echo "MCPTheSpire did not become ready within ${wait_seconds}s. Recent log:" >&2
tail -40 "$log_path" >&2 || true
exit 1
