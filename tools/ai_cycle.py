#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path


MAX_IMPLEMENTATION_RETRIES = 2
MAX_REVIEW_ROUNDS = 2


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

    # Explicitly terminate option parsing. --file is an array option in
    # OpenCode and would otherwise consume the prompt as another filename.
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
            f"OpenCode agent '{agent}' failed with exit code "
            f"{returncode}."
        )

    return output


def save(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


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


def implement(
    plan_file: Path,
    task_file: Path,
) -> str:
    return run_agent(
        "implementer",
        """
Implement the attached architecture plan for the attached user task.

Actually modify the repository and perform the focused verification requested
by the plan.

Do not commit or push.

If repository evidence contradicts the plan, stop the conflicting part and
report the contradiction rather than inventing a redesign.
""".strip(),
        files=[task_file, plan_file],
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

Read the task, original architecture plan, and review.

Fix ONLY the review findings and any directly necessary consequences.
Do not perform unrelated improvements.

Run the relevant verification again after the fixes.
Do not commit or push.
""".strip(),
        files=[task_file, plan_file, review_file],
    )


def review(
    plan_file: Path,
    task_file: Path,
) -> str:
    return run_agent(
        "reviewer",
        """
Review the current working-tree implementation against the attached original
user task and architecture plan.

Inspect the actual repository state and git diff yourself.

Do not modify files.

Return the strict VERDICT format required by your reviewer instructions.
""".strip(),
        files=[task_file, plan_file],
    )


def parse_verdict(review_text: str) -> str:
    if "VERDICT: PASS" in review_text:
        return "PASS"

    if "VERDICT: FIX" in review_text:
        return "FIX"

    return "INVALID"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the GPT architect -> DeepSeek implementer -> "
        "GPT reviewer workflow."
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
    plan_file = session_dir / "plan.md"

    save(
        task_file,
        f"# User task\n\n{task}\n",
    )

    snapshot_git_state(session_dir, "00-before")

    print(f"Repository: {ROOT}")
    print(f"Session:    {session_dir}")
    print(f"Task:       {task}")

    plan = run_agent(
        "architect",
        """
Analyze the attached user task for this repository.

Produce the detailed implementation plan required by your architect
instructions.

Do not modify repository files.
""".strip(),
        files=[task_file],
    )

    save(plan_file, plan)

    # Architect must never change the working tree.
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

    implementation = implement(plan_file, task_file)
    save(session_dir / "implementation-1.md", implementation)

    snapshot_git_state(session_dir, "01-after-implementation")

    for review_round in range(1, MAX_REVIEW_ROUNDS + 1):
        review_text = review(plan_file, task_file)

        review_file = session_dir / f"review-{review_round}.md"
        save(review_file, review_text)

        verdict = parse_verdict(review_text)

        if verdict == "PASS":
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

        if verdict == "INVALID":
            raise RuntimeError(
                "Reviewer did not return VERDICT: PASS or VERDICT: FIX. "
                f"See {review_file}"
            )

        if review_round == MAX_REVIEW_ROUNDS:
            snapshot_git_state(session_dir, "99-review-failed")

            print()
            print("===== NOT ACCEPTED =====")
            print(
                f"Implementation still failed review after "
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
            session_dir / f"fix-{review_round}.md",
            fix_result,
        )

        snapshot_git_state(
            session_dir,
            f"{review_round + 1:02d}-after-fix",
        )

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