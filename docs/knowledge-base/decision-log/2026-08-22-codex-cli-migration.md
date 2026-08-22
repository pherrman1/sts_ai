# 2026-08-22 — Codex CLI migration

## Decision

Adopt Codex CLI as the interactive repository agent while retaining the Cline
configuration temporarily as a rollback path. Keep the durable contract in
`AGENTS.md`, expose task-specific procedures as repository skills under
`.agents/skills/`, and keep repository-scoped Codex execution and MCP defaults
in `.codex/config.toml`.

Codex uses the `workspace-write` sandbox with approval-on-request and no
sandboxed network access. Serena starts with `--project-from-cwd`; RepoWise
starts in workspace mode at the active worktree's parent (`..`) so the agent can
call `list_repos` and explicitly select the alias whose path matches the active
Git worktree. Executables resolve through `PATH` rather than a user-specific
home-directory path.

## Guardrail boundary

Do not connect `.clinerules/hooks/` or
`tools/agent/cline_guardrails.py` directly to Codex. The implementation parses
Cline's event JSON and returns Cline cancellation objects, so reuse without a
tested adapter would not prove enforcement. During migration,
`tools/seed_guard.sh` remains the mechanical boundary for game-seed execution;
Codex sandboxing, approvals, repository instructions, focused verification,
and GitHub Actions provide the other layers.

## Alternatives considered

- Copy the Cline hooks into Codex configuration: rejected because the event and
  response protocol is not compatible or tested.
- Remove Cline files immediately: rejected so the user retains a rollback path
  during representative-task acceptance testing.
- Omit Serena and RepoWise initially: rejected because both installed commands
  explicitly support Codex/stdio and the repository already documents their
  constrained roles. Misrouted or unavailable servers still fall back to Git,
  `rg`, and focused reads.

## Evidence

- `serena start-mcp-server --help` documents `--project-from-cwd` as intended
  for CLI agents including Codex.
- `repowise mcp --help` documents stdio support for Codex and workspace mode.
- `codex -C <worktree> --strict-config doctor --json` parses the project config
  and reports three locally consistent stdio MCP servers: the existing global
  server plus repository Serena and RepoWise.
- `tests/agent/test_cline_guardrails.py` and
  `tools/agent/cline_guardrails.py::handle_pre_tool_use` pin the legacy Cline
  protocol and policy behavior.

## Status and follow-up

Adopted for the Codex pilot. Remove the legacy `.cline/`, `.clinerules/`, and
`.clineignore` files only after representative read, implementation, research,
and review tasks pass the migration acceptance checks. A future Codex hook
adapter must have protocol fixtures and command-policy tests before it can be
described as mechanical enforcement.
