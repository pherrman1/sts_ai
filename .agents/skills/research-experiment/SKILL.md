---
name: research-experiment
description: Use for hypothesis-driven research experiments, benchmark proposals, and evidence-based interpretation in this repository.
---

# Research experiment workflow

Use this skill for research questions, experiment proposals, benchmark
interpretation, and evidence recording in this repository.

## Choose the path first

### External ChatGPT/Sol handoff

Use this path when the handoff supplies the baseline, goal/hypothesis, verified
repository facts, required behavior, non-goals, and verification criteria.
Treat it as the accepted design plan. Codex performs only the bounded preflight
in the operations workflow, checks for material contradiction, and then
implements or runs the specified experiment. Do not restart broad research or
planning merely to reproduce the handoff.

### Codex-originated research

Use this path when Codex is asked to investigate an open question without an
accepted external plan. Establish the current baseline, inspect relevant
history and maintained pages, generate competing hypotheses, and propose a
one-variable intervention before implementation or an expensive run. If the
question becomes conceptually ambiguous, stop and report what decision is
missing rather than expanding the search indefinitely.

1. Read `AGENTS.md`, `docs/knowledge-base/CODE_MAP.md`,
   `docs/knowledge-base/operations/agent-context-and-workflow.md`, the relevant
   maintained knowledge-base page, and relevant experiment-ledger entries before
   proposing a change.
2. State the hypothesis, baseline, expected evidence, decision rule, and
   constraints before an expensive run. Generate multiple plausible
   explanations when the question is uncertain.
3. Change one conceptual variable at a time where practical. Preserve paired
   common seeds, fair/known-RNG labels, model paths or hashes, simulation
   budgets, and output schema.
4. Use the cheapest meaningful verification first. Route every seed-based
   command through `tools/seed_guard.sh`. Local automated execution remains
   capped at 128 seeds and should normally use substantially fewer. A justified
   large research run may be launched autonomously on the designated GCP host
   through `tools/agent/gcp_benchmark.py`; its explicit `--gcp-research` mode
   has no numeric seed ceiling and does not require a further seed-count
   approval step. Choose the smallest sample that answers the question.
   Before launch state the hypothesis, baseline/treatment, seed regime, budget,
   fair-vs-known-RNG regime, model/configuration provenance, intended N, and
   decision rule.
5. Separate implementation correctness from scientific interpretation. Record
   raw commands and results, update `EXPERIMENTS.md` or its current ledger shard
   when a benchmarked idea is run, and finish substantial cycles with a concise
   ELI5 conclusion. After implementation review passes, freeze the reviewed
   commit SHA before any expensive scientific run.

Route durable outputs without duplication:

- raw evidence → experiment ledger and evidence artifact;
- current research status → `evaluation/current-research.md`;
- qualified new default → `evaluation/current-baselines.md`;
- stable implementation fact → relevant architecture, behavior, or operations
  KB page.

`AGENTS.md` remains authoritative for project policy; this skill is a reusable
procedure, not a replacement for that file.
