#!/usr/bin/env bash
set -euo pipefail
# Seed-sweep argument positions verified against apps/one_combat.cpp mode dispatch
# (2026-08-31). silver_hard_combat_replay is bounded by JSONL root count and
# validates both the state-bound snapshot seed and any independent search seed.
# Other unlisted commands pass through without seed checking.

MAX_AUTOMATED_SEEDS=128

declare -A ONE_COMBAT_SEED_INDEX=(
  ["bestbench"]=3
  ["datagen3"]=2
  ["e2cgen"]=2
  ["wholecombatgen"]=2     ["combattransitiongen"]=2 ["combatevalgen"]=2 ["ooccfaudit"]=2
  ["oocnextgen"]=2
  ["pathcfgen"]=2
  ["strategicgen"]=2        ["strategicgen2"]=2
  ["strategicmarggen"]=2
  ["oocfactoreval"]=2      ["oocmargtradeoffeval"]=2 ["oock3tradeoffeval"]=2
  ["oocsemanticfullruneval"]=2 ["oockbudgeteval"]=2
  ["oocsemanticcapture"]=2 ["oocsemanticeval"]=2
)

declare -A PYTHON_SEED_INDEX=(
  ["check_replay.py"]=3
)

exe_name() {
  local name="$1"
  name="${name##*/}"
  echo "$name"
}

check_oversized() {
  local argv=("$@")
  local i=0
  while [ $i -lt ${#argv[@]} ]; do
    local exe
    exe="$(exe_name "${argv[$i]}")"
    if [ "$exe" = "one_combat" ]; then
      local mode="${argv[$((i + 1))]:-}"
      local idx="${ONE_COMBAT_SEED_INDEX[$mode]:-}"
      if [ -n "$idx" ]; then
        local seeds="${argv[$((i + idx))]:-}"
        # Semantic label pilot is deliberately bounded independently of the
        # general sweep ceiling, including when a research host is selected.
        if [ "$mode" = "oocsemanticcapture" ] || [ "$mode" = "oocsemanticeval" ]; then
          if ! [[ "$seeds" =~ ^[0-9]+$ ]] || [ "$seeds" -lt 1 ] || [ "$seeds" -gt 16 ]; then
            echo "SEED_GUARD: $mode requires 1..16 source seeds/decisions" >&2
            exit 1
          fi
        fi
        if [ "$MAX_AUTOMATED_SEEDS" -gt 0 ] && [[ "$seeds" =~ ^[0-9]+$ ]] && [ "$seeds" -gt "$MAX_AUTOMATED_SEEDS" ]; then
          echo "SEED_GUARD: $exe $mode requests $seeds seeds; automated maximum is $MAX_AUTOMATED_SEEDS" >&2
          exit 1
        fi
      fi
    elif [ "$exe" = "silver_hard_combat_replay" ]; then
      local snapshots="${argv[$((i + 1))]:-}"
      check_silver_replay_snapshots "$snapshots" "$MAX_AUTOMATED_SEEDS"
    elif [ "$exe" = "python" ] || [ "$exe" = "python3" ]; then
      local script="${argv[$((i + 1))]:-}"
      local script_name
      script_name="$(exe_name "$script")"
      local idx="${PYTHON_SEED_INDEX[$script_name]:-}"
      if [ -n "$idx" ]; then
        local seeds="${argv[$((i + idx))]:-}"
        if [ "$MAX_AUTOMATED_SEEDS" -gt 0 ] && [[ "$seeds" =~ ^[0-9]+$ ]] && [ "$seeds" -gt "$MAX_AUTOMATED_SEEDS" ]; then
          echo "SEED_GUARD: $script_name requests $seeds seeds; automated maximum is $MAX_AUTOMATED_SEEDS" >&2
          exit 1
        fi
      fi
    fi
    i=$((i + 1))
  done
}

check_silver_replay_snapshots() {
  local snapshots="$1"
  local maximum="$2"
  python3 - "$snapshots" "$maximum" <<'PY'
import json
import sys

path, maximum_text = sys.argv[1:]
maximum = int(maximum_text)
uint64_max = (1 << 64) - 1
count = 0

def fail(message):
    print(f"SEED_GUARD: silver_hard_combat_replay {message}", file=sys.stderr)
    raise SystemExit(1)

if not path:
    fail("requires a snapshot JSONL path")
try:
    stream = open(path, encoding="utf-8")
except OSError as error:
    fail(f"cannot read {path}: {error}")

with stream:
    for line_number, line in enumerate(stream, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            fail(f"invalid JSON on line {line_number}: {error}")
        if not isinstance(row, dict):
            fail(f"line {line_number} must contain a JSON object")
        for key in ("benchmark_seed", "isolated_search_seed"):
            if key not in row:
                if key == "isolated_search_seed":
                    continue
                fail(f"line {line_number} is missing {key}")
            value = row[key]
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= uint64_max:
                fail(f"line {line_number} {key} must be an unsigned 64-bit integer")
        count += 1
        if maximum > 0 and count > maximum:
            fail(f"requests {count} snapshot roots; automated maximum is {maximum}")

if count == 0:
    fail("requires at least one snapshot root")
PY
}

if [ $# -eq 0 ]; then
  echo "Usage: tools/seed_guard.sh [--gcp-research] [guard-only] <command...>" >&2
  echo "  With 'guard-only': validates seed count and exits 0/1 without running the command." >&2
  echo "  Without 'guard-only': validates seed count, then execs the command if valid." >&2
  echo "  With '--gcp-research': use only on the designated GCP benchmark host;" >&2
  echo "    seed parsing remains enabled but the local 128-seed ceiling is disabled." >&2
  exit 1
fi

gcp_research=false
if [ "$1" = "--gcp-research" ]; then
  gcp_research=true
  shift
fi

guard_only=false
if [ $# -gt 0 ] && [ "$1" = "guard-only" ]; then
  guard_only=true
  shift
fi

if [ $# -eq 0 ]; then
  echo "SEED_GUARD: missing command after guard mode options" >&2
  exit 1
fi

if $gcp_research; then
  # The unrestricted path is mechanically tied to the designated remote
  # working copy. The launcher supplies the context marker; local invocations
  # cannot opt into this mode merely by adding a flag.
  research_context="${STS_GCP_RESEARCH_CONTEXT:-}"
  research_root="/home/philippherrmann/sts_sweep"
  if [ "$research_context" != "sts-test" ] || [ "$(hostname)" != "sts-test" ] || [ "$PWD" != "$research_root" ]; then
    echo "SEED_GUARD: --gcp-research requires host sts-test in $research_root via the GCP launcher" >&2
    exit 1
  fi
  # The GCP path keeps all argument and replay-cell parsing, but deliberately
  # has no numeric ceiling. It is an explicit operating mode, not a local
  # safety bypass or a replacement for experiment provenance controls.
  MAX_AUTOMATED_SEEDS=0
fi

check_oversized "$@"

if $guard_only; then
  exit 0
fi

exec "$@"
