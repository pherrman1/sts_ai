#!/usr/bin/env bash
# Diagnose the inexpensive prerequisites for this checkout.  This script never
# installs dependencies, initializes submodules, or changes project state.
set -u

failures=0

pass() {
    printf 'PASS: %s\n' "$1"
}

fail() {
    printf 'FAIL: %s\n' "$1" >&2
    failures=$((failures + 1))
}

if ! repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
    fail "run from inside a Git checkout"
    exit 1
fi
if [ "$(pwd -P)" != "$repo_root" ]; then
    fail "run from repository root: $repo_root"
else
    pass "repository root: $repo_root"
fi

for path in CMakeLists.txt CMakePresets.json pyproject.toml uv.lock json pybind11 selfplay/loop.sh tools/seed_guard.sh; do
    if [ -e "$repo_root/$path" ]; then
        pass "expected path exists: $path"
    else
        fail "expected path missing: $path"
    fi
done

if submodule_status="$(git -C "$repo_root" submodule status --recursive 2>/dev/null)"; then
    if printf '%s\n' "$submodule_status" | grep -Eq '^[+U-]'; then
        fail "submodules are not at the revisions recorded by this checkout; run: git submodule update --init --recursive"
    else
        pass "submodules initialized and at recorded revisions"
    fi
else
    fail "could not inspect submodule state"
fi

for command in cmake g++ python3; do
    if command -v "$command" >/dev/null 2>&1; then
        pass "$command available: $(command -v "$command")"
    else
        fail "$command is not available on PATH"
    fi
done

if command -v uv >/dev/null 2>&1; then
    pass "uv available: $(uv --version)"
    if (cd "$repo_root" && uv lock --check); then
        pass "uv.lock is consistent with pyproject.toml"
    else
        fail "uv.lock is inconsistent; run: uv lock"
    fi
else
    fail "uv is not available on PATH; install it from https://docs.astral.sh/uv/"
fi

if [ "$failures" -eq 0 ]; then
    printf 'Environment doctor: all checks passed.\n'
    exit 0
fi

printf 'Environment doctor: %d check(s) failed; no repairs were attempted.\n' "$failures" >&2
exit 1
