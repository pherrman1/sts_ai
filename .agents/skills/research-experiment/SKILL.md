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

1. Follow `AGENTS.md`. Before proposing a change, read the maintained pages
   and experiment-ledger entries relevant to the research question, affected
   invariants, and evaluation protocol. Use `docs/knowledge-base/CODE_MAP.md`
   for unfamiliar code or subsystem boundaries; consult
   `docs/knowledge-base/operations/agent-context-and-workflow.md` for handoff,
   Git, and recording procedures as needed.
2. State the hypothesis, baseline, expected evidence, decision rule, and
   constraints before an expensive run. Generate multiple plausible
   explanations when the question is uncertain.
3. Change one conceptual variable at a time where practical. Preserve paired
   common seeds, fair/known-RNG labels, model paths or hashes, simulation
   budgets, and output schema.
4. Use the cheapest meaningful verification first. Route every seed-based
   command through `tools/seed_guard.sh`. Use the smallest justified
   experiment. Larger local runs require explicit authorization; there is no
   fixed numerical ceiling. Before launch record the hypothesis, baseline and
   treatment, exact seed ranges/counts, simulation and resource budgets,
   fair-vs-known-RNG regime, frozen source/model/binary provenance, and decision
   rule.
   Before collecting new data, inventory preserved local and remote artifacts
   and record why each candidate does or does not satisfy the required
   provenance, configuration, sample size, replication, freshness, and state
   constraints. Reuse qualifying evidence; do not silently recollect a
   discovery pool for prospective validation.
   For remote work, distinguish requested, launched, running, and completed
   state. Verify the actual host and environment, effective resource use,
   process progress, failures, output provenance, and observed throughput
   before claiming execution status or an ETA.
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
