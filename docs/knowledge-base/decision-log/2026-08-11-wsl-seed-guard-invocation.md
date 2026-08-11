# WSL seed-guard invocation

Date: 2026-08-11

## Decision

OpenCode Build may run Linux seed commands from Windows PowerShell as
`wsl bash tools/seed_guard.sh ...`. Shell scripts are pinned to LF through
`.gitattributes`.

## Rationale

PowerShell opens `.sh` files through the asynchronous Git Bash file
association, while the cached `one_combat` binary is a Linux/WSL executable.
The explicit WSL Bash invocation is synchronous, preserves guard enforcement,
and avoids CRLF parse failures.

## Alternatives considered

- Direct `tools/seed_guard.sh ...`: rejected on Windows because the `.sh` file
  association detaches and does not return command output reliably.
- Git Bash: rejected because it cannot execute the cached Linux binary.

## Evidence

- `opencode.json` Build-agent Bash permissions.
- `.gitattributes` shell-script EOL rule.
- `tools/seed_guard.sh::check_oversized`: WSL smoke passed and a 129-seed
  `bestbench` guard-only request was rejected.

## Status

Adopted. OpenCode must be restarted to load the permission change.
