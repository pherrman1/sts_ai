#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

fail=0

need_file() {
  if [[ ! -f "$1" ]]; then
    echo "MISSING: $1"
    fail=1
  else
    echo "ok: $1"
  fi
}

command -v pi >/dev/null || {
  echo "ERROR: pi is not on PATH"
  exit 1
}

echo "Pi: $(pi --version 2>/dev/null || true)"
echo "Node: $(node --version 2>/dev/null || true)"
echo

need_file AGENTS.md
need_file .pi/extensions/subagent/index.ts
need_file .pi/extensions/subagent/agents.ts
need_file .pi/extensions/sts-safety.ts
need_file .pi/extensions/sts-tools.ts
need_file .pi/agents/architect.md
need_file .pi/agents/investigator.md
need_file .pi/agents/implementer.md
need_file .pi/agents/reviewer.md
need_file .pi/agents/reviewer-pro.md
need_file .pi/prompts/sts-investigate.md

echo
echo "DeepSeek models visible to Pi:"
pi --list-models deepseek || fail=1

echo
if [[ $fail -ne 0 ]]; then
  echo "Pi starter-kit check FAILED."
  exit 1
fi

echo "Pi starter-kit files are present."
echo "Next: run Pi interactively from this repo, review/trust project resources,"
echo "then test a project-scoped read-only subagent."
