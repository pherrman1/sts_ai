#!/usr/bin/env python3
"""Repository-owned Cline hook policy and cheap completion checks.

Follows the Cline hook JSON protocol:
- Stdin: JSON HookInput (with preToolUse / taskComplete data)
- Stdout: JSON HookOutput {"cancel": bool, "errorMessage"?: str, "contextModification"?: str}
- Stderr: Diagnostic logging
"""
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

EDIT_TOOLS = {
    "write_to_file", "replace_in_file", "apply_patch", "apply_diff",
    "write_file", "replace_content", "replace_in_files", "editor",
    "serena__replace_content", "serena__replace_symbol_body",
    "serena__replace_in_files", "serena__insert_after_symbol",
    "serena__insert_before_symbol", "serena__rename_symbol",
    "serena__safe_delete_symbol",
}


def make_output(cancel: bool = False, error: str = "", context: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"cancel": cancel}
    if error:
        out["errorMessage"] = error
    if context:
        out["contextModification"] = context
    return out


def _extract_commands(parameters: Any) -> list[str]:
    if not isinstance(parameters, dict):
        return []
    values: list[str] = []
    for key in ("command", "cmd", "commands"):
        val = parameters.get(key)
        if isinstance(val, str):
            values.append(val)
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    values.append(item)
                elif isinstance(item, dict) and "command" in item:
                    values.append(str(item["command"]))
    return values

def _split_pipeline_or_subcommands(command: str) -> list[list[str]]:
    """Split command string on shell operators (;, &&, ||, |) into token lists."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        raw_tokens = list(lexer)
    except ValueError:
        raw_tokens = command.split()

    segments: list[list[str]] = []
    current: list[str] = []
    for token in raw_tokens:
        if token in {";", "&&", "||", "|"}:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)
    return segments


def _basename(token: str) -> str:
    cleaned = token.replace("\\", "/").rstrip("/")
    return cleaned.split("/")[-1]


def _is_seed_guarded(tokens: list[str], target_exe: str) -> bool:
    """Return True if target_exe in tokens is invoked via seed_guard.sh."""
    for idx, token in enumerate(tokens):
        if _basename(token) == target_exe:
            for prev_idx in range(idx):
                if _basename(tokens[prev_idx]) == "seed_guard.sh":
                    return True
    return False


def _check_command_safety(command: str, branch: str) -> str | None:
    segments = _split_pipeline_or_subcommands(command)
    for tokens in segments:
        if not tokens:
            continue
        lower_tokens = [t.lower() for t in tokens]

        # 1. Privilege escalation
        if any(t in {"sudo", "doas", "su"} for t in lower_tokens):
            return "Privilege escalation (sudo/doas/su) is blocked. Perform manual setup if needed."

        # 2. Broad process termination
        if any(t in {"pkill", "killall"} for t in lower_tokens) or (
            lower_tokens[0] == "kill" and not (len(tokens) == 2 and tokens[1].lstrip("-").isdigit())
        ):
            return "Broad process termination (pkill/killall/kill) is blocked. Resolve and stop processes manually."

        # 3. Direct one_combat / check_replay invocations without seed_guard.sh
        if any(_basename(t) == "one_combat" for t in tokens):
            if not _is_seed_guarded(tokens, "one_combat"):
                return "Direct execution of one_combat is blocked. Route through tools/seed_guard.sh."

        if any(_basename(t) == "check_replay.py" for t in tokens):
            if not _is_seed_guarded(tokens, "check_replay.py"):
                return "Direct execution of check_replay.py is blocked. Route through tools/seed_guard.sh."

        # 4. Git destructive commands
        git_idx = -1
        for idx, t in enumerate(lower_tokens):
            if _basename(t) == "git":
                git_idx = idx
                break

        if git_idx != -1:
            git_args = lower_tokens[git_idx + 1 :]
            if git_args:
                subcmd = git_args[0]
                if subcmd == "reset" and "--hard" in git_args:
                    return "git reset --hard is blocked."
                if subcmd == "clean" and any(
                    arg == "-f" or arg == "--force" or (arg.startswith("-") and "f" in arg and "d" in arg) or (arg.startswith("-") and "d" in arg)
                    for arg in git_args[1:]
                ):
                    return "Destructive git clean is blocked."
                if subcmd == "branch" and any(arg in {"-d", "-D", "--delete"} for arg in git_args):
                    return "Branch deletion (git branch -d/-D) is blocked."
                if subcmd == "push":
                    if any(arg in {"--force", "-f", "--force-with-lease"} for arg in git_args):
                        return "Force push (git push --force/-f/--force-with-lease) is blocked."
                    if "main" in git_args:
                        return "Direct push to main is blocked. Use a feature branch and pull request."
                    if branch == "main":
                        return "Plain git push from main is blocked. Work on a feature branch."
                if subcmd in {"checkout", "restore"}:
                    if any(arg in {".", "-- .", "--worktree", "--all"} for arg in git_args):
                        return f"Broad working-tree discard (git {subcmd} .) is blocked."

        # 5. Recursive filesystem deletion
        first_token = _basename(lower_tokens[0])
        if first_token in {"rm", "rmdir"}:
            flags = [t for t in lower_tokens[1:] if t.startswith("-")]
            if any("r" in f or "R" in f for f in flags) or "--recursive" in flags or "/s" in lower_tokens:
                return "Broad recursive filesystem deletion (rm -r/-rf) is blocked."

    return None


def get_current_git_branch() -> str:
    override = os.environ.get("CLINE_GUARD_BRANCH")
    if override:
        return override.strip()
    try:
        res = subprocess.check_output(
            ["git", "branch", "--show-current"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        return res
    except (OSError, subprocess.CalledProcessError):
        return ""


def handle_pre_tool_use(data: dict[str, Any]) -> dict[str, Any]:
    pre = data.get("preToolUse") or data.get("pre_tool_use") or {}
    tool_name = str(pre.get("toolName", pre.get("tool_name", "")))
    parameters = pre.get("parameters", {})
    branch = str(data.get("branch") or get_current_git_branch())

    # Check main branch edit protection
    if branch == "main" and tool_name in EDIT_TOOLS:
        return make_output(
            cancel=True,
            error="Project-file modifications are blocked on main. Please create and switch to a feature branch first.",
        )

    # Check shell commands
    commands = _extract_commands(parameters)
    for cmd in commands:
        danger = _check_command_safety(cmd, branch)
        if danger:
            sys.stderr.write(f"CLINE_GUARD: blocked command: {cmd!r} reason: {danger}\n")
            return make_output(cancel=True, error=danger)

    return make_output(cancel=False)


def collect_changed_files(metadata: dict[str, Any]) -> list[Path]:
    candidates: list[str] = []
    for key in ("changedFiles", "changed_files", "files"):
        val = metadata.get(key)
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except json.JSONDecodeError:
                val = val.splitlines()
        if isinstance(val, list):
            candidates.extend(str(item) for item in val)

    if not candidates:
        try:
            res_diff = subprocess.run(
                ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", "HEAD"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            if res_diff.returncode == 0:
                candidates.extend(res_diff.stdout.splitlines())

            res_untracked = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            if res_untracked.returncode == 0:
                candidates.extend(res_untracked.stdout.splitlines())
        except OSError:
            pass

    out: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        item = item.strip()
        if item and item not in seen:
            seen.add(item)
            p = ROOT / item
            if p.is_file():
                out.append(p)
    return out


def handle_task_complete(data: dict[str, Any]) -> dict[str, Any]:
    diff_check = subprocess.run(["git", "diff", "--check"], cwd=ROOT, text=True, capture_output=True, check=False)
    if diff_check.returncode != 0:
        err = "git diff --check failed; fix whitespace errors before completing:\n" + diff_check.stdout + diff_check.stderr
        return make_output(True, err.strip())
    task = data.get("taskComplete") or data.get("task_complete") or {}
    metadata = task.get("taskMetadata") or task.get("task_metadata") or {}
    changed = collect_changed_files(metadata if isinstance(metadata, dict) else {})
    checks = [([p for p in changed if p.suffix == ".py"], [sys.executable, "-m", "py_compile"], "Python syntax")]
    if shutil.which("bash"):
        checks.append(([p for p in changed if p.suffix == ".sh"], ["bash", "-n"], "Shell syntax"))
    for files, command, label in checks:
        if files:
            result = subprocess.run(command + [str(p) for p in files], cwd=ROOT, text=True, capture_output=True, check=False)
            if result.returncode:
                return make_output(True, f"{label} check failed:\n{result.stderr or result.stdout}".strip())
    for path in (p for p in changed if p.suffix == ".json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return make_output(True, f"JSON syntax check failed for {path.relative_to(ROOT)}: {exc}")
    if any(p.suffix in {".cpp", ".cc", ".cxx", ".h", ".hpp", ".hh", ".cmake"} or p.name in {"CMakeLists.txt", "CMakePresets.json"} for p in changed):
        return make_output(False, context="C++/CMake files changed: run focused local verification when useful; the PR Linux GCC check must pass before manual merge. TaskComplete does not run a full build or gameplay benchmark.")
    return make_output(False)


def main() -> int:
    try:
        data = json.load(sys.stdin)
        name = str(data.get("hookName") or data.get("hook_name") or "")
        result = handle_task_complete(data) if name == "TaskComplete" or "taskComplete" in data or "task_complete" in data else handle_pre_tool_use(data)
        print(json.dumps(result, separators=(",", ":")))
    except Exception as exc:
        sys.stderr.write(f"CLINE_GUARD_ERROR: {exc}\n")
        print(json.dumps(make_output(True, f"Guardrail error: {exc}"), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
