#!/usr/bin/env python3
"""Stdlib-only Cline safety policy and cheap completion validation."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EDIT_TOOLS = {"write_to_file", "replace_in_file", "apply_patch", "apply_diff", "write_file", "replace_content", "replace_in_files", "editor", "serena__replace_content", "serena__replace_symbol_body", "serena__replace_in_files", "serena__insert_after_symbol", "serena__insert_before_symbol", "serena__rename_symbol", "serena__safe_delete_symbol"}
MUTATING_SERENA = {x for x in EDIT_TOOLS if x.startswith("serena__")}
COMPLETION_TOOLS = {"attempt_completion", "submit_and_exit"}


def make_output(cancel=False, error="", context=""):
    result = {"cancel": bool(cancel)}
    if error:
        result["errorMessage"] = error
    if context:
        result["contextModification"] = context
    return result


def git_path(name):
    try:
        value = subprocess.check_output(["git", "rev-parse", "--git-path", name], cwd=ROOT, text=True).strip()
        return Path(value) if os.path.isabs(value) else (ROOT / value).resolve()
    except (OSError, subprocess.CalledProcessError):
        return ROOT / ".git" / name


BASELINE_PATH = git_path("cline-task-baseline.json")


def git_branch():
    return os.environ.get("CLINE_GUARD_BRANCH", subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, text=True, capture_output=True).stdout.strip())


def git_head():
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False).stdout.strip()


def commands(parameters):
    if not isinstance(parameters, dict):
        return []
    result = []
    for key in ("command", "cmd", "commands"):
        value = parameters.get(key)
        if isinstance(value, str):
            result.append(value)
        elif isinstance(value, list):
            result.extend(str(item.get("command", item)) if isinstance(item, dict) else str(item) for item in value)
    return result


def tokens(command):
    command = command.replace("\n", " ; ")
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return command.split()


def segments(command):
    result, current = [], []
    for token in tokens(command):
        if token in {";", "&&", "||", "|", "&"}:
            if current:
                result.append(current)
                current = []
        else:
            current.append(token)
    if current:
        result.append(current)
    return result


def base(value):
    return value.replace("\\", "/").rstrip("/").split("/")[-1].lower()


def git_args(parts):
    try:
        index = next(i for i, value in enumerate(parts) if base(value) == "git")
    except StopIteration:
        return None
    args = parts[index + 1:]
    options = {"-c", "-C", "--git-dir", "--work-tree", "--namespace", "--config-env"}
    while args and (args[0] in options or any(args[0].startswith(option + "=") for option in options)):
        args = args[2:] if args[0] in options else args[1:]
    return args


def pushes_main(args):
    for value in args[1:]:
        value = value.lstrip("+")
        destination = value.split(":", 1)[1] if ":" in value else value
        if destination in {"main", "refs/heads/main"}:
            return True
    return False


def guarded(parts, target):
    return any(base(parts[i]) == target and any(base(previous) == "seed_guard.sh" for previous in parts[:i]) for i in range(len(parts)))


def check_command(command, branch, depth=0):
    if depth > 1:
        return None
    for parts in segments(command):
        lower = [value.lower() for value in parts]
        if any(value in {"sudo", "doas", "su"} for value in lower):
            return "Privilege escalation is blocked. Perform the operation manually."
        if any(value in {"pkill", "killall"} for value in lower) or (lower and lower[0] == "kill" and not (len(parts) == 2 and parts[1].isdigit())):
            return "Broad process termination is blocked. Resolve and stop processes manually."
        for shell in ("bash", "sh"):
            if shell in lower and "-c" in lower:
                index = lower.index("-c") + 1
                if index < len(parts):
                    reason = check_command(parts[index], branch, depth + 1)
                    if reason:
                        return reason
        if any(base(value) == "one_combat" for value in parts) and not guarded(parts, "one_combat"):
            return "Direct one_combat execution is blocked; route it through tools/seed_guard.sh."
        if any(base(value) == "check_replay.py" for value in parts) and not guarded(parts, "check_replay.py"):
            return "Direct check_replay.py execution is blocked; route it through tools/seed_guard.sh."
        args = git_args(parts)
        if args:
            subcommand = args[0]
            if subcommand == "reset" and "--hard" in args:
                return "git reset --hard is blocked."
            if subcommand == "clean" and any(value == "--force" or (value.startswith("-") and "f" in value) for value in args[1:]):
                return "Destructive git clean is blocked."
            if subcommand == "branch" and any(value in {"-d", "-D", "--delete"} for value in args[1:]):
                return "Branch deletion is blocked."
            if subcommand == "push":
                if any(value in {"--force", "-f", "--force-with-lease"} or value.startswith("--force-with-lease=") for value in args[1:]):
                    return "Force push is blocked."
                if pushes_main(args):
                    return "Pushes to main are blocked."
                if branch == "main":
                    return "Plain git push from main is blocked."
            if subcommand in {"checkout", "restore"} and any(value in {".", "--", "--all"} for value in args[1:]):
                return "Broad working-tree discard is blocked."
        if base(parts[0]) in {"rm", "rmdir"} and any("r" in flag for flag in lower[1:] if flag.startswith("-")):
            return "Recursive filesystem deletion is blocked."
    return None


def changed_files(baseline):
    names = []
    specs = []
    if baseline:
        specs.append(["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", f"{baseline}..HEAD"])
    specs.extend([
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB"],
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMRTUXB"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ])
    for spec in specs:
        result = subprocess.run(spec, cwd=ROOT, text=True, capture_output=True, check=False)
        if result.returncode == 0:
            names.extend(result.stdout.splitlines())
    return [ROOT / name for name in dict.fromkeys(names) if name and (ROOT / name).is_file()]


def load_baseline():
    try:
        value = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def validate_changes():
    baseline = load_baseline().get("head")
    checks = [subprocess.run(["git", "diff", "--check", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=False), subprocess.run(["git", "diff", "--cached", "--check"], cwd=ROOT, text=True, capture_output=True, check=False)]
    if any(check.returncode for check in checks):
        return "git diff --check failed; fix whitespace errors before completing.\n" + "".join(check.stdout + check.stderr for check in checks), ""
    changed = changed_files(baseline)
    py = [str(path) for path in changed if path.suffix == ".py"]
    if py:
        result = subprocess.run([sys.executable, "-m", "py_compile", *py], cwd=ROOT, text=True, capture_output=True, check=False)
        if result.returncode:
            return "Python syntax check failed:\n" + (result.stderr or result.stdout), ""
    shell = [str(path) for path in changed if path.suffix == ".sh"]
    if shell and shutil.which("bash"):
        result = subprocess.run(["bash", "-n", *shell], cwd=ROOT, text=True, capture_output=True, check=False)
        if result.returncode:
            return "Shell syntax check failed:\n" + (result.stderr or result.stdout), ""
    for path in (path for path in changed if path.suffix == ".json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return f"JSON syntax check failed for {path.relative_to(ROOT)}: {exc}", ""
    if any(path.suffix in {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".cmake"} or path.name in {"CMakeLists.txt", "CMakePresets.json"} for path in changed):
        return None, "C++/CMake files changed: run focused local verification when useful; the PR Linux GCC check must pass before manual merge. No full build or gameplay benchmark was launched by this hook."
    return None, ""


def handle_pre_tool_use(data):
    pre = data.get("preToolUse") or data.get("pre_tool_use") or {}
    tool = str(pre.get("toolName", pre.get("tool_name", "")))
    params = pre.get("parameters", {})
    generic = params.get("toolName") if isinstance(params, dict) else None
    effective = str(generic or tool)
    branch = str(data.get("branch") or git_branch())
    if branch == "main" and (effective in EDIT_TOOLS or effective in MUTATING_SERENA or (effective.startswith("serena__") and any(word in effective for word in ("replace", "insert", "delete", "rename")))):
        return make_output(True, "Project-file modifications are blocked on main. Create and switch to a feature branch first.")
    if effective in COMPLETION_TOOLS:
        error, context = validate_changes()
        return make_output(bool(error), error, context)
    for command in commands(params):
        reason = check_command(command, branch)
        if reason:
            sys.stderr.write(f"CLINE_GUARD: blocked command {command!r}: {reason}\n")
            return make_output(True, reason)
    return make_output(False)


def main():
    try:
        data = json.load(sys.stdin)
        name = str(data.get("hookName") or data.get("hook_name") or "")
        if name == "TaskStart" or "taskStart" in data or "task_start" in data:
            task = data.get("taskStart") or data.get("task_start") or {}
            task_id = str(data.get("taskId") or data.get("task_id") or task.get("taskId", "unknown"))
            BASELINE_PATH.write_text(json.dumps({"taskId": task_id, "head": git_head(), "branch": git_branch()}) + "\n", encoding="utf-8")
            result = make_output(False)
        elif name == "TaskComplete" or "taskComplete" in data or "task_complete" in data:
            try:
                BASELINE_PATH.unlink()
            except FileNotFoundError:
                pass
            result = make_output(False)
        else:
            result = handle_pre_tool_use(data)
        print(json.dumps(result, separators=(",", ":")))
    except Exception as exc:
        sys.stderr.write(f"CLINE_GUARD_ERROR: {exc}\n")
        print(json.dumps(make_output(True, f"Guardrail error: {exc}"), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())