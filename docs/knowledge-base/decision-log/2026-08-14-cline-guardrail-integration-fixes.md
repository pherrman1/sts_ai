# 2026-08-14 — Cline guardrail integration fixes (one_combat classification, .ps1 hooks)

Date: 2026-08-14
Session/task: Fix Cline "refuses to do work" / `[migration] Tool result missing in legacy conversation history.` stops caused by two Phase-4 guardrail integration bugs.

## Decision

1. `PreToolUse` now blocks `one_combat` only when the segment **executes** the
   binary, resolved through known argv-forwarding wrappers
   (`executed_command` in `tools/agent/cline_guardrails.py`). Merely mentioning
   the name as an argument (cmake build targets, `rg` patterns) is allowed.
2. The `.clinerules/hooks/*.ps1` wrappers were deleted; the extensionless
   wrappers are the sole entry points. The `rm -rf` recursive-deletion rule is
   unchanged.

## Rationale

- Phase 6's legitimate commands were being blocked as if they were game-seed
  sweeps: `cmake --build build --target main one_combat unit-test` and
  `rg one_combat CMakeLists.txt` matched the old any-token `one_combat` rule.
  Blocked PreToolUse calls in this Cline build surface as the migration
  placeholder instead of an error message, so the agent appeared to "stop
  randomly". The seed-guard intent is about **running** the simulator, not
  naming the binary.
- Cline 4.1.8 (JetBrains PyCharm 2026.2 plugin `cline-2.0.0.jar`, core
  `~/.local/share/JetBrains/PyCharm2026.2/cline/core/2.0.0`, rollout variant
  `next`) registers every `.ps1` hook file as `pwsh -File <path>` even on
  Linux. `pwsh` is not installed here, so each hook event logged
  `hook command failed: pwsh -File <repo>/.clinerules/hooks/PreToolUse.ps1: spawn pwsh ENOENT`
  and the agent loop aborted the tool call (`Agent loop caught error`), leaving
  no tool result; on resume the history migration replaced the missing results
  with `[migration] Tool result missing in legacy conversation history.`
  (observed in sessions 1786697382133/1786704142134/1786705649756/
  1786706001756/1786706113160). Deleting the `.ps1` files removes the failing
  pwsh execution while keeping the working bash wrappers.

## Alternatives considered

- Install `pwsh` — rejected: keeps the repo portable but runs every hook twice
  (bash + pwsh) per event and still requires the interpreter on every Linux
  checkout.
- Block `one_combat` only as `parts[0]` — rejected: bypasses argv-forwarding
  wrappers such as `env STS_FAIR=1 ./build/one_combat ...`.
- Broaden the `rm -rf` rule — rejected explicitly; Phase 6 uses fresh uniquely
  named build directories instead, so no recursive-deletion change is needed.

## Evidence

- `tools/agent/cline_guardrails.py` — `executed_command`, `_WRAPPER_OPTION_ARGS`,
  `check_command` one_combat rule.
- `tests/agent/test_cline_guardrails.py` — `PreToolUseTests.test_one_combat_mention_vs_execution`
  (ALLOW: cmake build target, `rg`; BLOCK: direct and `env`/`nohup`/`time`/`nice`/`setsid` wrapped).
- `~/.cline/cline-core-service.log` — `hook command failed: pwsh -File <repo>/.clinerules/hooks/*.ps1 ... spawn pwsh ENOENT` at 13:15–13:19, immediately followed by `Agent loop caught error`; `which pwsh` empty.
- Guardrails suite: 15/15 `python3 -m unittest discover -s tests/agent -v`; `tools/agent/doctor.sh` all checks passed.

## Status and follow-up

- Implemented on `infra/cmake-core-objects-phase6` (no upstream; push requires an established upstream).
- Follow-up (user action): the affected session histories under `~/.cline/data/sessions/` still contain the placeholder text; repair strips the placeholder `tool_result`/dangling `tool_use` pairs and requires a Cline restart.
