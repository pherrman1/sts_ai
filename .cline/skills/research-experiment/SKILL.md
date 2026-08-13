---
name: research-experiment
description: Use for hypothesis-driven research experiments, benchmark proposals, and evidence-based interpretation in this repository.
---

# Research experiment workflow

Use this skill for research questions, experiment proposals, and benchmark
interpretation in this repository.

1. Read `AGENTS.md`, `docs/knowledge-base/CODE_MAP.md`, the relevant maintained
   knowledge-base page, and relevant experiment-ledger entries before proposing
   a change.
2. State the hypothesis, baseline, expected evidence, decision rule, and
   constraints before an expensive run. Generate multiple plausible
   explanations when the question is uncertain.
3. Change one conceptual variable at a time where practical. Preserve paired
   common seeds, fair/known-RNG labels, model paths or hashes, simulation
   budgets, and output schema.
4. Use the cheapest meaningful verification first. Route seed-based commands
   through `tools/seed_guard.sh`; automated agent runs must not exceed 128
   seeds and should normally use substantially fewer.
5. Separate implementation correctness from scientific interpretation. Record
   raw commands and results, update `EXPERIMENTS.md` or its current ledger shard
   when a benchmarked idea is run, and finish substantial cycles with a concise
   ELI5 conclusion.

`AGENTS.md` remains authoritative for project policy; this skill is a reusable
procedure, not a replacement for that file.