# ADR-0008: Guarded Cline, Serena, and RepoWise routing

Date: 2026-08-13
Status: accepted

## Context

Cline is the interactive coding-agent harness. Serena supplies live semantic code intelligence. RepoWise can contribute a derived structural index, ADR context, history-aware risk, health, and candidate dead-code signals, but it must not become a competing knowledge store or paid generation channel.

## Decision

Use Cline for interactive Plan/Act work, Serena for exact symbol definitions, references, diagnostics, and explicitly approved semantic refactoring, and RepoWise for structural overview, ADR rationale, git/change risk, hotspots, health, and cautious dead-code hypotheses. Keep RepoWise keyless with mock embeddings, disabled telemetry, no generated prose, no hooks, and no editor setup. Git-tracked Markdown remains authoritative.

## Rationale

The prior Cline/Serena workflow established the harness and semantic boundary. This guarded pilot extends it without enabling Serena memories, RepoWise LLM generation, automatic hooks, or repository-local generated state.

## Alternatives considered

- Use RepoWise graphs for all symbol questions — rejected because live LSP semantic navigation is the more exact source for C++ and Python symbols.
- Enable RepoWise prose, decision mining, or hooks — rejected because this pilot is keyless, non-authoritative, and must not create additional generated knowledge or approval bypasses.

## Consequences

RepoWise outputs are advisory. Dead-code findings require checking entry points, modes, environment paths, bindings, tests, and dynamic loading before deletion. `.repowise/` remains ignored and no paid generation is permitted without explicit authorization.

## Affected files

- `AGENTS.md`
- `.serena/project.yml`
- `.repowiseIgnore`
- `.gitignore`
- historical session record

## Evidence

- historical session record — establishes Cline as harness and Serena as semantic tooling while rejecting Serena memories.
- `.serena/project.yml` — declares LSP C++ and Python language servers and excludes memory/onboarding tools.
- `AGENTS.md` — defines project authority, verification, and approval rules.
