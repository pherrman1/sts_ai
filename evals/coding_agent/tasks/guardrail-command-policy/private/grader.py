#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
script = workspace / "tools/agent/cline_guardrails.py"

def blocked(command):
    payload = {"hookName": "PreToolUse", "branch": "feature", "preToolUse": {"toolName": "execute_command", "parameters": {"command": command}}}
    result = subprocess.run([sys.executable, str(script)], input=json.dumps(payload), text=True, capture_output=True, cwd=workspace)
    return json.loads(result.stdout)["cancel"]

checks = [
    {"name": "option-prefixed-destructive-git", "passed": blocked("git --namespace=agent reset --hard HEAD"), "detail": "namespaced hard reset must be blocked"},
    {"name": "safe-git-neighbor", "passed": not blocked("git --namespace=agent status --short"), "detail": "namespaced status remains allowed"},
    {"name": "wrapper-destructive-git", "passed": blocked("env GIT_OPTIONAL_LOCKS=0 git --namespace=agent clean -fd"), "detail": "wrapper form remains blocked"},
    {"name": "existing-guardrail-tests", "passed": subprocess.run([sys.executable, "-m", "unittest", "tests.agent.test_cline_guardrails.PreToolUseTests"], cwd=workspace, capture_output=True).returncode == 0, "detail": "public command-policy guardrail tests"},
]
print(json.dumps({"checks": checks}))
raise SystemExit(0 if all(c["passed"] for c in checks) else 1)