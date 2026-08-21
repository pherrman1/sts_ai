---
name: research-experiment
description: Use for hypothesis-driven research experiments, benchmark proposals, and evidence-based interpretation in this repository.
---

# Research experiment workflow

Use this skill for research questions, experiment proposals, and benchmark
interpretation in this repository.

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
   ELI5 conclusion.

`AGENTS.md` remains authoritative for project policy; this skill is a reusable
procedure, not a replacement for that file.
