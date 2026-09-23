#!/usr/bin/env bash
set -euo pipefail
# Seed-sweep argument positions verified against apps/one_combat.cpp mode dispatch
# (2026-08-31).  Modes that parse nSeeds from argc/argv are listed; modes not in
# this table are passed through without seed checking.

MAX_AUTOMATED_SEEDS=128

declare -A ONE_COMBAT_SEED_INDEX=(
  ["bestbench"]=3
  ["causalgen"]=2           ["combatgen"]=2
  ["datagen"]=2
  ["datagen2"]=2            ["datagen3"]=2          ["distgen"]=2
  ["e2cgen"]=2              ["fairgen"]=2           ["fightgen"]=2
  ["wholecombatgen"]=2     ["combattransitiongen"]=2 ["combattransitionlizardgen"]=2 ["combatevalgen"]=2 ["ooccfaudit"]=2
  ["particle_leaf_probe"]=2
  ["particle_posterior_probe"]=2
  ["fightrep"]=6            ["oocnextgen"]=2
  ["pathcfgen"]=2
  ["policygen"]=2
  ["searchdiag"]=2
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
      if [ "$mode" = "fightrep" ]; then
        # Grid replay: seed-equivalent count = NFIGHTS x |PARTICLES| x |SIMS|.
        # argv: one_combat fightrep CAPTURE_DIR OUTFILE PARTICLES SIMS [NFIGHTS]
        local nf="${argv[$((i + 6))]:-}"
        [[ "$nf" =~ ^[0-9]+$ ]] || nf=0
        local cells=0
        if [ "$nf" -gt 0 ]; then
          local pc="${argv[$((i + 4))]:-}" sc="${argv[$((i + 5))]:-}"
          local np=0 ns=0 tok
          IFS=',' read -ra parts <<< "$pc"
          for tok in "${parts[@]}"; do [ -n "$tok" ] && np=$((np + 1)); done
          IFS=',' read -ra parts <<< "$sc"
          for tok in "${parts[@]}"; do [ -n "$tok" ] && ns=$((ns + 1)); done
          cells=$((nf * np * ns))
        fi
        if [ "$MAX_AUTOMATED_SEEDS" -gt 0 ] && [ "$cells" -gt "$MAX_AUTOMATED_SEEDS" ]; then
          echo "SEED_GUARD: one_combat fightrep requests $cells replay cells (${nf}x${np}x${ns}); automated maximum is $MAX_AUTOMATED_SEEDS" >&2
          exit 1
        fi
      elif [ -n "$idx" ]; then
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
