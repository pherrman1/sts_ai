#!/usr/bin/env bash
# Bootstrap the locked shared Python environment for this checkout.

set -eu

link_only=0
quiet=0

usage() {
    printf 'usage: %s [--link-only] [--quiet]\n' "$0"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --link-only) link_only=1 ;;
        --quiet) quiet=1 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
    shift
done

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if ! command -v uv >/dev/null 2>&1; then
    printf 'bootstrap_python: uv is required; see https://docs.astral.sh/uv/\n' >&2
    exit 1
fi

if ! command -v sha256sum >/dev/null 2>&1; then
    printf 'bootstrap_python: sha256sum is required\n' >&2
    exit 1
fi

lock_id="$(sha256sum uv.lock | cut -c1-16)"
if [ -n "${STS_AI_SHARED_VENV_ROOT:-}" ]; then
    shared_root="$STS_AI_SHARED_VENV_ROOT"
else
    uv_cache_dir="$(uv cache dir)"
    shared_root="$(dirname "$uv_cache_dir")/sts_ai/venvs"
fi
shared_env="$shared_root/$lock_id"

if [ "$link_only" -eq 0 ]; then
    UV_PROJECT_ENVIRONMENT="$shared_env" uv sync --locked --extra analysis
elif [ ! -x "$shared_env/bin/python" ]; then
    [ "$quiet" -eq 1 ] || printf 'bootstrap_python: shared environment missing; run tools/agent/bootstrap_python.sh\n' >&2
    exit 1
fi

if [ -L .venv ]; then
    linked_env="$(readlink -f .venv)"
    if [ "$linked_env" != "$(readlink -f "$shared_env")" ]; then
        printf 'bootstrap_python: .venv points to %s, expected %s\n' "$linked_env" "$shared_env" >&2
        exit 1
    fi
elif [ -e .venv ]; then
    printf 'bootstrap_python: refusing to replace existing private .venv; move it aside and retry\n' >&2
    exit 1
else
    ln -s "$shared_env" .venv
fi

if [ "$quiet" -eq 0 ]; then
    printf 'python_environment_ready shared=%s worktree=%s/.venv\n' "$shared_env" "$repo_root"
fi
