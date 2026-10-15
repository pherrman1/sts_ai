#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
build = workspace / ".agent-eval-build"
checks = []
configured = subprocess.run(["cmake", "-S", ".", "-B", str(build), "-DCMAKE_BUILD_TYPE=Debug"], cwd=workspace, text=True, capture_output=True)
checks.append({"name": "configure", "passed": configured.returncode == 0, "detail": configured.stderr[-1000:]})
if configured.returncode == 0:
    built = subprocess.run(["cmake", "--build", str(build), "--target", "unit-test", "-j2"], cwd=workspace, text=True, capture_output=True)
    checks.append({"name": "unit-test-build", "passed": built.returncode == 0, "detail": built.stderr[-1000:]})
    if built.returncode == 0:
        for name in ("simhealth_gamble_empty_hand", "simhealth_selection_failure"):
            result = subprocess.run([str(build / "test"), name], cwd=workspace, text=True, capture_output=True)
            checks.append({"name": name, "passed": result.returncode == 0 and " PASS" in result.stdout, "detail": result.stdout[-500:] + result.stderr[-500:]})
print(json.dumps({"checks": checks}))
raise SystemExit(0 if checks and all(c["passed"] for c in checks) else 1)