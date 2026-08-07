#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path


MAX_IMPLEMENTATION_RETRIES = 2
MAX_REVIEW_ROUNDS = 2

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


def run_agent(
    agent: str,
    prompt: str,
    *,
    files: list[Path] | None = None,
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

    assert process.stdout is not None

    for line in process.stdout:
        print(line, end="", flush=True)
        output_lines.append(line)

    returncode = process.wait()
    output = "".join(output_lines)

    if returncode != 0:
        raise RuntimeError(
            f"OpenCode agent '{agent}' failed with exit code {returncode}."
        )

    return output


def parse_json_response(text: str, *, source: str) -> dict:
    """Extract the agent's final JSON object from OpenCode's streamed transcript."""
    text = text.strip()

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

        if timeout > 3600:
            raise RuntimeError(
                f"verification[{index}] asks for a timeout "
                "longer than one hour."
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
) -> str:
    return run_agent(
        "implementer",
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
""".strip(),
        files=[task_file, plan_file],
    )


def fix_verification(
    plan_file: Path,
    task_file: Path,
    verification_file: Path,
) -> str:
    return run_agent(
        "implementer",
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
""".strip(),
        files=[task_file, plan_file, verification_file],
    )


def fix_review(
    plan_file: Path,
    task_file: Path,
    review_file: Path,
) -> str:
    return run_agent(
        "implementer",
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
""".strip(),
        files=[task_file, plan_file, review_file],
    )


def review(
    plan_file: Path,
    task_file: Path,
    verification_file: Path,
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

Do not modify files.

Return ONLY the valid JSON review object required by your reviewer
instructions.
""".strip(),
        files=[task_file, plan_file, verification_file],
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

        fix_result = fix_verification(
            plan_file,
            task_file,
            verification_file,
        )

        save(
            session_dir / f"{phase}-verification-fix-{attempt}.md",
            fix_result,
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
            "Run the GPT architect -> DeepSeek implementer -> "
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
        "task",
        nargs="+",
        help="Description of the requested repository change",
    )

    args = parser.parse_args()
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
    )
    save(
        session_dir / "implementation-1.md",
        implementation,
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
        )

        save(
            session_dir / f"review-fix-{review_round}.md",
            fix_result,
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
