#!/usr/bin/env bash
set -euo pipefail

# Vendor Pi's official reference subagent extension at a known-good upstream
# revision from 2026-08-08. Override deliberately with PI_SUBAGENT_REF.
#
# Since 2026-08-08 the vendored .pi/extensions/subagent/index.ts is an
# STS-local fork (see the "STS-LOCAL FORK" header comment in the file) with
# live observability additions on top of upstream; agents.ts stays upstream.
# Re-running this script therefore REFUSES to replace index.ts silently:
# pass STS_FORCE_PI_SUBAGENT=1 to overwrite the local fork with the upstream
# revision (losing the observability additions).
REF="${PI_SUBAGENT_REF:-c185d412382581860a489b4959737bad1d119492}"
BASE="https://raw.githubusercontent.com/earendil-works/pi/${REF}/packages/coding-agent/examples/extensions/subagent"

cd "$(git rev-parse --show-toplevel)"
mkdir -p .pi/extensions/subagent

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

echo "Fetching Pi reference subagent extension at $REF"
curl -fsSL "$BASE/index.ts" -o "$tmpdir/index.ts"
curl -fsSL "$BASE/agents.ts" -o "$tmpdir/agents.ts"

if [[ -f .pi/extensions/subagent/index.ts ]] &&
   ! cmp -s "$tmpdir/index.ts" .pi/extensions/subagent/index.ts; then
  if [[ "${STS_FORCE_PI_SUBAGENT:-0}" == "1" ]]; then
    echo "STS_FORCE_PI_SUBAGENT=1: overwriting the STS-local fork of index.ts"
    echo "with the upstream revision (observability additions will be lost)."
  else
    echo "REFUSING: .pi/extensions/subagent/index.ts is the STS-local fork"
    echo "($REF base) and differs from upstream."
    echo "Set STS_FORCE_PI_SUBAGENT=1 to overwrite it deliberately."
    exit 1
  fi
fi

cp "$tmpdir/index.ts" .pi/extensions/subagent/index.ts
cp "$tmpdir/agents.ts" .pi/extensions/subagent/agents.ts

echo
echo "Installed:"
ls -l .pi/extensions/subagent/index.ts .pi/extensions/subagent/agents.ts

echo
if grep -q "STS-LOCAL FORK" .pi/extensions/subagent/index.ts; then
  echo "index.ts is the STS-local fork (NOT byte-identical to upstream)."
else
  echo "index.ts is byte-identical to upstream $REF."
fi
echo "Review these files, then start Pi interactively and trust the project."
echo "Project-local agents must be invoked with agentScope: project (or both)."
