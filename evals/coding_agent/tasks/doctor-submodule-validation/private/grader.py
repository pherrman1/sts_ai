#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

workspace = Path(sys.argv[1])
original = workspace / "tools/agent/doctor.sh"
script = Path(tempfile.mkdtemp(prefix="doctor-script-")) / "doctor.sh"
text = original.read_text(encoding="utf-8")
needle = 'submodule_status="$(git -C "$repo_root" submodule status --recursive 2>/dev/null)"'
text = text.replace(needle, 'submodule_status="$FAKE_SUBMODULE_STATUS"')
script.write_text(text, encoding="utf-8")
script.chmod(0o755)

def run(status):
    env = os.environ.copy()
    env["FAKE_SUBMODULE_STATUS"] = status
    return subprocess.run(["bash", str(script)], cwd=workspace, env=env, text=True, capture_output=True)

checks = [
    {"name": "mismatched-submodule-rejected", "passed": run("-deadbeef json").returncode != 0, "detail": "leading '-' status is invalid"},
    {"name": "clean-submodule-accepted", "passed": run(" deadbeef json").returncode == 0, "detail": "leading space status is valid"},
]
print(json.dumps({"checks": checks}))
raise SystemExit(0 if all(c["passed"] for c in checks) else 1)