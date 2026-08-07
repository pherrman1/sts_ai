#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path


MAX_IMPLEMENTATION_RETRIES = 2
MAX_REVIEW_ROUNDS = 2

MAX_CHEAP_TIMEOUT_SECONDS = 3600
MAX_EXPENSIVE_TIMEOUT_SECONDS = 6 * 3600

ALLOWED_VERIFICATION_EXECUTABLES = {
    "cmake",
    "ctest",
    "git",
    "python",
    "python3",
    "pytest",
}

ALLOWED_GIT_VERIFICATION_SUBCOMMANDS = {
    "blame",
    "diff",
    "grep",
    "log",
    "rev-parse",
    "show",
    "status",
}


ANSI_ESCAPE_RE = re.compile(
    r"\x1B(?:"
    r"\[[0-?]*[ -/]*[@-~]"
    r"|\][^\x07]*(?:\x07|\x1b\\)"
    r")"
)

FINAL_RESPONSE_BEGIN = "FINAL_RESPONSE_BEGIN"
FINAL_RESPONSE_END = "FINAL_RESPONSE_END"

# The implementation model must never rewrite the workflow that controls it.
# These files are restored byte-for-byte after every implementer invocation
# if the model changes them.
PROTECTED_WORKFLOW_PATHS = (
    Path("opencode.json"),
    Path(".opencode/prompts/architect.md"),
    Path(".opencode/prompts/implementer.md"),
    Path(".opencode/prompts/reviewer.md"),
    Path("tools/ai_cycle.py"),
)


def run(
    cmd: list[str],
    *,
    cwd: Path,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=check,
    )


def find_repo_root() -> Path:
    script_dir = Path(__file__).resolve().parent
    result = run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=script_dir,
    )
    return Path(result.stdout.strip()).resolve()


ROOT = find_repo_root()
AI_ROOT = ROOT / ".ai"


def git(*args: str) -> str:
    result = run(["git", *args], cwd=ROOT)
    return result.stdout


def ensure_safe_start() -> None:
    tracked_changes = git(
        "status",
        "--porcelain",
        "--untracked-files=no",
    ).strip()

    if tracked_changes:
        raise RuntimeError(
            "Tracked working-tree changes already exist.\n\n"
            "Commit or stash them before starting an AI cycle so that the "
            "reviewer can attribute all tracked changes to this task.\n\n"
            f"{tracked_changes}"
        )



def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text).replace("\r", "")


def extract_final_markdown(transcript: str) -> str:
    """Return only the implementation model's final human-readable answer."""
    clean = strip_ansi(transcript).strip()

    begin = clean.rfind(FINAL_RESPONSE_BEGIN)
    if begin != -1:
        start = begin + len(FINAL_RESPONSE_BEGIN)
        end = clean.find(FINAL_RESPONSE_END, start)
        if end != -1:
            return clean[start:end].strip() + "\n"

    # Backward-compatible fallback for an implementer that ignored the
    # explicit sentinel request but followed its normal response template.
    headings = (
        "IMPLEMENTATION SUMMARY",
        "# Implementation summary",
        "## Implementation summary",
    )
    positions = [clean.rfind(heading) for heading in headings]
    start = max(positions)

    if start != -1:
        return clean[start:].strip() + "\n"

    # Last resort: keep the cleaned transcript rather than ANSI garbage.
    return clean + "\n"


def snapshot_protected_workflow_files() -> dict[Path, bytes | None]:
    snapshot: dict[Path, bytes | None] = {}

    for relative_path in PROTECTED_WORKFLOW_PATHS:
        path = ROOT / relative_path
        snapshot[relative_path] = (
            path.read_bytes()
            if path.exists()
            else None
        )

    return snapshot


def restore_protected_workflow_files(
    snapshot: dict[Path, bytes | None],
) -> list[str]:
    restored: list[str] = []

    for relative_path, before in snapshot.items():
        path = ROOT / relative_path
        after = path.read_bytes() if path.exists() else None

        if after == before:
            continue

        if before is None:
            if path.exists():
                path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(before)

        restored.append(str(relative_path))

    if restored:
        print()
        print("===== WORKFLOW FILES RESTORED =====")
        for path in restored:
            print(f"Protected from implementer changes: {path}")
        print()

    return restored


def run_implementer_agent(
    prompt: str,
    *,
    files: list[Path] | None = None,
    log_file: Path | None = None,
) -> str:
    snapshot = snapshot_protected_workflow_files()

    try:
        return run_agent(
            "implementer",
            prompt,
            files=files,
            log_file=log_file,
        )
    finally:
        restore_protected_workflow_files(snapshot)


def run_agent(
    agent: str,
    prompt: str,
    *,
    files: list[Path] | None = None,
    log_file: Path | None = None,
) -> str:
    cmd = [
        "opencode",
        "run",
        "--auto",
        "--agent",
        agent,
        "--dir",
        str(ROOT),
    ]

    for file in files or []:
        cmd.extend(["--file", str(file)])

    # --file is an array option in OpenCode. Explicitly terminate option
    # parsing so the prompt is not consumed as another filename.
    cmd.extend(["--", prompt])

    print()
    print(f"===== {agent.upper()} =====")
    print()

    process = subprocess.Popen(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )

    output_lines: list[str] = []
    log_handle = None

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_handle = log_file.open(
            "w",
            encoding="utf-8",
        )

    try:
        assert process.stdout is not None

        for line in process.stdout:
            # Keep OpenCode's live terminal rendering, including colors.
            print(line, end="", flush=True)
            output_lines.append(line)

            # Session logs are deliberately plain text without ANSI escapes.
            if log_handle is not None:
                log_handle.write(strip_ansi(line))
                log_handle.flush()

        returncode = process.wait()
    finally:
        if log_handle is not None:
            log_handle.close()

    output = "".join(output_lines)

    if returncode != 0:
        raise RuntimeError(
            f"OpenCode agent '{agent}' failed with exit code {returncode}."
        )

    return output

def parse_json_response(text: str, *, source: str) -> dict:
    """Extract the agent's final JSON object from OpenCode's streamed transcript."""
    text = strip_ansi(text).strip()

    # Fast path for quiet/plain output.
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict):
        return data

    # `opencode run` prints tool activity and status lines before the model's
    # final answer. The requested JSON answer is therefore the trailing
    # top-level JSON object, not the complete captured stdout transcript.
    line_starts = [0]
    line_starts.extend(
        index + 1
        for index, char in enumerate(text)
        if char == "\n"
    )

    last_error: json.JSONDecodeError | None = None

    for start in reversed(line_starts):
        if start >= len(text) or text[start] != "{":
            continue

        candidate = text[start:].strip()

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue

        if isinstance(data, dict):
            return data

    detail = (
        str(last_error)
        if last_error is not None
        else "No trailing JSON object found."
    )
    raise RuntimeError(
        f"{source} returned no parseable final JSON object:\n"
        f"{detail}\n\n"
        f"Raw response:\n{text}"
    )


def save(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def save_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def snapshot_git_state(session_dir: Path, name: str) -> None:
    content = (
        "HEAD\n"
        "====\n"
        f"{git('rev-parse', 'HEAD').strip()}\n\n"
        "STATUS\n"
        "======\n"
        f"{git('status', '--short')}\n\n"
        "DIFF STAT\n"
        "=========\n"
        f"{git('diff', '--stat')}\n\n"
        "DIFF\n"
        "====\n"
        f"{git('diff')}\n"
    )

    save(session_dir / f"{name}.txt", content)



def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required session file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in session file {path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            f"Session JSON file must contain an object: {path}"
        )

    return data


def resolve_resume_session(raw: str) -> Path:
    candidate = Path(raw).expanduser()

    if not candidate.is_absolute():
        candidate = (ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(AI_ROOT.resolve())
    except ValueError as exc:
        raise RuntimeError(
            f"Resume session must be inside {AI_ROOT}: {candidate}"
        ) from exc

    if not candidate.exists() or not candidate.is_dir():
        raise RuntimeError(
            f"Resume session does not exist: {candidate}"
        )

    task_file = candidate / "task.md"
    if not task_file.exists():
        raise RuntimeError(
            f"Resume session has no task.md: {candidate}"
        )

    return candidate


def recover_or_load_plan(
    session_dir: Path,
) -> tuple[dict, Path]:
    plan_file = session_dir / "plan.json"

    if plan_file.exists():
        plan = load_json(plan_file)
        validate_plan(plan)
        print(f"Reusing architecture plan: {plan_file}")
        return plan, plan_file

    architect_log = session_dir / "architect.log"

    if not architect_log.exists():
        raise RuntimeError(
            "Cannot resume before architecture planning: neither "
            f"{plan_file.name} nor {architect_log.name} exists in "
            f"{session_dir}."
        )

    print(
        "plan.json is missing; recovering the already-paid architect "
        "answer from architect.log."
    )

    transcript = architect_log.read_text(
        encoding="utf-8",
        errors="replace",
    )

    plan = parse_json_response(
        transcript,
        source="Architect resume log",
    )
    validate_plan(plan)
    save_json(plan_file, plan)

    print(f"Recovered architecture plan: {plan_file}")
    return plan, plan_file


def existing_review_rounds(session_dir: Path) -> list[tuple[int, Path, dict]]:
    found: list[tuple[int, Path, dict]] = []

    pattern = re.compile(r"^review-(\d+)\.json$")

    for path in session_dir.glob("review-*.json"):
        match = pattern.match(path.name)
        if not match:
            continue

        round_number = int(match.group(1))
        data = load_json(path)
        validate_review(data)
        found.append((round_number, path, data))

    found.sort(key=lambda item: item[0])
    return found


def latest_successful_verification(
    session_dir: Path,
) -> Path | None:
    candidates: list[Path] = []

    for path in session_dir.glob("*verification-*.json"):
        try:
            data = load_json(path)
        except RuntimeError:
            continue

        if data.get("required_checks_passed") is True:
            candidates.append(path)

    if not candidates:
        return None

    return max(candidates, key=lambda path: path.stat().st_mtime)



def create_session_dir() -> Path:
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    session_dir = AI_ROOT / timestamp
    session_dir.mkdir(parents=True, exist_ok=False)
    return session_dir


def validate_project_executable(executable: str) -> None:
    if not executable.startswith("./"):
        return

    candidate = (ROOT / executable).resolve()

    try:
        candidate.relative_to(ROOT)
    except ValueError as exc:
        raise RuntimeError(
            f"Verification executable escapes repository: {executable}"
        ) from exc


def resolve_verification_cwd(relative_cwd: str) -> Path:
    cwd = (ROOT / relative_cwd).resolve()

    try:
        cwd.relative_to(ROOT)
    except ValueError as exc:
        raise RuntimeError(
            f"Verification cwd escapes repository: {relative_cwd}"
        ) from exc

    if not cwd.exists():
        raise RuntimeError(
            f"Verification cwd does not exist: {relative_cwd}"
        )

    if not cwd.is_dir():
        raise RuntimeError(
            f"Verification cwd is not a directory: {relative_cwd}"
        )

    return cwd


def validate_plan(plan: dict) -> None:
    required_keys = {
        "task_interpretation",
        "current_behavior",
        "design",
        "implementation_steps",
        "verification",
        "documentation",
        "acceptance_criteria",
        "risks",
    }

    missing = required_keys - plan.keys()

    if missing:
        raise RuntimeError(
            f"Architecture plan is missing keys: {sorted(missing)}"
        )

    if not isinstance(plan["implementation_steps"], list):
        raise RuntimeError(
            "plan.implementation_steps must be a list."
        )

    if not isinstance(plan["verification"], list):
        raise RuntimeError(
            "plan.verification must be a list."
        )

    if not isinstance(plan["documentation"], list):
        raise RuntimeError(
            "plan.documentation must be a list."
        )

    if not isinstance(plan["acceptance_criteria"], list):
        raise RuntimeError(
            "plan.acceptance_criteria must be a list."
        )

    if not isinstance(plan["risks"], list):
        raise RuntimeError(
            "plan.risks must be a list."
        )

    for index, check in enumerate(plan["verification"], start=1):
        if not isinstance(check, dict):
            raise RuntimeError(
                f"verification[{index}] must be an object."
            )

        name = check.get("name")
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError(
                f"verification[{index}].name must be a non-empty string."
            )

        argv = check.get("argv")

        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(x, str) for x in argv)
        ):
            raise RuntimeError(
                f"verification[{index}].argv must be "
                "a non-empty string array."
            )

        executable = argv[0]

        project_local = executable.startswith("./")

        if project_local:
            validate_project_executable(executable)

        if (
            executable not in ALLOWED_VERIFICATION_EXECUTABLES
            and not project_local
        ):
            raise RuntimeError(
                f"Verification executable is not allowed: {executable}"
            )

        if executable == "git":
            if (
                len(argv) < 2
                or argv[1] not in ALLOWED_GIT_VERIFICATION_SUBCOMMANDS
            ):
                raise RuntimeError(
                    f"verification[{index}] uses a disallowed git command: "
                    f"{argv!r}"
                )

        relative_cwd = check.get("cwd", ".")
        if not isinstance(relative_cwd, str):
            raise RuntimeError(
                f"verification[{index}].cwd must be a string."
            )
        resolve_verification_cwd(relative_cwd)

        supplied_env = check.get("env", {})
        if not isinstance(supplied_env, dict):
            raise RuntimeError(
                f"verification[{index}].env must be an object."
            )

        for key, value in supplied_env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise RuntimeError(
                    f"verification[{index}].env entries must be strings."
                )

        required = check.get("required")
        if not isinstance(required, bool):
            raise RuntimeError(
                f"verification[{index}].required must be true or false."
            )

        if check.get("cost") not in {"cheap", "expensive"}:
            raise RuntimeError(
                f"verification[{index}].cost must be "
                "'cheap' or 'expensive'."
            )

        timeout = check.get("timeout_seconds", 300)

        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
            raise RuntimeError(
                f"Invalid timeout for verification[{index}]."
            )

        max_timeout = (
            MAX_EXPENSIVE_TIMEOUT_SECONDS
            if check["cost"] == "expensive"
            else MAX_CHEAP_TIMEOUT_SECONDS
        )

        if timeout > max_timeout:
            raise RuntimeError(
                f"verification[{index}] asks for timeout_seconds={timeout}, "
                f"but the maximum for cost={check['cost']!r} is "
                f"{max_timeout} seconds."
            )


def validate_review(review_data: dict) -> None:
    verdict = review_data.get("verdict")

    if verdict not in {"PASS", "FIX"}:
        raise RuntimeError(
            "Reviewer verdict must be PASS or FIX."
        )

    summary = review_data.get("summary")
    if not isinstance(summary, str):
        raise RuntimeError(
            "Reviewer summary must be a string."
        )

    issues = review_data.get("issues")
    if not isinstance(issues, list):
        raise RuntimeError(
            "Reviewer issues must be a list."
        )

    if verdict == "FIX" and not issues:
        raise RuntimeError(
            "Reviewer returned FIX but supplied no issues."
        )

    for index, issue in enumerate(issues, start=1):
        if not isinstance(issue, dict):
            raise RuntimeError(
                f"Reviewer issue {index} must be an object."
            )

        severity = issue.get("severity")
        if severity not in {"CRITICAL", "MAJOR", "MINOR"}:
            raise RuntimeError(
                f"Reviewer issue {index} has invalid severity: {severity!r}"
            )

        for key in (
            "location",
            "problem",
            "failure_mechanism",
            "required_fix",
        ):
            if not isinstance(issue.get(key), str):
                raise RuntimeError(
                    f"Reviewer issue {index}.{key} must be a string."
                )


def run_verification(
    plan: dict,
    *,
    allow_expensive: bool,
) -> dict:
    results = []

    for index, check in enumerate(plan["verification"], start=1):
        cost = check["cost"]

        if cost == "expensive" and not allow_expensive:
            print()
            print(f"===== SKIP EXPENSIVE: {check['name']} =====")
            print()

            results.append(
                {
                    "name": check["name"],
                    "argv": check["argv"],
                    "cwd": check.get("cwd", "."),
                    "env": check.get("env", {}),
                    "required": check["required"],
                    "cost": cost,
                    "status": "SKIPPED_EXPENSIVE",
                    "returncode": None,
                    "stdout": "",
                }
            )
            continue

        cwd = resolve_verification_cwd(
            check.get("cwd", ".")
        )

        env = os.environ.copy()
        supplied_env = check.get("env", {})

        for key, value in supplied_env.items():
            env[key] = value

        timeout = check.get("timeout_seconds", 300)

        print()
        print(f"===== VERIFY: {check['name']} =====")
        print("argv:", check["argv"])
        print("cwd: ", cwd)
        print()

        try:
            result = subprocess.run(
                check["argv"],
                cwd=cwd,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )

            status = (
                "PASS"
                if result.returncode == 0
                else "FAIL"
            )

            output = result.stdout or ""

            print(output)

            results.append(
                {
                    "name": check["name"],
                    "argv": check["argv"],
                    "cwd": str(cwd.relative_to(ROOT)) or ".",
                    "env": supplied_env,
                    "required": check["required"],
                    "cost": cost,
                    "status": status,
                    "returncode": result.returncode,
                    "stdout": output,
                }
            )

        except subprocess.TimeoutExpired as exc:
            output = ""

            if exc.stdout:
                output = (
                    exc.stdout
                    if isinstance(exc.stdout, str)
                    else exc.stdout.decode(errors="replace")
                )

            print(output)
            print(
                f"\nVerification timed out after {timeout} seconds.",
                flush=True,
            )

            results.append(
                {
                    "name": check["name"],
                    "argv": check["argv"],
                    "cwd": str(cwd.relative_to(ROOT)) or ".",
                    "env": supplied_env,
                    "required": check["required"],
                    "cost": cost,
                    "status": "TIMEOUT",
                    "returncode": None,
                    "stdout": output,
                }
            )

    required_ok = all(
        result["status"] == "PASS"
        for result in results
        if result["required"]
    )

    return {
        "required_checks_passed": required_ok,
        "checks": results,
    }


def implement(
    plan_file: Path,
    task_file: Path,
    *,
    log_file: Path,
) -> str:
    return run_implementer_agent(
        """
Implement the attached architecture plan for the attached user task.

Actually modify the repository. The orchestration program, not you, is
authoritative for final verification and will execute the plan's verification
commands independently after you finish.

You may run focused checks yourself when useful for debugging, but do not
modify the architecture plan or its verification commands.

Do not commit or push.

If repository evidence contradicts the plan, stop the conflicting part and
report the contradiction rather than inventing a redesign.

Never run git restore, git checkout, git reset, git clean, or otherwise revert
a file merely because it was already changed or looks unrelated. Leave such a
file untouched and report it.

Wrap only your final user-facing summary between these exact marker lines:

FINAL_RESPONSE_BEGIN
<final summary>
FINAL_RESPONSE_END
""".strip(),
        files=[task_file, plan_file],
        log_file=log_file,
    )


def fix_verification(
    plan_file: Path,
    task_file: Path,
    verification_file: Path,
    *,
    log_file: Path,
) -> str:
    return run_implementer_agent(
        """
Independent verification of your implementation failed.

Read:
- the original user task
- the architecture plan
- the attached verification report

Diagnose the actual failing stdout/stderr and fix the underlying implementation.

Do not change or weaken legitimate tests merely to make them pass.
Do not modify the architecture plan or its verification commands.
Do not perform unrelated improvements.
Do not commit or push.

The orchestrator will independently execute verification again after you finish.

Never run git restore, git checkout, git reset, git clean, or otherwise revert
a file merely because it was already changed or looks unrelated. Leave such a
file untouched and report it.

Wrap only your final user-facing summary between these exact marker lines:

FINAL_RESPONSE_BEGIN
<final summary>
FINAL_RESPONSE_END
""".strip(),
        files=[task_file, plan_file, verification_file],
        log_file=log_file,
    )


def fix_review(
    plan_file: Path,
    task_file: Path,
    review_file: Path,
    *,
    log_file: Path,
) -> str:
    return run_implementer_agent(
        """
The senior reviewer found concrete problems in the implementation.

Read:
- the original user task
- the architecture plan
- the attached review

Fix ONLY the review findings and any directly necessary consequences.
Do not perform unrelated improvements.
Do not modify the architecture plan or its verification commands.
Do not commit or push.

The orchestrator will independently run the required verification after you
finish.

Never run git restore, git checkout, git reset, git clean, or otherwise revert
a file merely because it was already changed or looks unrelated. Leave such a
file untouched and report it.

Wrap only your final user-facing summary between these exact marker lines:

FINAL_RESPONSE_BEGIN
<final summary>
FINAL_RESPONSE_END
""".strip(),
        files=[task_file, plan_file, review_file],
        log_file=log_file,
    )


def review(
    plan_file: Path,
    task_file: Path,
    verification_file: Path,
    *,
    log_file: Path,
) -> dict:
    review_text = run_agent(
        "reviewer",
        """
Review the current working-tree implementation against:
- the original user task
- the architecture plan
- the independent verification report

Inspect the actual repository state, git diff, affected code, callers,
consumers, tests, and maintained documentation yourself.

The independent verification report is authoritative for mechanical checks.
Do not try to reproduce it with Python or arbitrary shell commands.

When using bash, issue permitted read-only git commands one at a time.
Do not use shell chaining (`&&`, `||`, `;`), pipes, or redirections.

Do not modify files.

Return ONLY the valid JSON review object required by your reviewer
instructions.
""".strip(),
        files=[task_file, plan_file, verification_file],
        log_file=log_file,
    )

    review_data = parse_json_response(
        review_text,
        source="Reviewer",
    )
    validate_review(review_data)
    return review_data


def run_verification_cycle(
    *,
    plan: dict,
    plan_file: Path,
    task_file: Path,
    session_dir: Path,
    phase: str,
    allow_expensive: bool,
) -> tuple[bool, Path]:
    verification_file: Path | None = None

    # Initial verification plus up to MAX_IMPLEMENTATION_RETRIES repair attempts.
    for attempt in range(1, MAX_IMPLEMENTATION_RETRIES + 2):
        verification = run_verification(
            plan,
            allow_expensive=allow_expensive,
        )

        verification_file = (
            session_dir / f"{phase}-verification-{attempt}.json"
        )
        save_json(
            verification_file,
            verification,
        )

        if verification["required_checks_passed"]:
            return True, verification_file

        if attempt > MAX_IMPLEMENTATION_RETRIES:
            return False, verification_file

        print()
        print(
            f"===== VERIFICATION FAILED: REPAIR {attempt}/"
            f"{MAX_IMPLEMENTATION_RETRIES} ====="
        )
        print()

        fix_log_file = (
            session_dir / f"{phase}-verification-fix-{attempt}.log"
        )
        fix_result = fix_verification(
            plan_file,
            task_file,
            verification_file,
            log_file=fix_log_file,
        )

        save(
            session_dir / f"{phase}-verification-fix-{attempt}.md",
            extract_final_markdown(fix_result),
        )

        snapshot_git_state(
            session_dir,
            f"{phase}-after-verification-fix-{attempt}",
        )

    assert verification_file is not None
    return False, verification_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run or resume the GPT architect -> DeepSeek implementer -> "
            "independent verification -> GPT reviewer workflow."
        )
    )

    parser.add_argument(
        "--allow-expensive",
        action="store_true",
        help=(
            "Also execute verification checks marked cost=expensive. "
            "Without this flag they are recorded as skipped."
        ),
    )

    parser.add_argument(
        "--resume",
        metavar="SESSION",
        help=(
            "Resume an existing .ai session instead of creating a new one. "
            "Example: --resume .ai/20260807-211234"
        ),
    )

    parser.add_argument(
        "task",
        nargs="*",
        help="Description of the requested repository change",
    )

    args = parser.parse_args()

    # -----------------------------------------------------------------
    # Session creation / recovery
    # -----------------------------------------------------------------
    if args.resume:
        if args.task:
            parser.error(
                "Do not provide a new task together with --resume; "
                "the existing session's task.md is reused."
            )

        session_dir = resolve_resume_session(args.resume)
        task_file = session_dir / "task.md"

        print(f"Repository: {ROOT}")
        print(f"Resuming:   {session_dir}")

        plan, plan_file = recover_or_load_plan(session_dir)

        # A resumed cycle is expected to have tracked task changes already,
        # so ensure_safe_start() must deliberately NOT run here.
        implementation_log = session_dir / "implementation-1.log"

        if not implementation_log.exists():
            print(
                "No implementation transcript found; continuing from "
                "the implementation stage."
            )

            implementation = implement(
                plan_file,
                task_file,
                log_file=implementation_log,
            )
            save(
                session_dir / "implementation-1.md",
                extract_final_markdown(implementation),
            )

            snapshot_git_state(
                session_dir,
                "01-after-implementation",
            )
        else:
            print(
                "Existing implementation transcript found; preserving the "
                "current working tree and continuing without rerunning "
                "DeepSeek's initial implementation."
            )

        # If a previous semantic review already passed, the session is done.
        reviews = existing_review_rounds(session_dir)
        for review_round, review_file, review_data in reviews:
            if review_data["verdict"] == "PASS":
                print()
                print("===== ALREADY ACCEPTED =====")
                print(f"Review round: {review_round}")
                print(f"Review file:  {review_file}")
                print(f"Session data: {session_dir}")
                return 0

        # Determine where a prior FIX review left us.
        next_review_round = 1

        if reviews:
            last_round, last_review_file, last_review_data = reviews
            next_review_round = last_round + 1

            if last_review_data["verdict"] == "FIX":
                fix_log = session_dir / f"review-fix-{last_round}.log"

                if not fix_log.exists():
                    print(
                        f"Review {last_round} requested fixes but no fixer "
                        "transcript exists; applying those fixes now."
                    )

                    fix_result = fix_review(
                        plan_file,
                        task_file,
                        last_review_file,
                        log_file=fix_log,
                    )

                    save(
                        session_dir / f"review-fix-{last_round}.md",
                        extract_final_markdown(fix_result),
                    )

                    snapshot_git_state(
                        session_dir,
                        f"review-{last_round}-after-fix",
                    )
                else:
                    print(
                        f"Review {last_round} fixer transcript already exists; "
                        "not rerunning that DeepSeek call."
                    )

        # Re-run verification on resume rather than trusting that the current
        # working tree still exactly matches an old verification artifact.
        # This costs local compute, not another architect/reviewer call.
        verification_ok, verification_file = run_verification_cycle(
            plan=plan,
            plan_file=plan_file,
            task_file=task_file,
            session_dir=session_dir,
            phase=f"resume-{dt.datetime.now().strftime('%H%M%S')}",
            allow_expensive=args.allow_expensive,
        )

        if not verification_ok:
            snapshot_git_state(
                session_dir,
                "99-resume-verification-failed",
            )

            print()
            print("===== NOT ACCEPTED =====")
            print(
                "Required verification still fails after resume repair "
                f"attempts. See: {verification_file}"
            )
            return 2

        if next_review_round > MAX_REVIEW_ROUNDS:
            print()
            print("===== NOT ACCEPTED =====")
            print(
                f"The session already used all {MAX_REVIEW_ROUNDS} semantic "
                "review rounds."
            )
            return 2

        for review_round in range(
            next_review_round,
            MAX_REVIEW_ROUNDS + 1,
        ):
            review_data = review(
                plan_file,
                task_file,
                verification_file,
                log_file=session_dir / f"review-{review_round}.log",
            )

            review_file = (
                session_dir / f"review-{review_round}.json"
            )
            save_json(
                review_file,
                review_data,
            )

            if review_data["verdict"] == "PASS":
                snapshot_git_state(
                    session_dir,
                    f"{review_round + 1:02d}-accepted",
                )

                print()
                print("===== ACCEPTED =====")
                print(f"Review round: {review_round}")
                print(f"Session data: {session_dir}")
                print()
                print("No commit was created.")
                print("Inspect the final diff manually before committing:")
                print("  git status --short")
                print("  git diff")
                return 0

            if review_round == MAX_REVIEW_ROUNDS:
                snapshot_git_state(
                    session_dir,
                    "99-review-failed",
                )

                print()
                print("===== NOT ACCEPTED =====")
                print(
                    "Implementation still failed semantic review after "
                    f"{MAX_REVIEW_ROUNDS} rounds."
                )
                print(f"See: {review_file}")
                return 2

            fix_result = fix_review(
                plan_file,
                task_file,
                review_file,
                log_file=session_dir / f"review-fix-{review_round}.log",
            )

            save(
                session_dir / f"review-fix-{review_round}.md",
                extract_final_markdown(fix_result),
            )

            snapshot_git_state(
                session_dir,
                f"review-{review_round}-after-fix",
            )

            verification_ok, verification_file = run_verification_cycle(
                plan=plan,
                plan_file=plan_file,
                task_file=task_file,
                session_dir=session_dir,
                phase=f"review-{review_round}-fix",
                allow_expensive=args.allow_expensive,
            )

            if not verification_ok:
                snapshot_git_state(
                    session_dir,
                    "99-post-review-verification-failed",
                )

                print()
                print("===== NOT ACCEPTED =====")
                print(
                    "Required verification failed after applying reviewer "
                    "fixes."
                )
                print(f"See: {verification_file}")
                return 2

        return 2

    # -----------------------------------------------------------------
    # Fresh session
    # -----------------------------------------------------------------
    if not args.task:
        parser.error(
            "Provide a task for a new cycle, or use --resume SESSION."
        )

    task = " ".join(args.task).strip()

    ensure_safe_start()

    session_dir = create_session_dir()
    task_file = session_dir / "task.md"

    save(
        task_file,
        f"# User task\n\n{task}\n",
    )

    snapshot_git_state(session_dir, "00-before")

    print(f"Repository: {ROOT}")
    print(f"Session:    {session_dir}")
    print(f"Task:       {task}")

    plan_text = run_agent(
        "architect",
        """
Analyze the attached user task for this repository.

Return ONLY the valid JSON architecture plan required by your architect
instructions.

Do not modify repository files.
""".strip(),
        files=[task_file],
        log_file=session_dir / "architect.log",
    )

    plan = parse_json_response(
        plan_text,
        source="Architect",
    )
    validate_plan(plan)

    plan_file = session_dir / "plan.json"
    save_json(plan_file, plan)

    # The architect is read-only. At this point the tracked tree must still be
    # exactly as clean as it was before the cycle.
    unexpected_architect_changes = git(
        "status",
        "--porcelain",
        "--untracked-files=no",
    ).strip()

    if unexpected_architect_changes:
        raise RuntimeError(
            "Architect changed tracked repository files despite read-only "
            "instructions. Aborting.\n\n"
            f"{unexpected_architect_changes}"
        )

    implementation = implement(
        plan_file,
        task_file,
        log_file=session_dir / "implementation-1.log",
    )
    save(
        session_dir / "implementation-1.md",
        extract_final_markdown(implementation),
    )

    snapshot_git_state(
        session_dir,
        "01-after-implementation",
    )

    verification_ok, verification_file = run_verification_cycle(
        plan=plan,
        plan_file=plan_file,
        task_file=task_file,
        session_dir=session_dir,
        phase="implementation",
        allow_expensive=args.allow_expensive,
    )

    if not verification_ok:
        snapshot_git_state(
            session_dir,
            "99-verification-failed",
        )

        print()
        print("===== NOT ACCEPTED =====")
        print(
            "Required verification still fails after "
            f"{MAX_IMPLEMENTATION_RETRIES} repair attempts."
        )
        print(f"See: {verification_file}")
        return 2

    for review_round in range(1, MAX_REVIEW_ROUNDS + 1):
        review_data = review(
            plan_file,
            task_file,
            verification_file,
            log_file=session_dir / f"review-{review_round}.log",
        )

        review_file = (
            session_dir / f"review-{review_round}.json"
        )
        save_json(
            review_file,
            review_data,
        )

        if review_data["verdict"] == "PASS":
            snapshot_git_state(
                session_dir,
                f"{review_round + 1:02d}-accepted",
            )

            print()
            print("===== ACCEPTED =====")
            print(f"Review round: {review_round}")
            print(f"Session data: {session_dir}")
            print()
            print("No commit was created.")
            print("Inspect the final diff manually before committing:")
            print("  git status --short")
            print("  git diff")
            return 0

        if review_round == MAX_REVIEW_ROUNDS:
            snapshot_git_state(
                session_dir,
                "99-review-failed",
            )

            print()
            print("===== NOT ACCEPTED =====")
            print(
                "Implementation still failed semantic review after "
                f"{MAX_REVIEW_ROUNDS} rounds."
            )
            print(f"See: {review_file}")
            return 2

        fix_result = fix_review(
            plan_file,
            task_file,
            review_file,
            log_file=session_dir / f"review-fix-{review_round}.log",
        )

        save(
            session_dir / f"review-fix-{review_round}.md",
            extract_final_markdown(fix_result),
        )

        snapshot_git_state(
            session_dir,
            f"review-{review_round}-after-fix",
        )

        verification_ok, verification_file = run_verification_cycle(
            plan=plan,
            plan_file=plan_file,
            task_file=task_file,
            session_dir=session_dir,
            phase=f"review-{review_round}-fix",
            allow_expensive=args.allow_expensive,
        )

        if not verification_ok:
            snapshot_git_state(
                session_dir,
                "99-post-review-verification-failed",
            )

            print()
            print("===== NOT ACCEPTED =====")
            print(
                "Required verification failed after applying reviewer fixes."
            )
            print(f"See: {verification_file}")
            return 2

    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
