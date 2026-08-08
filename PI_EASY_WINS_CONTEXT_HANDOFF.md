# Handoff: Agent-Oriented Repository Simplification — Easy Wins 1–3

## Objective

Reduce the amount of repository context that Pi agents need to read before they can do useful work.

This is **not** a production-code refactor. Do not split `apps/one_combat.cpp`, delete old code, change model behavior, alter evaluation semantics, or redesign the repository.

Implement only these three low-risk improvements:

1. make agent navigation through large files more targeted;
2. add a compact current code map for fast routing;
3. add lightweight measurement of what Pi agents actually read/search so future refactoring is evidence-driven.

The expected outcome is lower investigation latency/token use without changing Slay the Spire behavior.

## Required reading

Before editing:

1. Read `AGENTS.md`.
2. Read `docs/knowledge-base/README.md`.
3. Read `.pi/agents/architect.md`, `.pi/agents/investigator.md`, and `.pi/agents/reviewer.md`.
4. Inspect `.pi/extensions/subagent/index.ts` and any current Pi observability/event logging code.
5. Inspect `tools/ai_cycle.py` only to understand existing session artifacts and protected workflow paths. Do not redesign it here.

Treat current repository code as authoritative if this handoff is stale.

# Part 1 — Large-file navigation rules

Add a concise section to `AGENTS.md`, e.g. `## Agent context and large-file navigation`.

The guidance should say:

- Do not read large source/history files from beginning to end unless whole-file understanding is genuinely required.
- Search for a symbol, mode, experiment number, keyword, caller, artifact name, or date first.
- For large source files, read a focused region around the relevant symbol/call site and expand only when dependencies require it.
- For `EXPERIMENTS.md`, search first and read only relevant sections.
- Prefer `docs/knowledge-base/CODE_MAP.md` and the maintained KB before broad repository search.
- Do not inspect generated/model artifacts under `build/` unless the task explicitly depends on them.
- Ignore `docs/archive/`, `.ai/`, ignored experiment buffers, generated outputs, and similar historical/session data unless explicitly relevant.
- When a task crosses subsystem boundaries, identify those boundaries first rather than reading the entire integration driver.
- Reviewers may expand scope when needed to prove semantics, but should still prefer targeted reads.

Also update `architect.md` and `investigator.md` to follow this policy explicitly.

The investigator should:
- answer one narrow question at a time;
- search first;
- return relevant files/symbols so the architect does not have to rediscover them.

Do not impose arbitrary hard line-count caps that could prevent necessary inspection.

# Part 2 — Create `docs/knowledge-base/CODE_MAP.md`

Create a compact routing table for humans and agents.

Recommended shape:

```markdown
# Current code map

Last verified: YYYY-MM-DD

Purpose:
Fast routing for humans and agents. Code remains authoritative.

## Combat search
| Topic | Primary code | Key symbols / modes | Read next |

## Out-of-combat policy
...

## Strategic data generation / counterfactuals
...

## Training and export
...

## Native inference / model loading
...

## Evaluation / benchmarks
...

## Self-play
...

## Python bindings
...

## Agent tooling
...
```

For each row include:
- subsystem/topic;
- primary repository-relative file(s);
- important class/function/mode names;
- relevant knowledge-base page;
- optionally a short status note such as `current default`, `producer`, `consumer`, `integration only`, or `experimental`.

Constraints:
- derive the map from current code and current KB pages;
- do not infer rationale;
- do not copy changing benchmark numbers;
- do not list every file;
- prefer current execution paths;
- mark historical/experimental paths clearly;
- label uncertainty as `Unverified` or `Open question`.

Link `CODE_MAP.md` near the top of `docs/knowledge-base/README.md` as the first routing document for agents.

# Part 3 — Measure agent reads/searches

Reuse the Pi JSON/event path that already observes tool calls.

Record **tool metadata only**:
- timestamp;
- parent/subagent role;
- model;
- turn number when available;
- tool name;
- repository-relative path;
- read offset/limit;
- grep/find pattern;
- success/failure;
- optionally duration and returned line/byte count if cheap.

Do NOT record:
- hidden reasoning;
- API keys;
- full file contents;
- full prompts;
- arbitrary environment variables;
- private user data.

Prefer per-session JSONL in the existing ignored/session area, e.g.:

```text
.ai/<session>/context-reads.jsonl
```

If interactive Pi sessions do not naturally have an `.ai/<session>` directory, use a clearly documented ignored telemetry location.

Example:

```json
{"ts":"...","agent":"architect","model":"deepseek/deepseek-v4-pro","tool":"read","path":"apps/one_combat.cpp","offset":7990,"limit":120,"ok":true}
```

Add a small summarizer, e.g.:

```text
tools/summarize_agent_context.py
```

It should accept one or more telemetry JSONL files and report:
- reads by file;
- searches by directory;
- requested read lines by file when available;
- most frequently searched patterns/symbols;
- counts by agent role;
- top hotspots.

Example:

```text
Top files by requested lines
1. apps/one_combat.cpp       2840
2. EXPERIMENTS.md            1910

Most read files
1. apps/one_combat.cpp         18 reads

Most searched directories
1. apps/                       22
2. docs/knowledge-base/        15

By role
architect       41
investigator    27
reviewer        13
```

Telemetry is diagnostic only. Agent execution must not fail because telemetry cannot be written.

# Validation

Do not run game-seed benchmarks.

Required:
1. existing Pi/tooling tests;
2. new unit tests for telemetry parsing/aggregation;
3. fake/synthetic Pi events rather than real API calls;
4. `git diff --check`;
5. inspect complete diff;
6. verify every `CODE_MAP.md` path/symbol exists;
7. verify prompt read-only/write restrictions remain intact;
8. verify telemetry contains no sensitive values;
9. verify telemetry write failure is non-fatal.

# Suggested order

A. Navigation policy → verify prompts.
B. `CODE_MAP.md` → verify paths/symbols.
C. Telemetry + summarizer → synthetic tests + existing tests.

# Non-goals

Do not:
- split `apps/one_combat.cpp`;
- delete dead/old code;
- move experimental modes;
- split `EXPERIMENTS.md`;
- change benchmark protocols;
- change training/inference behavior;
- alter model artifacts;
- change the 128-seed cap;
- replace `ai_cycle.py`;
- change the default backend;
- redesign Pi orchestration.

Those are later tasks informed by the telemetry produced here.

# Completion report

Report:
1. files changed;
2. navigation rules added;
3. `CODE_MAP.md` structure and uncertain mappings;
4. telemetry storage location;
5. example telemetry record;
6. example summarizer output from synthetic/test data;
7. tests/checks and results;
8. deviations;
9. ELI5: how this makes future agents faster without changing the StS bot.

If current repository evidence contradicts this handoff, preserve the underlying goal and explain the deviation rather than blindly following stale instructions.
