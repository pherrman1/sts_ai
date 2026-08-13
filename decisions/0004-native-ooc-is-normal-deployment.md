# ADR-0004: Native out-of-combat inference is the normal deployment path

Date: 2026-08-13
Status: accepted

## Context

Run-level policy can use in-process native artifacts or optional Python-server endpoints. The default executable path must be clear for reproducible runs.

## Decision

Use native in-process out-of-combat inference by default. Keep `v_server.py` optional for normal `bestbench`, while allowing explicitly server-backed experimental and self-play paths to require it.

## Rationale

The code map and maintained OOC documentation identify compact native floor and win artifacts as startup-loaded defaults and describe the server bridge as optional except for specific paths.

## Alternatives considered

- Require the Python inference server for every run — rejected because the default native path exists and is the current normal deployment contract.

## Consequences

Startup validation must establish both artifact loading and whether a selected arm actually consumes an optional server model.

## Affected files

- `apps/one_combat.cpp`
- `models/v_rich_trees.txt`
- `models/v_win_trees.txt`
- `v_server.py`

## Evidence

- `docs/knowledge-base/CODE_MAP.md` — maps native OOC artifacts and the optional server bridge.
- `docs/knowledge-base/architecture/out-of-combat.md` — documents the normal in-process OOC policy chain.
