#!/usr/bin/env bash
set -euo pipefail
# Seed-sweep argument positions verified against apps/one_combat.cpp mode dispatch
# (2026-08-10).  Modes that parse nSeeds from argc/argv are listed; modes not in
# this table are passed through without seed checking.

MAX_AUTOMATED_SEEDS=128

declare -A ONE_COMBAT_SEED_INDEX=(
  ["allbench"]=3            ["bench"]=3             ["bestbench"]=3
  ["cardbench"]=3           ["causalgen"]=2         ["combatgen"]=2
  ["combobench"]=3          ["cpsictr"]=3           ["datagen"]=2
  ["datagen2"]=2            ["datagen3"]=2          ["distgen"]=2
  ["draftbench"]=3          ["fairgen"]=2           ["fightgen"]=2
  ["frontiergen"]=2         ["leafdiag"]=2          ["leafref"]=5
  ["oocnextgen"]=2          ["pathbench"]=3         ["pathcfgen"]=2
  ["policygen"]=2           ["restbench"]=3         ["rollouttrace"]=4
  ["runbench"]=3            ["searchdiag"]=2        ["shopbench"]=3
  ["skipbench"]=3           ["strategicgen"]=2      ["strategicgen2"]=2
  ["strategicmarggen"]=2
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
        if [[ "$seeds" =~ ^[0-9]+$ ]] && [ "$seeds" -gt "$MAX_AUTOMATED_SEEDS" ]; then
          echo "SEED_GUARD: $exe $mode requests $seeds seeds; automated maximum is $MAX_AUTOMATED_SEEDS" >&2
          exit 1
        fi
      fi
    elif [ "$exe" = "python" ] || [ "$exe" = "python3" ]; then
      local script="${argv[$((i + 1))]:-}"
      local script_name
      script_name="$(exe_name "$script")"
      local idx="${PYTHON_SEED_INDEX[$script_name]:-}"
      if [ -n "$idx" ]; then
        local seeds="${argv[$((i + idx))]:-}"
        if [[ "$seeds" =~ ^[0-9]+$ ]] && [ "$seeds" -gt "$MAX_AUTOMATED_SEEDS" ]; then
          echo "SEED_GUARD: $script_name requests $seeds seeds; automated maximum is $MAX_AUTOMATED_SEEDS" >&2
          exit 1
        fi
      fi
    fi
    i=$((i + 1))
  done
}

if [ $# -eq 0 ]; then
  echo "Usage: tools/seed_guard.sh [guard-only] <command...>" >&2
  echo "  With 'guard-only': validates seed count and exits 0/1 without running the command." >&2
  echo "  Without 'guard-only': validates seed count, then execs the command if valid." >&2
  exit 1
fi

guard_only=false
if [ "$1" = "guard-only" ]; then
  guard_only=true
  shift
fi

check_oversized "$@"

if $guard_only; then
  exit 0
fi

exec "$@"
