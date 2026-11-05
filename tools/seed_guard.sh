#!/usr/bin/env bash
set -euo pipefail
# Seed-sweep argument positions verified against apps/one_combat.cpp mode dispatch
# (2026-08-31). Other unlisted commands pass through without seed checking.

declare -A ONE_COMBAT_SEED_INDEX=(
  ["bestbench"]=3
  ["oocleafreplayprobe"]=2
  ["oocleafstabilityprobe"]=2
  ["oocselectivesilvergen"]=2
  ["heartoutcomegen"]=2
  ["expertreplay"]=2
  ["expertfights"]=2
  ["datagen3"]=2
  ["e2cgen"]=2
  ["wholecombatgen"]=2     ["combattransitiongen"]=2 ["combattransitionforcedgen"]=2 ["combattransitionlizardtargetcandidategen"]=2
  ["combattransitionlizardgen"]=2 ["combattransitionlizardtargetpairgen"]=2
  ["combatevalgen"]=2 ["ooccfaudit"]=2 ["vwinrefreshgen"]=2 ["vwinrefreshcrashdiag"]=2 ["ooccfpilotgen"]=2 ["cardstrengthprobe"]=2
  ["bossheadroom347gen"]=2
  ["bossrescue347"]=2 ["bossrescue347selftest"]=2
  ["silverparams400gen"]=2
  ["silverstopreplaygen"]=2
  ["ctmsilvergen"]=2
  ["endgamerootgen"]=2
  ["silversynthgen"]=2
  ["silverazgen"]=2
  ["silverazfocusgen"]=2
  ["silverfocusevalgen"]=2
  ["act4replay"]=2
  ["fightreplay"]=2
  ["turndomgen"]=2
  ["vwinrefreshbranchselftest"]=2
  ["vwinrefreshfatalcountselftest"]=2
  ["oocnextgen"]=2
  ["pathcfgen"]=2
  ["strategicgen"]=2        ["strategicgen2"]=2
  ["strategicmarggen"]=2
  ["potionpriceprobe"]=2
  ["fightendpairgen"]=2
  ["oocfactoreval"]=2      ["oocmargtradeoffeval"]=2 ["oock3tradeoffeval"]=2
  ["oocsemanticfullruneval"]=2 ["oockbudgeteval"]=2
  ["oocsemanticcapture"]=2 ["oocsemanticeval"]=2
  ["rundriverlossselftest"]=2
)

declare -A PYTHON_SEED_INDEX=(
  ["check_replay.py"]=3
  ["heart1_parity_seeds.py"]=3
)

exe_name() {
  local name="$1"
  name="${name##*/}"
  echo "$name"
}

check_seed_counts() {
  local argv=("$@")
  local i=0
  while [ $i -lt ${#argv[@]} ]; do
    local exe
    exe="$(exe_name "${argv[$i]}")"
    if [ "$exe" = "one_combat" ]; then
      local mode="${argv[$((i + 1))]:-}"
      local idx=""
      if [ -n "$mode" ]; then
        idx="${ONE_COMBAT_SEED_INDEX[$mode]:-}"
      fi
      if [ -n "$idx" ]; then
        local seeds="${argv[$((i + idx))]:-}"
        if { [ "$mode" = "oocleafreplayprobe" ] || [ "$mode" = "oocleafstabilityprobe" ] || [ "$mode" = "oocselectivesilvergen" ] || [ "$mode" = "heartoutcomegen" ] || [ "$mode" = "expertreplay" ] || [ "$mode" = "expertfights" ]; } && [ "$seeds" != 1 ]; then
          echo "SEED_GUARD: $mode requires exactly one source seed" >&2
          exit 1
        fi
        # Semantic label pilot is deliberately bounded independently of the
        # general seed-count validation (a native mode contract).
        if [ "$mode" = "oocsemanticcapture" ] || [ "$mode" = "oocsemanticeval" ]; then
          if ! [[ "$seeds" =~ ^0*([1-9]|1[0-6])$ ]]; then
            echo "SEED_GUARD: $mode requires 1..16 source seeds/decisions" >&2
            exit 1
          fi
        fi
        if ! [[ "$seeds" =~ ^[0-9]+$ ]] || ! [[ "$seeds" =~ [1-9] ]]; then
          echo "SEED_GUARD: $exe requires a positive integer seed count" >&2
          exit 1
        fi
      fi
    elif [ "$exe" = "exact_combat_solver" ]; then
      local seeds="${argv[$((i + 1))]:-}"
      if ! [[ "$seeds" =~ ^[0-9]+$ ]] || ! [[ "$seeds" =~ [1-9] ]]; then
        echo "SEED_GUARD: $exe requires a positive integer seed count" >&2
        exit 1
      fi
    elif [ "$exe" = "python" ] || [ "$exe" = "python3" ]; then
      local script="${argv[$((i + 1))]:-}"
      local script_name
      script_name="$(exe_name "$script")"
      local idx=""
      if [ -n "$script_name" ] && [ "${argv[$((i + 2))]:-}" != "--self-test" ]; then
        idx="${PYTHON_SEED_INDEX[$script_name]:-}"
      fi
      if [ -n "$idx" ]; then
        local seeds="${argv[$((i + idx))]:-}"
        if ! [[ "$seeds" =~ ^[0-9]+$ ]] || ! [[ "$seeds" =~ [1-9] ]]; then
          echo "SEED_GUARD: $exe requires a positive integer seed count" >&2
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

if [[ "$1" == --* ]]; then
  echo "SEED_GUARD: unknown option $1" >&2
  exit 1
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

check_seed_counts "$@"

if $guard_only; then
  exit 0
fi

exec "$@"
