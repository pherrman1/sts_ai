# Long-running commands

For benchmark, test, build, or verification commands that may exceed 30 seconds,
wrap them with an explicit shell timeout appropriate to the task.

Defaults:
- builds/tests: `timeout 10m`
- targeted seed runs: `timeout 15m`
- longer approved experiments: use the experiment-specific limit

Do not treat a Cline terminal/tool timeout as evidence that the underlying
process failed. Before rerunning a long command, check whether the process is
still running and inspect its output/result files.

For sts_ai seed-based verification, preserve the project's seed-budget rules
from AGENTS.md.
