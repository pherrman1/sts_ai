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
need_file tools/test_pi_subagent_lifecycle.py

echo
echo "Subagent extension status:"
if grep -q "STS-LOCAL FORK" .pi/extensions/subagent/index.ts; then
  base="$(sed -n 's|^// Base: upstream commit \([0-9a-f]\+\).*|\1|p' \
    .pi/extensions/subagent/index.ts | head -n1)"
  echo "  index.ts: STS-local fork (base ${base:-unknown}) - NOT byte-identical"
  echo "            to upstream. install_pi_subagent.sh will refuse to replace"
  echo "            it unless STS_FORCE_PI_SUBAGENT=1."

  if grep -q "STS-SUBAGENT-LIFECYCLE-GUARD" .pi/extensions/subagent/index.ts &&
     grep -q "AGENT_END_CLOSE_GRACE_MS" .pi/extensions/subagent/index.ts &&
     grep -q "SUBAGENT_HARD_TIMEOUT_MS" .pi/extensions/subagent/index.ts; then
    echo "  lifecycle: hardened (agent_end close watchdog + hard timeout present)"
  else
    echo "ERROR: STS-local subagent fork is missing lifecycle hardening."
    echo "       Expected STS-SUBAGENT-LIFECYCLE-GUARD,"
    echo "       AGENT_END_CLOSE_GRACE_MS, and SUBAGENT_HARD_TIMEOUT_MS."
    fail=1
  fi
else
  echo "  index.ts: no STS fork marker - assumed byte-identical to the pinned"
  echo "            upstream revision."
  echo "ERROR: lifecycle-hardened STS-local subagent fork is required."
  fail=1
fi

echo
echo "Subagent lifecycle regression tests:"
python3 tools/test_pi_subagent_lifecycle.py || fail=1

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