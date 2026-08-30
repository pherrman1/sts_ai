#!/usr/bin/env python3
"""Small, deterministic, model-agnostic coding-agent evaluation harness."""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "evals" / "coding_agent" / "tasks"
RUNTIME = ROOT / ".agent-eval"
REQUIRED = {
    "schema_version", "id", "version", "title", "prompt_file", "setup_patch",
    "timeout_seconds", "allowed_changed_paths", "forbidden_changed_paths", "grader",
}


class EvalError(Exception):
    pass


SAFE_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def safe_rel(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise EvalError(f"{label} must be a non-empty relative POSIX path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise EvalError(f"unsafe {label}: {value!r}")
    return path


def load_tasks() -> dict[str, dict]:
    tasks: dict[str, dict] = {}
    if not TASKS.is_dir():
        raise EvalError(f"task directory missing: {TASKS}")
    for manifest_path in sorted(TASKS.glob("*/task.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvalError(f"invalid manifest {manifest_path}: {exc}") from exc
        if not isinstance(manifest, dict) or set(manifest) != REQUIRED:
            raise EvalError(f"manifest {manifest_path} has unknown or missing fields")
        task_id = manifest["id"]
        if not isinstance(task_id, str) or task_id != manifest_path.parent.name or task_id in tasks:
            raise EvalError(f"invalid or duplicate task id: {task_id!r}")
        if manifest["schema_version"] != 1 or not isinstance(manifest["version"], int):
            raise EvalError(f"unsupported schema/version in {manifest_path}")
        if not isinstance(manifest["timeout_seconds"], (int, float)) or manifest["timeout_seconds"] <= 0:
            raise EvalError(f"invalid timeout in {manifest_path}")
        for key in ("allowed_changed_paths", "forbidden_changed_paths"):
            if not isinstance(manifest[key], list) or not all(isinstance(x, str) and x for x in manifest[key]):
                raise EvalError(f"invalid {key} in {manifest_path}")
        for key in ("prompt_file", "setup_patch", "grader"):
            rel = safe_rel(manifest[key], key)
            if not (manifest_path.parent / rel).is_file():
                raise EvalError(f"missing {key} for {task_id}: {rel}")
        tasks[task_id] = manifest
    if len(tasks) != 4:
        raise EvalError(f"expected exactly four tasks, found {len(tasks)}")
    return tasks


def task_dir(task_id: str) -> Path:
    tasks = load_tasks()
    if task_id not in tasks:
        raise EvalError(f"unknown task: {task_id}")
    return TASKS / task_id


def run(cmd: list[str], cwd: Path, timeout: float, *, check: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise EvalError(f"command timed out after {timeout}s: {' '.join(cmd)}") from exc
    if check and result.returncode:
        raise EvalError(f"command failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr[-2000:]}")
    return result


def tracked_export(destination: Path) -> None:
    if not destination.is_dir() or any(destination.iterdir()):
        raise EvalError(f"export destination is not empty: {destination}")
    archive = subprocess.run(["git", "archive", "HEAD"], cwd=ROOT, capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(destination)], input=archive, check=True)
    # Git archives contain submodule gitlinks but not their contents. Materialize
    # the checked-out dependency source without copying its nested Git metadata.
    for name in ("json", "pybind11"):
        source = ROOT / name
        if source.is_dir():
            target = destination / name
            if target.exists() and target.is_dir():
                shutil.rmtree(target)
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git"))


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd, 30, check=check)


def prepare(task_id: str, skill_file_value: str | None = None, skill_name: str | None = None) -> dict:
    if (skill_file_value is None) != (skill_name is None):
        raise EvalError("--skill-file and --skill-name must be provided together")
    skill_file = None
    skill_sha256 = None
    if skill_file_value is not None:
        skill_file = Path(skill_file_value).expanduser().resolve()
        if not skill_file.is_file() or skill_file.is_symlink():
            raise EvalError(f"skill source must be an existing regular file: {skill_file_value}")
        if not SAFE_SKILL_NAME.fullmatch(skill_name or ""):
            raise EvalError(f"unsafe skill name: {skill_name!r}")
        skill_sha256 = hashlib.sha256(skill_file.read_bytes()).hexdigest()
    manifest = load_tasks()[task_id]
    source = task_dir(task_id)
    RUNTIME.joinpath("work").mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=f"{task_id}-", dir=RUNTIME / "work"))
    tracked_export(workspace)
    git(workspace, "init", "-q")
    git(workspace, "config", "user.email", "agent-eval@example.invalid")
    git(workspace, "config", "user.name", "agent-eval")
    git(workspace, "add", "-A")
    git(workspace, "commit", "-qm", f"candidate baseline: {task_id}")
    patch = source / safe_rel(manifest["setup_patch"], "setup_patch")
    applied = subprocess.run(["git", "apply", "--unidiff-zero", "--whitespace=nowarn", str(patch)], cwd=workspace, text=True, capture_output=True)
    if applied.returncode:
        raise EvalError(f"setup patch failed for {task_id}: {applied.stderr}")
    if not git(workspace, "diff", "--quiet", check=False).returncode:
        raise EvalError(f"setup patch made no repository change for {task_id}")
    shutil.rmtree(workspace / "evals", ignore_errors=True)
    if skill_file is not None:
        target = workspace / ".agents" / "skills" / skill_name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(skill_file, target)
    git(workspace, "add", "-A")
    git(workspace, "commit", "--amend", "-qm", f"candidate baseline: {task_id}")
    status = git(workspace, "status", "--short").stdout
    if status:
        raise EvalError(f"prepared candidate is not clean: {status}")
    prompt = (source / safe_rel(manifest["prompt_file"], "prompt_file")).read_text(encoding="utf-8")
    prepared = {"task_id": task_id, "workspace": str(workspace), "prompt": prompt, "baseline_commit": git(workspace, "rev-parse", "HEAD").stdout.strip()}
    if skill_file is not None:
        prepared.update({
            "prompt": f"Use the ${skill_name} skill at .agents/skills/{skill_name}/SKILL.md for this task.\n\n{prompt}",
            "skill_name": skill_name,
            "skill_sha256": skill_sha256,
        })
    return prepared


def changed_files(workspace: Path) -> list[str]:
    names = git(workspace, "diff", "--name-only", "HEAD", check=False).stdout.splitlines()
    names += git(workspace, "ls-files", "--others", "--exclude-standard", check=False).stdout.splitlines()
    return sorted({name for name in names if not name.startswith(".agent-eval-build/")})


def in_scope(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def environment() -> dict[str, object]:
    compiler = shutil.which("g++")
    compiler_version = "unavailable"
    if compiler:
        compiler_version = subprocess.run([compiler, "--version"], text=True, capture_output=True).stdout.splitlines()[0]
    return {"OS": platform.system(), "architecture": platform.machine(), "CPU_count": os.cpu_count(), "Python": platform.python_version(), "compiler": compiler_version}


def grade(task_id: str, workspace_value: str, labels: dict[str, str]) -> tuple[int, dict]:
    started = time.monotonic()
    manifest = load_tasks()[task_id]
    workspace = Path(workspace_value).resolve()
    runtime_root = (RUNTIME / "work").resolve()
    if runtime_root not in workspace.parents or not (workspace / ".git").exists():
        raise EvalError("workspace must be a prepared child of .agent-eval/work")
    baseline = git(workspace, "rev-parse", "HEAD").stdout.strip()
    files = changed_files(workspace)
    checks: list[dict] = []
    for path in files:
        if in_scope(path, manifest["forbidden_changed_paths"]):
            checks.append({"name": "changed-path-policy", "passed": False, "detail": f"forbidden path changed: {path}"})
        elif not in_scope(path, manifest["allowed_changed_paths"]):
            checks.append({"name": "changed-path-policy", "passed": False, "detail": f"path outside allowlist: {path}"})
    if not files:
        checks.append({"name": "changed-path-policy", "passed": True, "detail": "no agent changes"})
    grader = task_dir(task_id) / safe_rel(manifest["grader"], "grader")
    result = run([sys.executable, str(grader), str(workspace)], workspace, float(manifest["timeout_seconds"]))
    if result.stdout.strip():
        try:
            checks.extend(json.loads(result.stdout).get("checks", []))
        except json.JSONDecodeError as exc:
            raise EvalError(f"grader returned invalid JSON: {exc}") from exc
    elif result.returncode == 0:
        raise EvalError("grader returned no JSON")
    passed = result.returncode == 0 and all(check.get("passed", False) for check in checks)
    diff = git(workspace, "diff", "HEAD", check=False).stdout.encode() + "\0".join(files).encode()
    record = {"schema_version": 1, "task_id": task_id, "task_version": manifest["version"], "result": "PASS" if passed else "FAIL", "checks": checks, "changed_files": files, "changed_line_count": len(git(workspace, "diff", "--numstat", "HEAD", check=False).stdout.splitlines()), "duration_seconds": round(time.monotonic() - started, 3), "baseline_commit": baseline, "candidate_commit": baseline, "diff_hash": hashlib.sha256(diff).hexdigest(), "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "environment": environment(), "labels": {k: v for k, v in labels.items() if v}}
    return (0 if passed else 1), record


def self_test() -> int:
    for task_id in load_tasks():
        prepared = prepare(task_id)
        code, record = grade(task_id, prepared["workspace"], {})
        if code == 0:
            raise EvalError(f"broken fixture unexpectedly passed: {task_id}")
        workspace = Path(prepared["workspace"])
        patch = task_dir(task_id) / "setup.patch"
        subprocess.run(["git", "apply", "--unidiff-zero", "-R", str(patch)], cwd=workspace, check=True)
        code, restored = grade(task_id, str(workspace), {})
        if code != 0:
            raise EvalError(f"restored oracle failed: {task_id}: {json.dumps(restored)}")
        second_code, second = grade(task_id, str(workspace), {})
        if second_code != code or [c["passed"] for c in second["checks"]] != [c["passed"] for c in restored["checks"]]:
            raise EvalError(f"non-reproducible result: {task_id}")
        print(json.dumps({"task_id": task_id, "broken_fixture": record["result"], "restored": restored["result"]}, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    p = sub.add_parser("prepare"); p.add_argument("task_id"); p.add_argument("--skill-file"); p.add_argument("--skill-name")
    p = sub.add_parser("grade"); p.add_argument("task_id"); p.add_argument("workspace"); p.add_argument("--agent", default=""); p.add_argument("--model", default=""); p.add_argument("--configuration", default="")
    sub.add_parser("self-test")
    args = parser.parse_args()
    try:
        if args.command == "list":
            for task_id, manifest in load_tasks().items(): print(json.dumps({"id": task_id, "title": manifest["title"], "version": manifest["version"]}, sort_keys=True))
            return 0
        if args.command == "prepare":
            print(json.dumps(prepare(args.task_id, args.skill_file, args.skill_name), indent=2, sort_keys=True)); return 0
        if args.command == "self-test": return self_test()
        code, record = grade(args.task_id, args.workspace, {"agent": args.agent, "model": args.model, "configuration": args.configuration})
        print(json.dumps(record, indent=2, sort_keys=True))
        RUNTIME.joinpath("results").mkdir(parents=True, exist_ok=True)
        (RUNTIME / "results" / f"{args.task_id}-{int(time.time())}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return code
    except EvalError as exc:
        print(json.dumps({"schema_version": 1, "result": "INFRA_ERROR", "error": str(exc), "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "environment": environment()}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
