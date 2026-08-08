#!/usr/bin/env bash
set -euo pipefail

# Vendor Pi's official reference subagent extension at a known-good upstream
# revision from 2026-08-08. Override deliberately with PI_SUBAGENT_REF.
REF="${PI_SUBAGENT_REF:-c185d412382581860a489b4959737bad1d119492}"
BASE="https://raw.githubusercontent.com/earendil-works/pi/${REF}/packages/coding-agent/examples/extensions/subagent"

cd "$(git rev-parse --show-toplevel)"
mkdir -p .pi/extensions/subagent

echo "Installing Pi reference subagent extension at $REF"
curl -fsSL "$BASE/index.ts" -o .pi/extensions/subagent/index.ts
curl -fsSL "$BASE/agents.ts" -o .pi/extensions/subagent/agents.ts

echo
echo "Installed:"
ls -l .pi/extensions/subagent/index.ts .pi/extensions/subagent/agents.ts

echo
echo "Review these files, then start Pi interactively and trust the project."
echo "Project-local agents must be invoked with agentScope: project (or both)."
