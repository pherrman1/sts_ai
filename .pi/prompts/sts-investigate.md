---
description: Parallel read-only STS investigation followed by architect synthesis
argument-hint: "<question>"
---
Investigate this STS research/software question:

$@

Use the `subagent` tool with `agentScope: "project"`.

First choose 2-5 genuinely distinct investigation aspects.

For the investigator stage, make EXACTLY ONE `subagent` tool call using
parallel `tasks` mode:

{
  "tasks": [
    {"agent": "investigator", "task": "<aspect 1>"},
    {"agent": "investigator", "task": "<aspect 2>"},
    {"agent": "investigator", "task": "<aspect 3>"},
    {"agent": "investigator", "task": "<aspect 4>"},
    {"agent": "investigator", "task": "<aspect 5>"}
  ],
  "agentScope": "project"
}

Do NOT emit multiple independent `subagent` tool calls in one assistant
response.

Wait for the single combined parallel result before doing anything else.

After the investigator results return, make EXACTLY ONE separate `subagent`
call to the `architect` agent.

Do not automatically retry an investigator batch if the subagent tool fails
or returns no usable output. Report the failure instead.

At the end, summarize for the user:
- strongest finding;
- important uncertainty;
- architect recommendation;
- ELI5 explanation.
