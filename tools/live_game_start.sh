#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage: tools/live_game_start.sh [options]

Start or verify the local ModTheSpire + MCPTheSpire + model-inspector setup.

Options:
  --check                  validate installed artifacts and current state only
  --probe                  run the driver's read-only MCP dry-run after startup
  --foreground             keep ModTheSpire attached to this terminal
  --allow-missing-advisor  start MCP even when the inspector advisor is absent
  --wait SECONDS           startup wait limit (default: 45)
  -h, --help               show this help

Environment overrides:
  STS_GAME_DIR, STS_MODTHESPIRE_JAR, STS_MCP_THE_SPIRE_JAR,
  STS_MODEL_INSPECTOR_JAR, STS_MODEL_INSPECTOR_CONFIG,
  STS_MODEL_INSPECTOR_ADVISOR, STS_CTM_MODEL, STS_MCP_PORT,
  STS_LIVE_GAME_LOG
EOF
}

die() {
  echo "live-game-start: $*" >&2
  exit 2
}

warn() {
  echo "live-game-start: warning: $*" >&2
}

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
check_only=0
probe=0
foreground=0
allow_missing_advisor=0
wait_seconds=45

while (($#)); do
  case "$1" in
    --check) check_only=1 ;;
    --probe) probe=1 ;;
    --foreground) foreground=1 ;;
    --allow-missing-advisor) allow_missing_advisor=1 ;;
    --wait)
      (($# >= 2)) || die "--wait requires a number of seconds"
      wait_seconds=$2
      shift
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
    if [[ -d "$candidate" ]]; then
      game_dir=$candidate
      break
    fi
  done
fi
[[ -d "$game_dir" ]] || die "SlayTheSpire directory not found; set STS_GAME_DIR"

java_bin=${STS_JAVA_BIN:-$(command -v java || true)}
if [[ -z "$java_bin" && -x "$game_dir/jre/bin/java" ]]; then
  java_bin="$game_dir/jre/bin/java"
fi
[[ -n "$java_bin" && -x "$java_bin" ]] || die "Java runtime not found; set STS_JAVA_BIN"

modthespire_jar=${STS_MODTHESPIRE_JAR:-}
if [[ -z "$modthespire_jar" ]]; then
  for candidate in \
    "$home_dir/.local/share/Steam/steamapps/workshop/content/646570/1605060445/ModTheSpire.jar" \
    "$home_dir/.steam/steam/steamapps/workshop/content/646570/1605060445/ModTheSpire.jar"; do
    if [[ -f "$candidate" ]]; then
      modthespire_jar=$candidate
      break
    fi
  done
fi
[[ -f "$modthespire_jar" ]] || die "ModTheSpire.jar not found; set STS_MODTHESPIRE_JAR"

mcp_jar=${STS_MCP_THE_SPIRE_JAR:-$game_dir/mods/MCPTheSpire.jar}
inspector_jar=${STS_MODEL_INSPECTOR_JAR:-$game_dir/mods/sts-model-inspector.jar}
[[ -f "$mcp_jar" ]] || die "MCPTheSpire.jar not found: $mcp_jar"
[[ -f "$inspector_jar" ]] || die "sts-model-inspector.jar not found: $inspector_jar"

config_path=${STS_MODEL_INSPECTOR_CONFIG:-$home_dir/.sts-model-inspector.properties}
property() {
  local key=$1
  [[ -f "$config_path" ]] || return 0
  awk -F= -v wanted="$key" '
    /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
    { left=$1; gsub(/^[[:space:]]+|[[:space:]]+$/, "", left) }
    left == wanted { sub(/^[^=]*=/, ""); gsub(/^[[:space:]]+|[[:space:]]+$/, ""); print; exit }
  ' "$config_path"
}

advisor=${STS_MODEL_INSPECTOR_ADVISOR:-$(property advisor)}
ctm_model=${STS_CTM_MODEL:-$(property ctmModel)}
if [[ -z "$advisor" || ! -x "$advisor" ]]; then
  if ((allow_missing_advisor)); then
    warn "advisor is missing or not executable; MCP will start but inspector/Silver responses will not be ready"
  else
    die "advisor is missing or not executable: ${advisor:-<unset>}; fix $config_path or use --allow-missing-advisor"
  fi
fi
if [[ -n "$ctm_model" && ! -f "$ctm_model" ]]; then
  warn "configured CTM model does not exist: $ctm_model"
elif [[ -z "$ctm_model" ]]; then
  warn "no CTM model configured; Silver may still run, but CTM responses will be unavailable"
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

game_process_present() {
  ps -eo args= | awk -v jar="$modthespire_jar" 'index($0, jar) { found=1 } END { exit !found }'
}

print_ready() {
  echo "MCP endpoint: $mcp_url"
  echo "Inspector snapshot: $home_dir/.cache/sts-model-inspector/latest.json"
  echo "Advisor config: $config_path"
  echo "Driver: (cd $repo_root && uv run --extra live-driver python tools/live_game_driver.py --strict-silver --max-steps 10)"
  echo "Log: $log_path"
}

run_probe() {
  local probe_log="$home_dir/.cache/sts-live-driver/start-probe.log"
  mkdir -p "$(dirname "$probe_log")"
  for ((attempt=0; attempt<wait_seconds; attempt++)); do
    if (cd "$repo_root" && uv run --extra live-driver python tools/live_game_driver.py --dry-run --max-steps 1) >"$probe_log" 2>&1; then
      cat "$probe_log"
      return 0
    fi
    sleep 1
  done
  cat "$probe_log" >&2
  return 1
}

echo "game=$game_dir"
echo "ModTheSpire=$modthespire_jar"
echo "MCPTheSpire=$mcp_jar"
echo "inspector=$inspector_jar"

if port_is_open; then
  game_process_present || die "port $mcp_port is already occupied but ModTheSpire is not running: $mcp_url"
  echo "MCPTheSpire is already running; reusing the existing modded game."
  print_ready
  if ((probe)); then
    run_probe
  fi
  exit 0
fi

if ((check_only)); then
  echo "MCPTheSpire is not running."
  print_ready
  exit 1
fi

mkdir -p "$(dirname "$log_path")"
if ((foreground)); then
  echo "Starting ModTheSpire in the foreground..."
  print_ready
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
    echo "MCPTheSpire is ready."
    print_ready
    if ((probe)); then
      run_probe
    fi
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
