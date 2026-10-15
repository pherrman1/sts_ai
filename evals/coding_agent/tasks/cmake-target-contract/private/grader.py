#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

workspace = Path(sys.argv[1])
build = workspace / ".agent-eval-build"
configure = subprocess.run(["cmake", "-S", ".", "-B", str(build), "-DCMAKE_BUILD_TYPE=Release"], cwd=workspace, text=True, capture_output=True)
checks = [{"name": "configure", "passed": configure.returncode == 0, "detail": configure.stderr[-1000:]}]
if configure.returncode == 0:
    build_result = subprocess.run(["cmake", "--build", str(build), "--target", "parity_test", "-j2"], cwd=workspace, text=True, capture_output=True)
    checks.append({"name": "parity-test-target-builds", "passed": build_result.returncode == 0, "detail": build_result.stderr[-1000:]})
    checks.append({"name": "parity-test-output-exists", "passed": (build / "parity_test").is_file(), "detail": str(build / "parity_test")})
print(json.dumps({"checks": checks}))
raise SystemExit(0 if all(c["passed"] for c in checks) else 1)