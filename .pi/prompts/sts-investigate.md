---
description: Parallel read-only STS investigation followed by architect synthesis
argument-hint: "<question>"
---
Investigate this STS research/software question:

$@

Use the `subagent` tool with `agentScope: "project"`.

First run 2-3 `investigator` agents in parallel on genuinely distinct aspects
of the question. Choose the aspects from the repository evidence; for ML/search
problems useful divisions often include training/inference parity,
offline/online distribution, actual online model use, search/RNG semantics, and
prior experiment evidence.

All investigators are read-only.

After they finish, run the `architect` agent with `agentScope: "project"`.
Give the architect:
- the original question;
- the investigator findings;
- instructions to inspect any missing evidence itself;
- instructions to synthesize a single conclusion or implementation plan.

Do not invoke the implementer. This command is investigation/planning only.

At the end, summarize for the user:
- strongest finding;
- important uncertainty;
- architect recommendation;
- ELI5 explanation.
