#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage: tools/live_game_start.sh [options]

Ensure the stable runtime, then start or verify ModTheSpire + MCPTheSpire.

  --check                  validate without starting the game
  --probe                  run the direct driver's read-only MCP dry-run
  --refresh-runtime        build and atomically publish this worktree's advisor
  --deploy-inspector       build and atomically deploy the Java inspector JAR
  --restart-game           safely restart the expected ModTheSpire process
  --foreground             keep a newly started ModTheSpire attached
  --allow-missing-advisor  explicit MCP-only escape hatch
  --wait SECONDS           startup wait limit (default: 45)
  -h, --help               show this help

Environment: STS_LIVE_RUNTIME_DIR, STS_GAME_DIR, STS_MODTHESPIRE_JAR,
STS_MCP_THE_SPIRE_JAR, STS_MODEL_INSPECTOR_JAR, STS_MODEL_INSPECTOR_CONFIG,
STS_MODEL_INSPECTOR_ADVISOR, STS_CTM_MODEL, STS_LIVE_OOC_MODEL, STS_MCP_PORT,
STS_LIVE_GAME_LOG.
EOF
}

die() { echo "live-game-start: $*" >&2; exit 2; }
warn() { echo "live-game-start: warning: $*" >&2; }

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
runtime_tool="$repo_root/tools/live_game_runtime.py"
check_only=0 probe=0 foreground=0 allow_missing_advisor=0 refresh_runtime=0
deploy_inspector=0 restart_game=0 wait_seconds=45
while (($#)); do
  case "$1" in
    --check) check_only=1 ;;
    --probe) probe=1 ;;
    --foreground) foreground=1 ;;
    --allow-missing-advisor) allow_missing_advisor=1 ;;
    --refresh-runtime) refresh_runtime=1 ;;
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

runtime_command=ensure
((refresh_runtime)) && runtime_command=install
if ! python3 "$runtime_tool" "$runtime_command"; then
  ((allow_missing_advisor)) || die "stable runtime $runtime_command failed"
  warn "stable runtime unavailable; continuing in explicit MCP-only mode"
fi
if ((deploy_inspector)); then
  python3 "$runtime_tool" deploy-inspector --game-dir "$game_dir" --modthespire-jar "$modthespire_jar"
fi
[[ -f "$inspector_jar" ]] || die "sts-model-inspector.jar not found: $inspector_jar"

runtime_root=${STS_LIVE_RUNTIME_DIR:-${XDG_DATA_HOME:-$home_dir/.local/share}/sts-ai/live-runtime}
export STS_MODEL_INSPECTOR_ADVISOR=${STS_MODEL_INSPECTOR_ADVISOR:-$runtime_root/current/one_combat_advisor}
export STS_CTM_MODEL=${STS_CTM_MODEL:-$runtime_root/current/models/combat_transition_near_full_except_smoke_v2.native}
if [[ -f "$runtime_root/current/models/ooc_strategic_tok_final.native" ]]; then
  export STS_LIVE_OOC_MODEL=${STS_LIVE_OOC_MODEL:-$runtime_root/current/models/ooc_strategic_tok_final.native}
fi
if [[ ! -x "$STS_MODEL_INSPECTOR_ADVISOR" ]]; then
  ((allow_missing_advisor)) || die "stable advisor missing or not executable: $STS_MODEL_INSPECTOR_ADVISOR"
  warn "advisor unavailable; inspector responses will not be ready"
fi
[[ -f "$STS_CTM_MODEL" ]] || warn "CTM model unavailable: $STS_CTM_MODEL"

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
game_process_present() { ps -eo args= | awk -v jar="$modthespire_jar" 'index($0, jar) { found=1 } END { exit !found }'; }

show_runtime_identity() {
  local status
  status=$(python3 "$runtime_tool" status --json 2>/dev/null || true)
  python3 - "$status" <<'PY'
import json, sys
try: status=json.loads(sys.argv[1])
except Exception: print("runtime identity: unavailable"); raise SystemExit
current=status.get("manifest", {}).get("runtimeId", "unavailable")
active=status.get("activeRuntime", {}).get("runtimeId", "unknown")
print("running runtime: " + active)
print("current installed runtime: " + current)
if active == "unknown": print("warning: running runtime identity is unknown; restart before claiming the current runtime is loaded")
elif active != current: print("warning: runtime change requires game restart")
PY
}
print_ready() {
  echo "MCP endpoint: $mcp_url"
  echo "Inspector snapshot: $home_dir/.cache/sts-model-inspector/latest.json"
  echo "Stable runtime: $runtime_root/current"
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

if port_is_open; then
  game_process_present || die "port $mcp_port is occupied but the expected ModTheSpire process is absent: $mcp_url"
  show_runtime_identity
  if ((refresh_runtime || deploy_inspector)) && ((!restart_game)); then
    die "runtime change requires game restart; rerun with --restart-game when safe"
  fi
  if ((!restart_game)); then
    echo "MCPTheSpire is already running; reusing the existing modded game."
    print_ready
    ((probe)) && run_probe
    exit 0
  fi
  mapfile -t game_pids < <(pgrep -f -- "$modthespire_jar" || true)
  ((${#game_pids[@]})) || die "expected ModTheSpire process disappeared before restart"
  echo "Stopping expected ModTheSpire process for explicit restart: ${game_pids[*]}"
  kill -TERM "${game_pids[@]}"
  for ((attempt=0; attempt<100; attempt++)); do
    port_is_open || break
    sleep 0.1
  done
  port_is_open && die "ModTheSpire did not stop cleanly; save state was not modified"
fi

if ((check_only)); then
  echo "MCPTheSpire is not running."
  python3 "$runtime_tool" status
  print_ready
  exit 1
fi

mkdir -p "$(dirname "$log_path")"
python3 "$runtime_tool" record-active --inspector-jar "$inspector_jar"
if ((foreground)); then
  echo "Starting ModTheSpire in the foreground..."; print_ready
  cd "$game_dir"
  exec "$java_bin" -jar "$modthespire_jar" --skip-launcher --mods basemod,MCPTheSpire,stsmodelinspector
fi

echo "Starting ModTheSpire in the background; log=$log_path"
(
  cd "$game_dir"
  if command -v setsid >/dev/null 2>&1; then
    exec nohup setsid -f "$java_bin" -jar "$modthespire_jar" --skip-launcher --mods basemod,MCPTheSpire,stsmodelinspector
  fi
  exec nohup "$java_bin" -jar "$modthespire_jar" --skip-launcher --mods basemod,MCPTheSpire,stsmodelinspector
) >>"$log_path" 2>&1 </dev/null &
game_pid=$!
echo "ModTheSpire PID: $game_pid"
for ((elapsed=0; elapsed<wait_seconds*10; elapsed++)); do
  if port_is_open; then
    game_process_present || die "port $mcp_port opened without the expected ModTheSpire process"
    echo "MCPTheSpire is ready."; print_ready
    ((probe)) && run_probe
    exit 0
  fi
  if ! game_process_present && ! kill -0 "$game_pid" 2>/dev/null; then
    echo "ModTheSpire exited before MCP became ready. Recent log:" >&2
    tail -40 "$log_path" >&2 || true
    exit 1
  fi
  sleep 0.1
done
echo "MCPTheSpire did not become ready within ${wait_seconds}s. Recent log:" >&2
tail -40 "$log_path" >&2 || true
exit 1
