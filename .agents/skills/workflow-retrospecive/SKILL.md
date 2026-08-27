---
name: workflow-retrospective
description: Use at the end of a substantial or inefficient session to identify avoidable time, token, compute, context, build, verification, and re-learning costs and propose the smallest durable workflow improvements.
---

# Workflow retrospective

Use this skill when the user asks to review the current session for efficiency,
friction, repeated work, or workflow improvements.

The goal is not to critique every action or generate process for its own sake.
Find only improvements likely to save more future effort than they cost.

Do not modify code, documentation, configuration, skills, or workflow unless the
user explicitly asks after seeing the assessment.

## Review principles

1. Use evidence from the current session first: commands, searches, files read,
   builds, tests, benchmark runs, failures, retries, tool calls, and decisions.
   Do not invent timings, causes, repetition, or savings that were not observed.

2. Keep the retrospective cheap. Do not run builds, tests, benchmarks, broad
   repository scans, or expensive tools merely to assess efficiency. Use
   targeted read-only inspection only when needed to determine whether an
   apparent problem already has a documented solution.

3. Look for avoidable cost in these categories:

   - **Re-learning:** rediscovering stable facts already known or documented.
   - **Context:** reading or searching substantially more material than needed.
   - **Build:** unnecessary full builds, repeated compilation, poor target
     selection, avoidable cache misses, or rebuilding unchanged code.
   - **Verification:** tests, benchmarks, seeds, metrics, or checks that did not
     affect the decision.
   - **Agent wandering:** repeating research, architecture discovery, planning,
     or debugging after sufficient evidence already existed.
   - **Tool friction:** using a slower or more complex tool when Git, `rg`,
     focused reads, an existing script, or an existing skill was sufficient.
   - **Command friction:** repeated malformed commands, environment mistakes,
     missing prerequisites, or manually reconstructed command sequences.
   - **Git/worktree friction:** unnecessary setup, repeated state discovery, or
     avoidable cross-worktree duplication.
   - **Knowledge gaps:** stable facts that had to be rediscovered because the
     authoritative maintained documentation did not contain them.
   - **Workflow gaps:** repeated manual procedures that may justify a small
     script, command, skill, preset, or documentation change.

4. Distinguish symptoms from causes. For example, a long compile is not itself
   a workflow defect if the changed headers legitimately require rebuilding all
   dependent translation units.

5. Check whether the repository already contains the solution before proposing
   a new mechanism. Prefer existing `AGENTS.md`, `CODE_MAP.md`, maintained
   knowledge-base pages, skills, build presets, scripts, and tests over adding
   another abstraction.

6. Prefer deletion, simplification, better routing, or reuse over new
   infrastructure. Do not propose telemetry, automation, hooks, databases,
   general frameworks, or new scripts unless a simpler fix is insufficient and
   the expected recurring savings justify them.

## Re-learning and durable knowledge

Do not create per-session journals, summaries, memories, or retrospective logs
by default.

When useful knowledge was rediscovered, classify it:

- If it is already documented, identify why the agent failed to reach it and
  improve routing only if this is likely to recur.
- If it is a stable implementation or operational fact, propose updating the
  existing authoritative knowledge-base page.
- If it is experimental evidence, use the existing experiment ledger.
- If it is a significant durable decision, use the existing decision-log or ADR
  process.
- If it is transient or task-specific, do not preserve it.

The objective is to make future sessions read less, not to create more material
for them to search.

## Change threshold

Treat friction conservatively:

- **One-off and cheap:** report only if useful; recommend no workflow change.
- **Repeated or plausibly recurring:** consider a small durable fix.
- **Rare but very expensive or dangerous:** a durable guardrail may be justified
  even after one occurrence.
- **Uncertain:** state the uncertainty rather than proposing speculative
  infrastructure.

Do not infer recurrence merely because something happened twice during one
debugging chain when both occurrences were necessary.

## Prioritization

Recommend at most three changes.

Rank candidates by expected net benefit:

`expected recurring time/token/compute saved - implementation and maintenance cost`

Prefer fixes that also reduce correctness risk, but do not inflate a minor
efficiency issue into a correctness project.

For each recommended change state:

- observed evidence;
- likely cause;
- smallest proposed intervention;
- expected benefit;
- confidence;
- why doing nothing would or would not be reasonable.

If no change clearly clears the threshold, say:

**No workflow change recommended.**

## Required output

Finish with:

### Session efficiency

- Re-learning: LOW / MEDIUM / HIGH
- Context waste: LOW / MEDIUM / HIGH
- Build waste: LOW / MEDIUM / HIGH
- Verification waste: LOW / MEDIUM / HIGH
- Tool/command friction: LOW / MEDIUM / HIGH
- Agent wandering: LOW / MEDIUM / HIGH

### Highest-leverage findings

List at most three, ordered by expected net benefit. Distinguish observed facts
from inference.

### Recommended action

Give one of:

- **No workflow change recommended**
- **Record/update existing knowledge**
- **Small workflow correction**
- **Small tooling change**

State the single best next action. Do not implement it unless explicitly asked.

`AGENTS.md` remains authoritative for project policy. This skill is a lightweight
diagnostic procedure, not a required end-of-session ritual and not a replacement
for implementation review, experiment review, or maintained project knowledge.
