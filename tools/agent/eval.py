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
import stat
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "evals" / "coding_agent" / "tasks"
RUNTIME = ROOT / ".agent-eval"
CACHE_VERSION = 3
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


def export_identity() -> dict[str, object]:
    head = git(ROOT, "rev-parse", "HEAD").stdout.strip()
    submodules: dict[str, str] = {}
    for name in ("json", "pybind11"):
        entry = git(ROOT, "ls-tree", "HEAD", "--", name).stdout.split()
        if len(entry) != 4 or entry[0] != "160000" or entry[1] != "commit":
            raise EvalError(f"missing or invalid submodule gitlink: {name}")
        revision = entry[2]
        source = ROOT / name
        if not source.is_dir() or git(source, "rev-parse", "HEAD").stdout.strip() != revision:
            raise EvalError(f"submodule is not checked out at pinned revision: {name}={revision}")
        submodules[name] = revision
    return {"version": CACHE_VERSION, "head": head, "submodules": submodules}


def cache_path(identity: dict[str, object]) -> Path:
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return RUNTIME / "cache" / hashlib.sha256(encoded).hexdigest()[:24]


def extract_archive(repository: Path, revision: str, destination: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", revision], cwd=repository, capture_output=True, check=True,
    ).stdout
    subprocess.run(["tar", "-x", "-C", str(destination)], input=archive, check=True)


def build_public_export(destination: Path, identity: dict[str, object]) -> None:
    if not destination.is_dir() or any(destination.iterdir()):
        raise EvalError(f"export destination is not empty: {destination}")
    extract_archive(ROOT, str(identity["head"]), destination)
    # Git archives contain submodule gitlinks but not their contents. Materialize
    # each exact pinned dependency revision without nested Git metadata.
    for name in ("json", "pybind11"):
        source = ROOT / name
        target = destination / name
        if target.exists() and target.is_dir():
            shutil.rmtree(target)
        target.mkdir()
        extract_archive(source, str(identity["submodules"][name]), target)
    remove_hidden_data(destination)


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode()
        if path.is_symlink():
            digest.update(b"L\0" + relative + b"\0" + os.fsencode(os.readlink(path)) + b"\0")
        elif path.is_file():
            executable = b"X" if path.stat().st_mode & stat.S_IXUSR else b"-"
            digest.update(b"F" + executable + b"\0" + relative + b"\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
    return digest.hexdigest()


def _tracked_export(destination: Path) -> None:
    if not destination.is_dir() or any(destination.iterdir()):
        raise EvalError(f"export destination is not empty: {destination}")
    identity = export_identity()
    entry = cache_path(identity)
    tree = entry / "tree"
    manifest = entry / "manifest.json"
    if entry.exists():
        try:
            recorded = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise EvalError(f"invalid tracked-export cache entry: {entry}: {exc}") from exc
        expected = {"identity": identity, "tree_sha256": tree_sha256(tree)} if tree.is_dir() else None
        if recorded != expected or (tree / "evals").exists():
            raise EvalError(f"tracked-export cache identity/content mismatch: {entry}")
    else:
        entry.parent.mkdir(parents=True, exist_ok=True)
        temporary = entry.parent / f".tmp-{uuid.uuid4().hex[:12]}"
        try:
            temporary.mkdir()
            temporary_tree = temporary / "tree"
            temporary_tree.mkdir()
            build_public_export(temporary_tree, identity)
            record = {"identity": identity, "tree_sha256": tree_sha256(temporary_tree)}
            (temporary / "manifest.json").write_text(
                json.dumps(record, sort_keys=True) + "\n", encoding="utf-8",
            )
            try:
                temporary.rename(entry)
            except FileExistsError:
                shutil.rmtree(temporary)
                return tracked_export(destination)
            recorded = record
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
    archive = subprocess.run(
        ["tar", "-cf", "-", "-C", str(tree), "."], capture_output=True, check=True,
    ).stdout
    subprocess.run(["tar", "-xf", "-", "-C", str(destination)], input=archive, check=True)
    if tree_sha256(destination) != recorded["tree_sha256"]:
        raise EvalError(f"tracked-export cache changed during materialization: {entry}")


def tracked_export(destination: Path) -> None:
    try:
        _tracked_export(destination)
    except EvalError:
        raise
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvalError(f"tracked export failed: {exc}") from exc


def git(cwd: Path, *args: str, check: bool = True, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd, timeout, check=check)


def apply_setup_patch(workspace: Path, patch: Path, task_id: str) -> None:
    patch_bytes = patch.read_bytes().replace(b"\r\n", b"\n")
    stats = subprocess.run(
        ["git", "apply", "--numstat", "-z", "-"],
        cwd=workspace, input=patch_bytes, capture_output=True,
    )
    entries = [entry for entry in stats.stdout.split(b"\0") if entry]
    if stats.returncode or not entries:
        raise EvalError(f"setup patch made no repository change for {task_id}")
    targets: list[Path] = []
    for entry in entries:
        parts = entry.split(b"\t", 2)
        if len(parts) != 3:
            raise EvalError(f"invalid setup patch statistics for {task_id}")
        targets.append(workspace / safe_rel(os.fsdecode(parts[2]), "setup patch path"))

    def state(path: Path) -> tuple[str, bytes | str] | None:
        try:
            if path.is_symlink():
                return ("symlink", os.readlink(path))
            if path.is_file():
                return ("file", hashlib.sha256(path.read_bytes()).digest())
            if not path.exists():
                return None
        except OSError as exc:
            raise EvalError(
                f"failed to inspect setup patch target for {task_id}: {path}: {exc}"
            ) from exc
        raise EvalError(f"setup patch target is not a file: {path}")

    before = [state(target) for target in targets]
    applied = subprocess.run(
        ["git", "apply", "--unidiff-zero", "--whitespace=nowarn", "-"],
        cwd=workspace, input=patch_bytes, capture_output=True,
    )
    if applied.returncode:
        raise EvalError(f"setup patch failed for {task_id}: {applied.stderr.decode(errors='replace')}")
    if before == [state(target) for target in targets]:
        raise EvalError(f"setup patch made no repository change for {task_id}")


def remove_hidden_data(workspace: Path) -> None:
    hidden = workspace / "evals"
    if hidden.exists():
        try:
            shutil.rmtree(hidden)
        except OSError as exc:
            raise EvalError(f"failed to remove hidden evaluator data: {exc}") from exc
    if hidden.exists():
        raise EvalError(f"hidden evaluator data remains after removal: {hidden}")


def prepared_record_path(workspace: Path) -> Path:
    return RUNTIME / "prepared" / f"{workspace.name}.json"


def create_workspace(prefix: str) -> Path:
    parent = RUNTIME / "work"
    parent.mkdir(parents=True, exist_ok=True)
    unique = uuid.uuid4().hex
    name = f"{prefix}{unique}" if os.name != "nt" else f"{prefix[:8]}{unique[:12]}"
    workspace = parent / name
    workspace.mkdir()
    return workspace


def record_prepared_baseline(task_id: str, workspace: Path, baseline_commit: str) -> None:
    path = prepared_record_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise EvalError(f"prepared baseline record already exists: {path}")
    path.write_text(json.dumps({
        "task_id": task_id,
        "workspace": str(workspace.resolve()),
        "baseline_commit": baseline_commit,
    }, sort_keys=True) + "\n", encoding="utf-8")


def load_prepared_baseline(task_id: str, workspace: Path) -> str:
    path = prepared_record_path(workspace)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalError(f"missing or invalid prepared baseline record: {path}") from exc
    expected = {"task_id", "workspace", "baseline_commit"}
    if not isinstance(record, dict) or set(record) != expected:
        raise EvalError(f"invalid prepared baseline record schema: {path}")
    if record["task_id"] != task_id or record["workspace"] != str(workspace):
        raise EvalError("prepared baseline record does not match task/workspace")
    baseline = record["baseline_commit"]
    if not isinstance(baseline, str) or not re.fullmatch(r"[0-9a-f]{40}", baseline):
        raise EvalError("prepared baseline record has invalid commit SHA")
    if git(workspace, "cat-file", "-e", f"{baseline}^{{commit}}", check=False).returncode:
        raise EvalError("prepared baseline commit is missing from candidate repository")
    return baseline


def prepare(task_id: str, skill_file_value: str | None = None, skill_name: str | None = None) -> dict:
    phase_started = time.monotonic()
    phases: dict[str, float] = {}

    def phase(name: str) -> None:
        nonlocal phase_started
        now = time.monotonic()
        phases[name] = round(now - phase_started, 6)
        phase_started = now

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
    workspace = create_workspace(f"{task_id}-")
    tracked_export(workspace)
    phase("tracked_export")
    git(workspace, "init", "-q")
    git(workspace, "config", "user.email", "agent-eval@example.invalid")
    git(workspace, "config", "user.name", "agent-eval")
    patch = source / safe_rel(manifest["setup_patch"], "setup_patch")
    apply_setup_patch(workspace, patch, task_id)
    remove_hidden_data(workspace)
    if skill_file is not None:
        target = workspace / ".agents" / "skills" / skill_name / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(skill_file, target)
    phase("mutation_and_overlay")
    # Stage only after hidden evaluator data is gone. Even staging the original
    # export would write recoverable private blobs into .git/objects. The empty
    # repository is initialized earlier only to isolate patch application from
    # the evaluator source checkout.
    git(workspace, "add", "-A", timeout=120)
    git(workspace, "commit", "-qm", f"candidate baseline: {task_id}")
    phase("stage_and_commit")
    status = git(workspace, "status", "--short").stdout
    if status:
        raise EvalError(f"prepared candidate is not clean: {status}")
    baseline_commit = git(workspace, "rev-parse", "HEAD").stdout.strip()
    record_prepared_baseline(task_id, workspace, baseline_commit)
    prompt = (source / safe_rel(manifest["prompt_file"], "prompt_file")).read_text(encoding="utf-8")
    prepared = {"task_id": task_id, "workspace": str(workspace), "prompt": prompt, "baseline_commit": baseline_commit}
    if skill_file is not None:
        prepared.update({
            "prompt": f"Use the ${skill_name} skill at .agents/skills/{skill_name}/SKILL.md for this task.\n\n{prompt}",
            "skill_name": skill_name,
            "skill_sha256": skill_sha256,
        })
    if os.environ.get("STS_AGENT_EVAL_TIMINGS") == "1":
        print(json.dumps({"prepare_phases_seconds": phases}, sort_keys=True), file=sys.stderr)
    return prepared


def changed_files(workspace: Path, baseline_commit: str) -> list[str]:
    names = git(workspace, "log", "-m", "--no-renames", "--format=", "--name-only", f"{baseline_commit}..HEAD", check=False).stdout.splitlines()
    names += git(workspace, "diff", "--no-renames", "--cached", "--name-only", "HEAD", check=False).stdout.splitlines()
    names += git(workspace, "diff", "--no-renames", "--name-only", check=False).stdout.splitlines()
    names += git(workspace, "ls-files", "--others", "--exclude-standard", check=False).stdout.splitlines()
    return sorted({name for name in names if not name.startswith(".agent-eval-build/")})


def candidate_diff(workspace: Path, baseline_commit: str, files: list[str]) -> bytes:
    parts = [
        git(workspace, "log", "-m", "--no-renames", "--format=commit %H", "-p", "--binary", f"{baseline_commit}..HEAD", check=False).stdout.encode(),
        git(workspace, "diff", "--no-renames", "--cached", "--binary", "HEAD", check=False).stdout.encode(),
        git(workspace, "diff", "--no-renames", "--binary", check=False).stdout.encode(),
    ]
    untracked = set(git(workspace, "ls-files", "--others", "--exclude-standard", check=False).stdout.splitlines())
    for name in files:
        parts.append(name.encode() + b"\0")
        if name in untracked:
            try:
                parts.append((workspace / name).read_bytes())
            except OSError as exc:
                raise EvalError(f"cannot read untracked candidate file: {name}") from exc
    return b"\0".join(parts)


def in_scope(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def environment() -> dict[str, object]:
    compiler = shutil.which("g++")
    compiler_version = "unavailable"
    if compiler:
        compiler_version = subprocess.run([compiler, "--version"], text=True, capture_output=True).stdout.splitlines()[0]
    return {"OS": platform.system(), "architecture": platform.machine(), "CPU_count": os.cpu_count(), "Python": platform.python_version(), "compiler": compiler_version}


def grader_command(grader: Path, workspace: Path) -> list[str]:
    if os.name != "nt":
        return [sys.executable, str(grader), str(workspace)]
    command = 'python3 "$(wslpath -a "$1")" "$(wslpath -a "$2")"'
    return ["wsl", "-e", "bash", "-lc", command, "_", str(grader), str(workspace)]


def grade(task_id: str, workspace_value: str, labels: dict[str, str]) -> tuple[int, dict]:
    started = time.monotonic()
    manifest = load_tasks()[task_id]
    workspace = Path(workspace_value).resolve()
    runtime_root = (RUNTIME / "work").resolve()
    if runtime_root not in workspace.parents or not (workspace / ".git").exists():
        raise EvalError("workspace must be a prepared child of .agent-eval/work")
    baseline = load_prepared_baseline(task_id, workspace)
    candidate = git(workspace, "rev-parse", "HEAD").stdout.strip()
    if git(workspace, "merge-base", "--is-ancestor", baseline, candidate, check=False).returncode:
        raise EvalError("candidate HEAD is not a descendant of the prepared baseline")
    files = changed_files(workspace, baseline)
    checks: list[dict] = []
    for path in files:
        if in_scope(path, manifest["forbidden_changed_paths"]):
            checks.append({"name": "changed-path-policy", "passed": False, "detail": f"forbidden path changed: {path}"})
        elif not in_scope(path, manifest["allowed_changed_paths"]):
            checks.append({"name": "changed-path-policy", "passed": False, "detail": f"path outside allowlist: {path}"})
    if not files:
        checks.append({"name": "changed-path-policy", "passed": True, "detail": "no agent changes"})
    grader = task_dir(task_id) / safe_rel(manifest["grader"], "grader")
    result = run(grader_command(grader, workspace), workspace, float(manifest["timeout_seconds"]))
    if result.stdout.strip():
        try:
            checks.extend(json.loads(result.stdout).get("checks", []))
        except json.JSONDecodeError as exc:
            raise EvalError(f"grader returned invalid JSON: {exc}") from exc
    elif result.returncode == 0:
        raise EvalError("grader returned no JSON")
    passed = result.returncode == 0 and all(check.get("passed", False) for check in checks)
    diff = candidate_diff(workspace, baseline, files)
    committed_numstat = git(workspace, "log", "-m", "--no-renames", "--format=", "--numstat", f"{baseline}..HEAD", check=False).stdout.splitlines()
    worktree_numstat = git(workspace, "diff", "--no-renames", "--numstat", "HEAD", check=False).stdout.splitlines()
    record = {"schema_version": 1, "task_id": task_id, "task_version": manifest["version"], "result": "PASS" if passed else "FAIL", "checks": checks, "changed_files": files, "changed_line_count": len([line for line in committed_numstat + worktree_numstat if line]), "duration_seconds": round(time.monotonic() - started, 3), "baseline_commit": baseline, "candidate_commit": candidate, "diff_hash": hashlib.sha256(diff).hexdigest(), "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(), "environment": environment(), "labels": {k: v for k, v in labels.items() if v}}
    return (0 if passed else 1), record


def self_test() -> int:
    for task_id in load_tasks():
        prepared = prepare(task_id)
        code, record = grade(task_id, prepared["workspace"], {})
        if code == 0:
            raise EvalError(f"broken fixture unexpectedly passed: {task_id}")
        workspace = Path(prepared["workspace"])
        patch = task_dir(task_id) / "setup.patch"
        patch_bytes = patch.read_bytes().replace(b"\r\n", b"\n")
        subprocess.run(
            ["git", "apply", "--unidiff-zero", "-R", "-"],
            cwd=workspace, input=patch_bytes, check=True,
        )
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
