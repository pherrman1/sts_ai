#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path


MAX_IMPLEMENTATION_RETRIES = 2
MAX_REVIEW_ROUNDS = 2
MAX_SOL_REVIEW_ROUNDS = 3
MAX_EXPENSIVE_REPAIRS = 2

MAX_CHEAP_TIMEOUT_SECONDS = 3600
MAX_EXPENSIVE_TIMEOUT_SECONDS = 6 * 3600
MAX_AUTOMATED_SEEDS = 128

KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX = {
    "allbench": 3,
    "bench": 3,
    "bestbench": 3,
    "cardbench": 3,
    "causalgen": 2,
    "combatgen": 2,
    "combobench": 3,
    "cpsictr": 3,
    "datagen": 2,
    "datagen2": 2,
    "datagen3": 2,
    "distgen": 2,
    "draftbench": 3,
    "evalcombat": 3,
    "evalrun": 3,
    "fairgen": 2,
    "fightgen": 2,
    "oocnextgen": 2,
    "pathbench": 3,
    "pathcfgen": 2,
    "policygen": 2,
    "restbench": 3,
    "runbench": 3,
    "searchdiag": 2,
    "shopbench": 3,
    "skipbench": 3,
    "strategicgen": 2,
    "strategicgen2": 2,
}

KNOWN_PYTHON_SEED_SWEEP_ARG_INDEX = {
    "check_replay.py": 3,
}

# Keep escalation policy centralized and inspectable. Documentation-only paths
# do not trigger subsystem escalation unless the architecture plan itself
# identifies a semantic risk.
HIGH_RISK_PATH_RULES = {
    "training": ("train_", "training", "selfplay/"),
    "inference": ("inference", "export_", "native_model", "v_server.py"),
    "selfplay": ("selfplay/", "selfplay"),
    "search": ("search", "searcher", "battle_scum"),
    "RNG/seed handling": ("rng", "random", "seed"),
    "VNet/PVNet": ("vnet", "pvnet"),
    "evaluation/benchmark methodology": (
        "paired_analysis.py",
        "benchmark",
        "bestbench",
        "evaluation",
    ),
    "strategic labels/targets": ("strategic", "label", "target"),
    "counterfactual generation": ("counterfactual", "causalgen"),
    "action masking/state encoding": ("action_mask", "masking", "encoder"),
}

HIGH_RISK_PLAN_TERMS = {
    "training": ("training", "trainer", "retrain"),
    "inference": ("inference", "model loading", "model export", "model use"),
    "selfplay": ("selfplay", "self-play"),
    "search": ("search semantics", "searcher", "tree search"),
    "RNG/fairness": ("rng", "fairness", "known-rng", "known rng", "seed handling"),
    "VNet/PVNet": ("vnet", "pvnet"),
    "evaluation methodology": ("evaluation validity", "benchmark methodology"),
    "labels/targets/bootstrap": (
        "label semantics",
        "target semantics",
        "bootstrap semantics",
    ),
    "counterfactual generation": ("counterfactual generation",),
    "action masking/state encoding": ("action masking", "state encoding"),
    "leakage/parity mismatch": (
        "leakage",
        "training/inference parity",
        "offline/online mismatch",
        "model-use parity",
    ),
}

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


class RejectedRecoveryExhausted(RuntimeError):
    pass

# The implementation model must never rewrite the workflow that controls it.
# These files are restored byte-for-byte after every implementer invocation
# if the model changes them.
PROTECTED_WORKFLOW_PATHS = (
    Path("opencode.json"),
    Path(".opencode/prompts/architect.md"),
    Path(".opencode/prompts/implementer.md"),
    Path(".opencode/prompts/reviewer.md"),
    Path(".opencode/prompts/reviewer-escalation.md"),
    Path("tools/ai_cycle.py"),
    Path("tools/ai_inspect.py"),
    Path("tools/test_ai_cycle.py"),
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


def candidate_fingerprint(*, context_files: tuple[Path, ...] = ()) -> str:
    """Identify the review candidate without hashing ignored experiment data."""
    digest = hashlib.sha256()
    digest.update(git("rev-parse", "HEAD").strip().encode("ascii"))
    digest.update(git("diff", "--binary", "HEAD").encode("utf-8"))
    for path in context_files:
        digest.update(str(path.resolve()).encode("utf-8"))
        digest.update(path.read_bytes())

    # New non-ignored files are not in git diff, so hash their contents too.
    status = git("status", "--porcelain", "--untracked-files=all")
    digest.update(status.encode("utf-8"))
    for line in status.splitlines():
        if not line.startswith("?? "):
            continue
        path = ROOT / line[3:]
        if path.is_file():
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)

    return digest.hexdigest()


def changed_diff_stats() -> tuple[list[str], int, int]:
    paths = [
        line
        for line in git("diff", "--name-only", "HEAD").splitlines()
        if line
    ]
    changed_lines = 0
    tracked_files = 0
    for line in git("diff", "--numstat", "HEAD").splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        tracked_files += 1
        if parts[0].isdigit():
            changed_lines += int(parts[0])
        if parts[1].isdigit():
            changed_lines += int(parts[1])

    status = git("status", "--porcelain", "--untracked-files=all")
    for line in status.splitlines():
        if not line.startswith("?? "):
            continue
        relative_path = line[3:]
        paths.append(relative_path)
        path = ROOT / relative_path
        if path.is_file():
            tracked_files += 1
            try:
                with path.open("r", encoding="utf-8", errors="replace") as handle:
                    changed_lines += sum(1 for _ in handle)
            except OSError:
                pass
    return sorted(set(paths)), changed_lines, tracked_files


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


def recover_completed_implementer_summary(log_file: Path, summary_file: Path) -> bool:
    if summary_file.exists():
        return True
    if not log_file.exists():
        return False
    transcript = log_file.read_text(encoding="utf-8", errors="replace")
    if FINAL_RESPONSE_END not in strip_ansi(transcript):
        return False
    save(summary_file, extract_final_markdown(transcript))
    print(f"Recovered completed implementer response from: {log_file}")
    return True


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


CYCLE_COST_ENTRIES: list[dict] = []
CYCLE_DENIED_CALLS: list[tuple[str, str]] = []

DENIED_TOOL_MARKER = (
    "The user has specified a rule which prevents you from using this "
    "specific tool call."
)


def extract_denied_tool_calls(lines: list[str]) -> list[str]:
    """Find attempted calls that a permission rule blocked.

    OpenCode prints the denied command as a line starting with a cross mark
    and ending in " failed", immediately followed by the rule-denial error.
    """
    stripped = [strip_ansi(line) for line in lines]
    calls: list[str] = []
    for index, line in enumerate(stripped):
        if DENIED_TOOL_MARKER not in line:
            continue
        for previous in range(index - 1, max(-1, index - 5), -1):
            prev = stripped[previous].strip()
            if prev.startswith("\u2717 ") and prev.endswith(" failed"):
                calls.append(prev[2 : -len(" failed")].strip())
                break
    return calls


def append_denied_tool_calls(
    session_dir: Path,
    agent: str,
    calls: list[str],
    timestamp: str,
) -> None:
    if not calls:
        return
    path = session_dir / "denied-tool-calls.md"
    if not path.exists():
        save(
            path,
            "# Denied tool calls\n\n"
            "Attempted calls that a workflow permission rule blocked, per agent "
            "and run. Review these to decide whether a rule should be widened.\n",
        )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {agent} \u2014 {timestamp}\n")
        for call in calls:
            handle.write(f"- `{call}`\n")
        handle.write("\n")



def opencode_db_path() -> Path | None:
    """Locate the opencode session database (Linux default or XDG override)."""
    data_home = Path(
        os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    )
    candidates = (
        data_home / "opencode" / "opencode.db",
        Path.home() / ".local" / "share" / "opencode" / "opencode.db",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def fetch_costs_since(since_ms: int) -> list[dict]:
    """Read session cost/token rows created for this repository since since_ms."""
    db_path = opencode_db_path()
    if db_path is None:
        return []

    try:
        connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        rows = connection.execute(
            """
            SELECT agent, model, cost,
                   tokens_input, tokens_output, tokens_reasoning,
                   tokens_cache_read, tokens_cache_write
            FROM session
            WHERE directory = ? AND time_created >= ?
            ORDER BY time_created
            """,
            (str(ROOT), int(since_ms)),
        ).fetchall()
        connection.close()
    except (sqlite3.Error, OSError):
        return []

    entries: list[dict] = []
    for agent, model_json, cost, ti, to, tr, tcr, tcw in rows:
        model = ""
        if isinstance(model_json, str):
            try:
                model = json.loads(model_json).get("id", "")
            except json.JSONDecodeError:
                model = model_json
        entries.append(
            {
                "agent": agent or "unknown",
                "model": model,
                "cost": float(cost or 0.0),
                "tokens_input": int(ti or 0),
                "tokens_output": int(to or 0),
                "tokens_reasoning": int(tr or 0),
                "tokens_cache_read": int(tcr or 0),
                "tokens_cache_write": int(tcw or 0),
            }
        )
    return entries


def summarize_cost_entries(entries: list[dict]) -> dict:
    by_agent: dict[str, float] = {}
    for entry in entries:
        agent = entry.get("agent") or "unknown"
        by_agent[agent] = by_agent.get(agent, 0.0) + float(entry.get("cost") or 0.0)
    return {"per_agent": by_agent, "total": sum(by_agent.values())}


def append_cost_entries(session_dir: Path, entries: list[dict]) -> None:
    if not entries:
        return
    path = session_dir / "costs.json"
    existing: list[dict] = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            loaded = None
        if isinstance(loaded, dict) and isinstance(loaded.get("entries"), list):
            existing = loaded["entries"]
    save_json(path, {"entries": [*existing, *entries]})


def print_cycle_cost_summary() -> None:
    if not CYCLE_COST_ENTRIES:
        print()
        print("===== AI CYCLE COST =====")
        print("No cost data recorded (opencode session database not found or")
        print("no agent calls were made in this run).")
        return

    summary = summarize_cost_entries(CYCLE_COST_ENTRIES)
    print()
    print("===== AI CYCLE COST =====")
    for agent, cost in sorted(summary["per_agent"].items()):
        print(f"{agent:<22} ${cost:.4f}")
    print(f"{'TOTAL':<22} ${summary['total']:.4f}")
    print("Per-call breakdown saved in the session's costs.json.")

    if CYCLE_DENIED_CALLS:
        print()
        print(
            f"===== DENIED TOOL CALLS: {len(CYCLE_DENIED_CALLS)} ====="
        )
        by_agent: dict[str, int] = {}
        for agent, _ in CYCLE_DENIED_CALLS:
            by_agent[agent] = by_agent.get(agent, 0) + 1
        for agent, count in sorted(by_agent.items()):
            print(f"{agent:<22} {count}")
        print("Review them in the session's denied-tool-calls.md and adjust")
        print("permission rules in opencode.json if needed.")


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

    call_start_ms = time.time() * 1000

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

        cost_entries = fetch_costs_since(call_start_ms)
        if cost_entries:
            CYCLE_COST_ENTRIES.extend(cost_entries)
            if log_file is not None:
                append_cost_entries(log_file.parent, cost_entries)
            call_total = sum(entry["cost"] for entry in cost_entries)
            models = ", ".join(
                sorted({entry["model"] for entry in cost_entries if entry["model"]})
            )
            print()
            print(
                f"===== AGENT COST: {agent} ${call_total:.4f}"
                + (f" ({models})" if models else "")
                + " ====="
            )

        denied_calls = extract_denied_tool_calls(output_lines)
        if denied_calls:
            CYCLE_DENIED_CALLS.extend((agent, call) for call in denied_calls)
            if log_file is not None:
                append_denied_tool_calls(
                    log_file.parent,
                    agent,
                    denied_calls,
                    dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )
            print()
            print(
                f"===== DENIED TOOL CALLS: {len(denied_calls)} ====="
            )
            print("Recorded in denied-tool-calls.md for permission-rule review.")

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

    # Some models wrap the answer in a fenced code block (```json ... ```).
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced is not None:
        try:
            data = json.loads(fenced.group(1))
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
        upgraded = upgrade_legacy_seed_counts(plan)
        validate_plan(plan, allow_legacy_sweeps=True)
        if upgraded:
            save_json(plan_file, plan)
            print("Added seed_count to known legacy sweep checks.")
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
    upgrade_legacy_seed_counts(plan)
    validate_plan(plan, allow_legacy_sweeps=True)
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
        validate_review(data, allow_legacy=True)
        found.append((round_number, path, data))

    found.sort(key=lambda item: item[0])
    return found


def existing_sol_review_rounds(session_dir: Path) -> list[tuple[int, Path, dict]]:
    found: list[tuple[int, Path, dict]] = []
    pattern = re.compile(r"^sol-review-(\d+)\.json$")

    for path in session_dir.glob("sol-review-*.json"):
        match = pattern.match(path.name)
        if not match:
            continue
        data = load_json(path)
        validate_review(data, allow_legacy=True)
        found.append((int(match.group(1)), path, data))

    found.sort(key=lambda item: item[0])
    return found


def matching_review(
    reviews: list[tuple[int, Path, dict]],
    fingerprint: str,
) -> tuple[int, Path, dict] | None:
    for item in reversed(reviews):
        if item[2].get("candidate_fingerprint") == fingerprint:
            return item
    return None


def verification_reports(session_dir: Path) -> list[tuple[Path, dict]]:
    reports: list[tuple[Path, dict]] = []
    for path in session_dir.glob("*verification-*.json"):
        try:
            reports.append((path, load_json(path)))
        except RuntimeError:
            continue
    reports.sort(key=lambda item: item[0].stat().st_mtime)
    return reports


def matching_successful_verification(
    session_dir: Path,
    fingerprint: str,
    costs: set[str],
) -> Path | None:
    candidates = []
    for path, data in verification_reports(session_dir):
        if data.get("candidate_fingerprint") != fingerprint:
            continue
        if set(data.get("costs_run", [])) != costs:
            continue
        if data.get("required_checks_passed") is True:
            candidates.append(path)
    return candidates[-1] if candidates else None


def matching_verification_report(
    session_dir: Path,
    fingerprint: str,
    costs: set[str],
) -> tuple[Path, dict] | None:
    for path, data in reversed(verification_reports(session_dir)):
        if data.get("candidate_fingerprint") != fingerprint:
            continue
        if set(data.get("costs_run", [])) == costs:
            return path, data
    return None


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


def known_seed_sweep_arg_index(argv: list[str]) -> int | None:
    executable_name = Path(argv[0]).name
    if (
        executable_name == "one_combat"
        and len(argv) >= 2
        and argv[1] in KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX
    ):
        return KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX[argv[1]]
    if (
        executable_name in {"python", "python3"}
        and len(argv) >= 2
        and Path(argv[1]).name in KNOWN_PYTHON_SEED_SWEEP_ARG_INDEX
    ):
        return KNOWN_PYTHON_SEED_SWEEP_ARG_INDEX[Path(argv[1]).name]
    return None


def upgrade_legacy_seed_counts(plan: dict) -> bool:
    """Upgrade only known pre-seed_count plans while preserving strict new plans.

    A recorded legacy sweep whose inferred seed count exceeds the automated
    cap is left without seed_count: it documents a pre-existing experiment and
    must not be rejected merely because it predates the cap.
    """
    upgraded = False
    for check in plan.get("verification", []):
        if not isinstance(check, dict) or "seed_count" in check:
            continue
        argv = check.get("argv")
        if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
            continue
        seed_arg_index = known_seed_sweep_arg_index(argv)
        if seed_arg_index is None or len(argv) <= seed_arg_index:
            continue
        try:
            inferred = int(argv[seed_arg_index])
        except ValueError:
            continue
        if inferred > MAX_AUTOMATED_SEEDS:
            continue
        check["seed_count"] = inferred
        upgraded = True
    return upgraded


def validate_plan(plan: dict, *, allow_legacy_sweeps: bool = False) -> None:
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

        seed_count = check.get("seed_count")
        if seed_count is not None and (
            not isinstance(seed_count, int)
            or isinstance(seed_count, bool)
            or seed_count <= 0
        ):
            raise RuntimeError(
                f"verification[{index}].seed_count must be a positive integer."
            )
        if seed_count is not None and seed_count > MAX_AUTOMATED_SEEDS:
            raise RuntimeError(
                f"verification[{index}].seed_count={seed_count} exceeds the "
                f"automated maximum of {MAX_AUTOMATED_SEEDS}."
            )

        seed_arg_index = known_seed_sweep_arg_index(argv)

        if seed_arg_index is not None:
            if seed_count is None:
                if not allow_legacy_sweeps:
                    raise RuntimeError(
                        f"verification[{index}] is a known game-seed sweep and "
                        "must declare seed_count."
                    )
                continue
            if len(argv) <= seed_arg_index:
                raise RuntimeError(
                    f"verification[{index}] omits the known seed-count argv."
                )
            try:
                argv_seed_count = int(argv[seed_arg_index])
            except ValueError as exc:
                raise RuntimeError(
                    f"verification[{index}] has a non-integer seed-count argv."
                ) from exc
            if argv_seed_count != seed_count:
                raise RuntimeError(
                    f"verification[{index}].seed_count={seed_count} does not "
                    f"match argv seed count {argv_seed_count}."
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


def validate_review(review_data: dict, *, allow_legacy: bool = False) -> None:
    verdict = review_data.get("verdict")

    if verdict not in {"PASS", "FIX"}:
        raise RuntimeError(
            "Reviewer verdict must be PASS or FIX."
        )

    summary = review_data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise RuntimeError(
            "Reviewer summary must be a non-empty string."
        )

    eli5_summary = review_data.get("eli5_summary")
    if allow_legacy and eli5_summary is None:
        eli5_summary = "Legacy review artifact; no ELI5 summary was recorded."
    if not isinstance(eli5_summary, str) or not eli5_summary.strip():
        raise RuntimeError(
            "Reviewer eli5_summary must be a non-empty string."
        )

    uncertainty = review_data.get("uncertainty")
    if allow_legacy and uncertainty is None:
        uncertainty = "HIGH"
    if uncertainty not in {"LOW", "MEDIUM", "HIGH"}:
        raise RuntimeError(
            "Reviewer uncertainty must be LOW, MEDIUM, or HIGH."
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

    if verdict == "PASS" and any(
        issue["severity"] in {"CRITICAL", "MAJOR"} for issue in issues
    ):
        raise RuntimeError(
            "Reviewer returned PASS with a CRITICAL or MAJOR issue."
        )


def run_verification(
    plan: dict,
    *,
    costs_to_run: set[str],
) -> dict:
    if not costs_to_run <= {"cheap", "expensive"}:
        raise ValueError(f"Invalid verification costs: {sorted(costs_to_run)}")

    results = []

    for index, check in enumerate(plan["verification"], start=1):
        cost = check["cost"]

        if cost not in costs_to_run:
            print()
            print(f"===== NOT RUN THIS PHASE: {check['name']} =====")
            print()

            results.append(
                {
                    "name": check["name"],
                    "argv": check["argv"],
                    "cwd": check.get("cwd", "."),
                    "env": check.get("env", {}),
                    "required": check["required"],
                    "cost": cost,
                    "status": "NOT_RUN_THIS_PHASE",
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
        if result["required"] and result["cost"] in costs_to_run
    )

    return {
        "required_checks_passed": required_ok,
        "costs_run": sorted(costs_to_run),
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

You may run cheap focused checks yourself when useful for debugging, but do not
run checks marked expensive and do not modify the architecture plan or its
verification commands.

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
    agent: str = "reviewer",
    extra_files: list[Path] | None = None,
    prompt: str | None = None,
    log_file: Path,
) -> dict:
    review_text = run_agent(
        agent,
        prompt or """
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
        files=[task_file, plan_file, verification_file, *(extra_files or [])],
        log_file=log_file,
    )

    review_data = parse_json_response(
        review_text,
        source=agent,
    )
    validate_review(review_data)
    return review_data


def save_and_print_review(
    session_dir: Path,
    review_data: dict,
    *,
    round_number: int,
    sol: bool = False,
    artifact_stem: str | None = None,
    display_label: str | None = None,
) -> Path:
    stem = artifact_stem or (
        f"sol-review-{round_number}" if sol else f"review-{round_number}"
    )
    review_file = session_dir / f"{stem}.json"
    save_json(review_file, review_data)
    eli5_file = session_dir / f"{stem}-eli5.md"
    save(eli5_file, review_data["eli5_summary"].strip() + "\n")

    label = display_label or (
        f"ESCALATION REVIEW {round_number}" if sol else f"REVIEW {round_number}"
    )
    print()
    print(f"===== {label}: {review_data['verdict']} =====")
    print()
    print("ELI5:")
    print(review_data["eli5_summary"].strip())
    print()
    print("Technical review:")
    print(review_file)
    print()
    return review_file


def obtain_review(
    *,
    session_dir: Path,
    plan_file: Path,
    task_file: Path,
    verification_file: Path,
    fingerprint: str,
    round_number: int,
    sol: bool = False,
    extra_files: list[Path] | None = None,
    artifact_stem: str | None = None,
    display_label: str | None = None,
    prompt: str | None = None,
    review_transform: Callable[[dict], None] | None = None,
    single_attempt: bool = False,
) -> tuple[Path, dict]:
    stem = artifact_stem or (
        f"sol-review-{round_number}" if sol else f"review-{round_number}"
    )
    log_file = session_dir / f"{stem}.log"
    candidate_file = session_dir / f"{stem}-candidate.json"

    if log_file.exists() and candidate_file.exists():
        metadata = load_json(candidate_file)
        if metadata.get("candidate_fingerprint") == fingerprint:
            try:
                data = parse_json_response(
                    log_file.read_text(encoding="utf-8", errors="replace"),
                    source=f"{stem} resume log",
                )
                validate_review(data)
                if review_transform is not None:
                    review_transform(data)
            except RuntimeError:
                if single_attempt:
                    exhausted_file = session_dir / "recovery-exhausted.json"
                    save_json(
                        exhausted_file,
                        {
                            "reason": f"{stem} returned an incomplete or invalid review",
                            "artifact_file": log_file.name,
                            "candidate_fingerprint": fingerprint,
                        },
                    )
                    raise RejectedRecoveryExhausted(
                        f"The bounded {stem} attempt was incomplete or invalid. "
                        f"See: {exhausted_file}"
                    )
                print(f"Incomplete {stem} transcript found; rerunning that call.")
            else:
                data["candidate_fingerprint"] = fingerprint
                print(f"Recovered completed paid review from: {log_file}")
                return (
                    save_and_print_review(
                        session_dir,
                        data,
                        round_number=round_number,
                        sol=sol,
                        artifact_stem=artifact_stem,
                        display_label=display_label,
                    ),
                    data,
                )

    if single_attempt and candidate_file.exists():
        metadata = load_json(candidate_file)
        if metadata.get("candidate_fingerprint") == fingerprint:
            exhausted_file = session_dir / "recovery-exhausted.json"
            save_json(
                exhausted_file,
                {
                    "reason": f"{stem} attempt started without a complete transcript",
                    "artifact_file": candidate_file.name,
                    "candidate_fingerprint": fingerprint,
                },
            )
            raise RejectedRecoveryExhausted(
                f"The bounded {stem} attempt did not complete. See: {exhausted_file}"
            )
        # A marker for a different candidate only means the repository changed
        # since that attempt; the old call is stale, so start a fresh paid call
        # instead of consuming the bounded recovery budget.
        print(
            f"Stale {stem} attempt marker for a different candidate; "
            "starting a fresh call."
        )

    save_json(candidate_file, {"candidate_fingerprint": fingerprint})
    try:
        data = review(
            plan_file,
            task_file,
            verification_file,
            agent="reviewer_escalation" if sol else "reviewer",
            extra_files=extra_files,
            prompt=prompt,
            log_file=log_file,
        )
    except Exception as exc:
        if not single_attempt:
            raise
        # A nonzero opencode exit does not mean the model never answered:
        # permission denials or an aborted run can leave a complete paid
        # review in the transcript. Recover it before exhausting the budget.
        try:
            transcript = log_file.read_text(encoding="utf-8", errors="replace")
            data = parse_json_response(
                transcript,
                source=f"{stem} failed-run log",
            )
            validate_review(data)
            if review_transform is not None:
                review_transform(data)
        except RuntimeError:
            data = None
        if data is not None:
            data["candidate_fingerprint"] = fingerprint
            print(
                f"Recovered completed paid review from failed run: {log_file}"
            )
            return (
                save_and_print_review(
                    session_dir,
                    data,
                    round_number=round_number,
                    sol=sol,
                    artifact_stem=artifact_stem,
                    display_label=display_label,
                ),
                data,
            )
        exhausted_file = session_dir / "recovery-exhausted.json"
        save_json(
            exhausted_file,
            {
                "reason": f"{stem} call failed",
                "artifact_file": log_file.name,
                "candidate_fingerprint": fingerprint,
            },
        )
        raise RejectedRecoveryExhausted(
            f"The bounded {stem} call failed. See: {exhausted_file}"
        ) from exc
    data["candidate_fingerprint"] = fingerprint
    if review_transform is not None:
        review_transform(data)
    return (
        save_and_print_review(
            session_dir,
            data,
            round_number=round_number,
            sol=sol,
            artifact_stem=artifact_stem,
            display_label=display_label,
        ),
        data,
    )


def should_escalate_to_sol(
    *,
    changed_paths: list[str],
    changed_lines: int,
    tracked_file_count: int,
    plan: dict,
    verification_history: list[dict],
    luna_reviews: list[dict],
    latest_luna_review: dict,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    for concept, fragments in HIGH_RISK_PATH_RULES.items():
        if any(
            not path.startswith("docs/")
            and any(fragment in path.lower() for fragment in fragments)
            for path in changed_paths
        ):
            reasons.append(f"high-risk subsystem changed: {concept}")

    plan_text = json.dumps(
        {
            "design": plan.get("design", ""),
            "risks": plan.get("risks", []),
            "acceptance_criteria": plan.get("acceptance_criteria", []),
        },
        sort_keys=True,
    ).lower()
    for concept, terms in HIGH_RISK_PLAN_TERMS.items():
        if any(term in plan_text for term in terms):
            reasons.append(f"architect identified high-risk concept: {concept}")

    if changed_lines > 300:
        reasons.append(f"change size exceeds 300 lines: {changed_lines}")
    if tracked_file_count > 8:
        reasons.append(f"change spans more than 8 tracked files: {tracked_file_count}")

    if any(
        check.get("required")
        and check.get("status") in {"FAIL", "TIMEOUT"}
        for report in verification_history
        for check in report.get("checks", [])
    ):
        reasons.append("required verification failed earlier in this session")

    if any(
        any(issue.get("severity") == "CRITICAL" for issue in review.get("issues", []))
        for review in luna_reviews
    ):
        reasons.append("a cheap review reported a CRITICAL issue")
    if any(
        sum(issue.get("severity") == "MAJOR" for issue in review.get("issues", [])) >= 2
        for review in luna_reviews
    ):
        reasons.append("a cheap review reported at least two MAJOR issues")
    if latest_luna_review.get("uncertainty") == "HIGH":
        reasons.append("reviewer uncertainty is HIGH")

    # Preserve deterministic order while removing overlapping-rule duplicates.
    reasons = list(dict.fromkeys(reasons))
    return bool(reasons), reasons


def write_escalation_decision(
    session_dir: Path,
    fingerprint: str,
    escalated: bool,
    reasons: list[str],
) -> Path:
    path = session_dir / "escalation.json"
    save_json(
        path,
        {
            "escalated": escalated,
            "reasons": reasons,
            "candidate_fingerprint": fingerprint,
        },
    )
    print()
    print(f"===== ESCALATION REQUIRED: {'YES' if escalated else 'NO'} =====")
    if reasons:
        for reason in reasons:
            print(f"- {reason}")
    else:
        print("No deterministic escalation rule matched.")
    print(f"Decision: {path}")
    print()
    return path


def run_verification_cycle(
    *,
    plan: dict,
    plan_file: Path,
    task_file: Path,
    session_dir: Path,
    phase: str,
) -> tuple[bool, Path]:
    verification_file: Path | None = None

    # Initial verification plus up to MAX_IMPLEMENTATION_RETRIES repair attempts.
    for attempt in range(1, MAX_IMPLEMENTATION_RETRIES + 2):
        verification = run_verification(
            plan,
            costs_to_run={"cheap"},
        )
        verification["candidate_fingerprint"] = candidate_fingerprint(
            context_files=(task_file, plan_file)
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


def finish_accepted(session_dir: Path, review_round: int) -> int:
    snapshot_git_state(session_dir, f"{review_round + 1:02d}-accepted")
    print()
    print("===== ACCEPTED =====")
    print(f"Latest review round: {review_round}")
    print(f"Session data:       {session_dir}")
    print()
    print("No commit was created.")
    print("Inspect the final diff manually before committing:")
    print("  git status --short")
    print("  git diff")
    return 0


def latest_rejected_luna_review(
    session_dir: Path,
) -> tuple[int, Path, dict] | None:
    reviews = existing_review_rounds(session_dir)
    if not reviews:
        return None
    latest = reviews[-1]
    if latest[0] < MAX_REVIEW_ROUNDS or latest[2]["verdict"] != "FIX":
        return None
    return latest


def reject_after_semantic_limit(
    *,
    session_dir: Path,
    review_round: int,
    review_file: Path,
    review_data: dict,
    fingerprint: str,
    allow_expensive: bool,
) -> int:
    rejection_path = session_dir / "semantic-rejection.json"
    if rejection_path.exists():
        previous = load_json(rejection_path)
        allow_expensive = allow_expensive or previous.get("allow_expensive") is True
    severities = {
        issue.get("severity")
        for issue in review_data.get("issues", [])
        if issue.get("severity") in {"CRITICAL", "MAJOR"}
    }
    issue_label = "/".join(sorted(severities)) or "blocking"
    save_json(
        rejection_path,
        {
            "reason": "semantic_review_limit",
            "review_round": review_round,
            "review_file": str(review_file.relative_to(session_dir)),
            "candidate_fingerprint": fingerprint,
            "recovery_available": True,
            "allow_expensive": allow_expensive,
        },
    )

    print()
    print("===== NOT ACCEPTED =====")
    print()
    print("Reason:")
    print(
        f"Semantic review still reports {issue_label} issues after "
        f"{review_round} review rounds."
    )
    print()
    print("ELI5:")
    print(review_data["eli5_summary"].strip())
    print()
    print("Recommended next step:")
    print("Run:")
    expensive_flag = " --allow-expensive" if allow_expensive else ""
    print(
        f"  python3 tools/ai_cycle.py --resume {session_dir} "
        f"--continue-rejected{expensive_flag}"
    )
    print()
    print("This uses the escalation reviewer to adjudicate the remaining disagreement.")
    print("The existing Architect plan will NOT be regenerated.")
    return 2


def ensure_cheap_candidate_verification(
    *,
    plan: dict,
    plan_file: Path,
    task_file: Path,
    session_dir: Path,
    phase: str,
) -> tuple[bool, Path, str]:
    fingerprint = candidate_fingerprint(context_files=(task_file, plan_file))
    existing = matching_verification_report(
        session_dir, fingerprint, {"cheap"}
    )
    if existing is not None:
        verification_file, verification = existing
        print(f"Reusing cheap verification for unchanged candidate: {verification_file}")
        return verification.get("required_checks_passed") is True, verification_file, fingerprint

    verification = run_verification(plan, costs_to_run={"cheap"})
    fingerprint = candidate_fingerprint(context_files=(task_file, plan_file))
    verification["candidate_fingerprint"] = fingerprint
    verification_file = session_dir / f"{phase}-verification-1.json"
    save_json(
        verification_file,
        verification,
    )
    return (
        verification["required_checks_passed"],
        verification_file,
        fingerprint,
    )


def exhaust_rejected_recovery(
    *,
    session_dir: Path,
    reason: str,
    candidate_fingerprint_value: str,
    artifact_file: Path,
) -> int:
    path = session_dir / "recovery-exhausted.json"
    save_json(
        path,
        {
            "reason": reason,
            "artifact_file": str(artifact_file.relative_to(session_dir)),
            "candidate_fingerprint": candidate_fingerprint_value,
        },
    )
    print()
    print("===== NOT ACCEPTED =====")
    print("The one additional rejected-session recovery cycle is exhausted.")
    print(f"Reason: {reason}")
    print(f"See: {artifact_file}")
    return 2


def normalize_recovery_final_eli5(review_data: dict) -> None:
    if review_data.get("verdict") != "FIX":
        return
    review_data["eli5_summary"] = (
        "The escalation reviewer found a blocking issue. The one automated recovery cycle is "
        "exhausted, so manual intervention or architecture revision comes next."
    )


def run_recovery_final_gate(
    *,
    plan: dict,
    session_dir: Path,
    fingerprint: str,
    allow_expensive: bool,
) -> tuple[bool, Path]:
    if not allow_expensive:
        report = run_verification(plan, costs_to_run=set())
        report["candidate_fingerprint"] = fingerprint
        report["expensive_gate_enabled"] = False
        path = session_dir / "recovery-final-expensive-verification-disabled.json"
        save_json(path, report)
        print("Final expensive verification not enabled; recorded as not run.")
        return True, path

    existing = matching_verification_report(
        session_dir, fingerprint, {"expensive"}
    )
    if existing is not None:
        existing_file, existing_report = existing
        print(
            "Reusing final expensive verification for unchanged candidate: "
            f"{existing_file}"
        )
        return existing_report.get("required_checks_passed") is True, existing_file

    report = run_verification(plan, costs_to_run={"expensive"})
    report["candidate_fingerprint"] = fingerprint
    report["expensive_gate_enabled"] = True
    attempt = len(list(session_dir.glob("recovery-final-expensive-verification-*.json"))) + 1
    path = session_dir / f"recovery-final-expensive-verification-{attempt}.json"
    save_json(path, report)
    return report["required_checks_passed"], path


def reset_incomplete_recovery(session_dir: Path) -> list[str]:
    """Manually clear only interrupted recovery attempts.

    Explicit escape hatch for the durable single-attempt markers: a token
    outage or transient failure can consume the bounded recovery budget even
    though the attempt never produced a verdict. Completed artifacts are
    preserved so paid calls are not repeated.
    """
    cleared: list[str] = []

    exhausted_file = session_dir / "recovery-exhausted.json"
    if exhausted_file.exists():
        exhausted_file.unlink()
        cleared.append(exhausted_file.name)

    for stem in ("recovery-adjudication", "recovery-review", "recovery-sol-review"):
        if (session_dir / f"{stem}.json").exists():
            continue
        for suffix in ("-candidate.json", ".log"):
            path = session_dir / f"{stem}{suffix}"
            if path.exists():
                path.unlink()
                cleared.append(path.name)

    fix_source = session_dir / "recovery-fix-1-source.json"
    fix_summary = session_dir / "recovery-fix-1.md"
    if fix_source.exists() and not fix_summary.exists():
        for name in ("recovery-fix-1-source.json", "recovery-fix-1.log"):
            path = session_dir / name
            if path.exists():
                path.unlink()
                cleared.append(name)

    return cleared


def continue_rejected_workflow(
    *,
    plan: dict,
    plan_file: Path,
    task_file: Path,
    session_dir: Path,
    allow_expensive: bool,
) -> int:
    rejected = latest_rejected_luna_review(session_dir)
    if rejected is None:
        raise RuntimeError(
            "--continue-rejected requires a session whose latest review "
            f"is FIX at or beyond the {MAX_REVIEW_ROUNDS}-round limit."
        )

    rejected_round, rejected_file, _ = rejected
    fingerprint = candidate_fingerprint(context_files=(task_file, plan_file))
    complete_file = session_dir / "recovery-complete.json"
    if complete_file.exists():
        complete = load_json(complete_file)
        if complete.get("candidate_fingerprint") == fingerprint:
            print("Rejected-session recovery already completed for this candidate.")
            return finish_accepted(session_dir, rejected_round)

    exhausted_file = session_dir / "recovery-exhausted.json"
    if exhausted_file.exists():
        print()
        print("===== NOT ACCEPTED =====")
        print("The one additional rejected-session recovery cycle is exhausted.")
        print(f"See: {exhausted_file}")
        return 2

    original_reviews = [path for _, path, _ in existing_review_rounds(session_dir)]
    recovery_fix_log = session_dir / "recovery-fix-1.log"
    recovery_fix_summary = session_dir / "recovery-fix-1.md"
    recovery_fix_source = session_dir / "recovery-fix-1-source.json"
    fix_used = recovery_fix_source.exists()
    if fix_used:
        recover_completed_implementer_summary(
            recovery_fix_log, recovery_fix_summary
        )

    if not fix_used:
        ok, verification_file, fingerprint = ensure_cheap_candidate_verification(
            plan=plan,
            plan_file=plan_file,
            task_file=task_file,
            session_dir=session_dir,
            phase="recovery-adjudication-cheap",
        )
        if not ok:
            return exhaust_rejected_recovery(
                session_dir=session_dir,
                reason="required cheap verification failed before escalation adjudication",
                candidate_fingerprint_value=fingerprint,
                artifact_file=verification_file,
            )

        adjudication_prompt = """
This is a manual-intervention adjudication after the ordinary cheap reviewer
returned FIX through its bounded review limit. The cheaper reviewer did NOT
return PASS.

Read the task, unchanged architecture plan, latest cheap verification report,
all prior reviews, and the current repository diff/code. Decide whether
the remaining objections are legitimate.

Return PASS if the current code is actually acceptable despite the cheap
reviewer's objections. Return FIX only for legitimate remaining problems, with the
minimal precise fix required. Be especially alert for a confused, repetitive,
or contradictory prior review. Do not repeat style observations and do not
modify files. Return only the required JSON review object.
""".strip()
        adjudication_file, adjudication = obtain_review(
            session_dir=session_dir,
            plan_file=plan_file,
            task_file=task_file,
            verification_file=verification_file,
            fingerprint=fingerprint,
            round_number=1,
            sol=True,
            extra_files=original_reviews,
            artifact_stem="recovery-adjudication",
            display_label="ESCALATION ADJUDICATION",
            prompt=adjudication_prompt,
            single_attempt=True,
        )

        if adjudication["verdict"] == "PASS":
            final_ok, final_file = run_recovery_final_gate(
                plan=plan,
                session_dir=session_dir,
                fingerprint=fingerprint,
                allow_expensive=allow_expensive,
            )
            if final_ok:
                save_json(
                    complete_file,
                    {
                        "candidate_fingerprint": fingerprint,
                        "accepted_by": "escalation adjudication",
                    },
                )
                return finish_accepted(session_dir, rejected_round)
            fix_source_file = final_file
            save_json(
                recovery_fix_source,
                {
                    "source": str(fix_source_file.relative_to(session_dir)),
                    "candidate_fingerprint_before_fix": fingerprint,
                },
            )
            fix_result = fix_verification(
                plan_file,
                task_file,
                final_file,
                log_file=recovery_fix_log,
            )
        else:
            fix_source_file = adjudication_file
            save_json(
                recovery_fix_source,
                {
                    "source": str(fix_source_file.relative_to(session_dir)),
                    "candidate_fingerprint_before_fix": fingerprint,
                },
            )
            fix_result = fix_review(
                plan_file,
                task_file,
                adjudication_file,
                log_file=recovery_fix_log,
            )

        save(recovery_fix_summary, extract_final_markdown(fix_result))
        snapshot_git_state(session_dir, "recovery-after-fix-1")

    ok, verification_file, fingerprint = ensure_cheap_candidate_verification(
        plan=plan,
        plan_file=plan_file,
        task_file=task_file,
        session_dir=session_dir,
        phase="recovery-post-fix-cheap",
    )
    if not ok:
        return exhaust_rejected_recovery(
            session_dir=session_dir,
            reason="required cheap verification failed after the recovery fix",
            candidate_fingerprint_value=fingerprint,
            artifact_file=verification_file,
        )

    recovery_luna_file, _ = obtain_review(
        session_dir=session_dir,
        plan_file=plan_file,
        task_file=task_file,
        verification_file=verification_file,
        fingerprint=fingerprint,
        round_number=1,
        artifact_stem="recovery-review",
        display_label="RECOVERY LUNA REVIEW",
        extra_files=[rejected_file, session_dir / "recovery-adjudication.json"],
        single_attempt=True,
    )

    final_sol_prompt = """
This is the final escalation audit in a one-cycle recovery after the ordinary
review limit was reached. Independently inspect the current repository
diff/code and adjudicate the attached recovery review as well as all prior
evidence. A cheap-review FIX is not automatically authoritative, but return
FIX if any legitimate blocking issue remains. Return PASS only if this
candidate can proceed to final verification. Do not modify files or repeat
style observations.
If returning FIX, the ELI5 must say that the one automated recovery cycle is
exhausted and manual intervention or architecture revision comes next; do not
claim that another automatic implementer fix will run.
Return only the required JSON review object.
""".strip()
    recovery_sol_file, recovery_sol = obtain_review(
        session_dir=session_dir,
        plan_file=plan_file,
        task_file=task_file,
        verification_file=verification_file,
        fingerprint=fingerprint,
        round_number=1,
        sol=True,
        artifact_stem="recovery-sol-review",
        display_label="RECOVERY ESCALATION AUDIT",
        prompt=final_sol_prompt,
        review_transform=normalize_recovery_final_eli5,
        single_attempt=True,
        extra_files=[
            *original_reviews,
            session_dir / "recovery-adjudication.json",
            recovery_luna_file,
        ],
    )
    if recovery_sol["verdict"] == "FIX":
        save_json(
            exhausted_file,
            {
                "reason": "escalation final audit returned FIX",
                "review_file": str(recovery_sol_file.relative_to(session_dir)),
                "candidate_fingerprint": fingerprint,
            },
        )
        print()
        print("===== NOT ACCEPTED =====")
        print("The one additional rejected-session recovery cycle is exhausted.")
        print("ELI5:")
        print(recovery_sol["eli5_summary"].strip())
        print(f"Technical review: {recovery_sol_file}")
        return 2

    final_ok, final_file = run_recovery_final_gate(
        plan=plan,
        session_dir=session_dir,
        fingerprint=fingerprint,
        allow_expensive=allow_expensive,
    )
    if not final_ok:
        save_json(
            exhausted_file,
            {
                "reason": "final expensive verification failed after recovery fix",
                "verification_file": str(final_file.relative_to(session_dir)),
                "candidate_fingerprint": fingerprint,
            },
        )
        print("===== NOT ACCEPTED =====")
        print(f"Final expensive verification failed. See: {final_file}")
        return 2


    save_json(
        complete_file,
        {
            "candidate_fingerprint": fingerprint,
            "accepted_by": "recovery review plus escalation final audit",
        },
    )
    return finish_accepted(session_dir, rejected_round)


def complete_candidate_workflow(
    *,
    plan: dict,
    plan_file: Path,
    task_file: Path,
    session_dir: Path,
    allow_expensive: bool,
) -> int:
    for log_file in session_dir.glob("expensive-fix-*.log"):
        recover_completed_implementer_summary(
            log_file, log_file.with_suffix(".md")
        )
    expensive_repairs = len(list(session_dir.glob("expensive-fix-*.md")))

    while True:
        fingerprint = candidate_fingerprint(context_files=(task_file, plan_file))
        verification_file = matching_successful_verification(
            session_dir, fingerprint, {"cheap"}
        )
        if verification_file is None:
            phase = f"cheap-{dt.datetime.now().strftime('%H%M%S%f')}"
            verification_ok, verification_file = run_verification_cycle(
                plan=plan,
                plan_file=plan_file,
                task_file=task_file,
                session_dir=session_dir,
                phase=phase,
            )
            if not verification_ok:
                snapshot_git_state(session_dir, "99-cheap-verification-failed")
                print()
                print("===== NOT ACCEPTED =====")
                print(f"Required cheap verification failed. See: {verification_file}")
                return 2
            fingerprint = candidate_fingerprint(
                context_files=(task_file, plan_file)
            )
        else:
            print(f"Reusing cheap verification for unchanged candidate: {verification_file}")

        luna_rounds = existing_review_rounds(session_dir)
        luna_match = matching_review(luna_rounds, fingerprint)
        if luna_match is not None and luna_match[2]["verdict"] == "FIX":
            if luna_match[0] >= MAX_REVIEW_ROUNDS:
                return reject_after_semantic_limit(
                    session_dir=session_dir,
                    review_round=luna_match[0],
                    review_file=luna_match[1],
                    review_data=luna_match[2],
                    fingerprint=fingerprint,
                    allow_expensive=allow_expensive,
                )
            fix_log = session_dir / f"review-fix-{luna_match[0]}.log"
            fix_summary = session_dir / f"review-fix-{luna_match[0]}.md"
            if not recover_completed_implementer_summary(fix_log, fix_summary):
                fix_result = fix_review(
                    plan_file,
                    task_file,
                    luna_match[1],
                    log_file=fix_log,
                )
                save(
                    fix_summary,
                    extract_final_markdown(fix_result),
                )
                snapshot_git_state(
                    session_dir, f"review-{luna_match[0]}-after-fix"
                )
                continue
            luna_match = None

        if luna_match is None:
            luna_round = (luna_rounds[-1][0] + 1) if luna_rounds else 1
            if luna_round > MAX_REVIEW_ROUNDS:
                rejected = latest_rejected_luna_review(session_dir)
                if rejected is None:
                    raise RuntimeError(
                        "review limit reached without a reusable FIX review."
                    )
                return reject_after_semantic_limit(
                    session_dir=session_dir,
                    review_round=rejected[0],
                    review_file=rejected[1],
                    review_data=rejected[2],
                    fingerprint=fingerprint,
                    allow_expensive=allow_expensive,
                )
            review_file, review_data = obtain_review(
                session_dir=session_dir,
                plan_file=plan_file,
                task_file=task_file,
                verification_file=verification_file,
                fingerprint=fingerprint,
                round_number=luna_round,
            )
            luna_match = (luna_round, review_file, review_data)
        else:
            print(
                "Reusing review for unchanged candidate: "
                f"{luna_match[1]}"
            )

        luna_round, luna_file, luna_data = luna_match
        if luna_data["verdict"] == "FIX":
            if luna_round >= MAX_REVIEW_ROUNDS:
                return reject_after_semantic_limit(
                    session_dir=session_dir,
                    review_round=luna_round,
                    review_file=luna_file,
                    review_data=luna_data,
                    fingerprint=fingerprint,
                    allow_expensive=allow_expensive,
                )
            fix_result = fix_review(
                plan_file,
                task_file,
                luna_file,
                log_file=session_dir / f"review-fix-{luna_round}.log",
            )
            save(
                session_dir / f"review-fix-{luna_round}.md",
                extract_final_markdown(fix_result),
            )
            snapshot_git_state(session_dir, f"review-{luna_round}-after-fix")
            continue

        paths, changed_lines, tracked_files = changed_diff_stats()
        reports = [data for _, data in verification_reports(session_dir)]
        all_luna_data = [data for _, _, data in existing_review_rounds(session_dir)]
        escalated, reasons = should_escalate_to_sol(
            changed_paths=paths,
            changed_lines=changed_lines,
            tracked_file_count=tracked_files,
            plan=plan,
            verification_history=reports,
            luna_reviews=all_luna_data,
            latest_luna_review=luna_data,
        )
        prior_escalation_file = session_dir / "escalation.json"
        if prior_escalation_file.exists():
            prior_escalation = load_json(prior_escalation_file)
            if prior_escalation.get("escalated") is True and not escalated:
                escalated = True
                reasons.append("task was previously classified high-risk")
        escalation_file = write_escalation_decision(
            session_dir, fingerprint, escalated, reasons
        )

        if escalated:
            sol_rounds = existing_sol_review_rounds(session_dir)
            sol_match = matching_review(sol_rounds, fingerprint)
            if sol_match is not None and sol_match[2]["verdict"] == "FIX":
                sol_fix_log = session_dir / f"sol-review-fix-{sol_match[0]}.log"
                sol_fix_summary = session_dir / f"sol-review-fix-{sol_match[0]}.md"
                if not recover_completed_implementer_summary(
                    sol_fix_log, sol_fix_summary
                ):
                    fix_result = fix_review(
                        plan_file,
                        task_file,
                        sol_match[1],
                        log_file=sol_fix_log,
                    )
                    save(
                        sol_fix_summary,
                        extract_final_markdown(fix_result),
                    )
                    snapshot_git_state(
                        session_dir, f"sol-review-{sol_match[0]}-after-fix"
                    )
                    continue
                sol_match = None

            if sol_match is None:
                sol_round = (sol_rounds[-1][0] + 1) if sol_rounds else 1
                if sol_round > MAX_SOL_REVIEW_ROUNDS:
                    print()
                    print("===== NOT ACCEPTED =====")
                    print(
                        f"The session used all {MAX_SOL_REVIEW_ROUNDS} escalation "
                        "review rounds."
                    )
                    return 2
                sol_file, sol_data = obtain_review(
                    session_dir=session_dir,
                    plan_file=plan_file,
                    task_file=task_file,
                    verification_file=verification_file,
                    fingerprint=fingerprint,
                    round_number=sol_round,
                    sol=True,
                    extra_files=[luna_file, escalation_file],
                )
                sol_match = (sol_round, sol_file, sol_data)
            else:
                print(
                    "Reusing escalation review for unchanged candidate: "
                    f"{sol_match[1]}"
                )

            if sol_match[2]["verdict"] == "FIX":
                fix_result = fix_review(
                    plan_file,
                    task_file,
                    sol_match[1],
                    log_file=session_dir / f"sol-review-fix-{sol_match[0]}.log",
                )
                save(
                    session_dir / f"sol-review-fix-{sol_match[0]}.md",
                    extract_final_markdown(fix_result),
                )
                snapshot_git_state(
                    session_dir, f"sol-review-{sol_match[0]}-after-fix"
                )
                continue

        if not allow_expensive:
            final_report = run_verification(plan, costs_to_run=set())
            final_report["candidate_fingerprint"] = fingerprint
            final_report["expensive_gate_enabled"] = False
            final_file = session_dir / "final-expensive-verification-disabled.json"
            save_json(final_file, final_report)
            print("Final expensive verification not enabled; recorded as not run.")
            return finish_accepted(session_dir, luna_round)

        expensive_file = matching_successful_verification(
            session_dir, fingerprint, {"expensive"}
        )
        if expensive_file is not None:
            print(
                "Reusing final expensive verification for unchanged candidate: "
                f"{expensive_file}"
            )
            return finish_accepted(session_dir, luna_round)

        expensive = run_verification(plan, costs_to_run={"expensive"})
        expensive["candidate_fingerprint"] = fingerprint
        expensive["expensive_gate_enabled"] = True
        attempt = expensive_repairs + 1
        expensive_file = session_dir / f"final-expensive-verification-{attempt}.json"
        save_json(expensive_file, expensive)
        if expensive["required_checks_passed"]:
            return finish_accepted(session_dir, luna_round)

        if expensive_repairs >= MAX_EXPENSIVE_REPAIRS:
            print()
            print("===== NOT ACCEPTED =====")
            print(f"Final expensive verification failed. See: {expensive_file}")
            return 2

        expensive_repairs += 1
        fix_result = fix_verification(
            plan_file,
            task_file,
            expensive_file,
            log_file=session_dir / f"expensive-fix-{expensive_repairs}.log",
        )
        save(
            session_dir / f"expensive-fix-{expensive_repairs}.md",
            extract_final_markdown(fix_result),
        )
        snapshot_git_state(
            session_dir, f"after-expensive-fix-{expensive_repairs}"
        )
        # Never rerun the expensive check directly after edits. The next loop
        # starts with cheap verification and fresh semantic acceptance.


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run or resume the GPT architect -> DeepSeek implementer -> "
            "cheap verification -> review -> optional escalation audit -> "
            "final expensive verification workflow."
        )
    )

    parser.add_argument(
        "--allow-expensive",
        action="store_true",
        help=(
            "Execute checks marked cost=expensive only as the final gate after "
            "semantic review. Without this flag they are recorded as not run."
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
        "--continue-rejected",
        action="store_true",
        help=(
            "Use one bounded escalation-adjudicated recovery cycle for a resumed "
            "session that exhausted ordinary review rounds."
        ),
    )

    parser.add_argument(
        "--retry-recovery",
        action="store_true",
        help=(
            "With --resume and --continue-rejected: clear only interrupted "
            "recovery attempts so a token outage or transient failure does "
            "not consume the bounded recovery budget. Completed reviews, "
            "fixes, and verification reports are preserved."
        ),
    )

    parser.add_argument(
        "task",
        nargs="*",
        help="Description of the requested repository change",
    )

    args = parser.parse_args()

    if args.continue_rejected and not args.resume:
        parser.error("--continue-rejected requires --resume SESSION.")
    if args.retry_recovery and not (args.resume and args.continue_rejected):
        parser.error("--retry-recovery requires --resume SESSION --continue-rejected.")

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

        if args.continue_rejected:
            if args.retry_recovery:
                cleared = reset_incomplete_recovery(session_dir)
                if cleared:
                    print()
                    print("===== RECOVERY RETRY RESET =====")
                    print("Cleared interrupted recovery attempt artifacts:")
                    for name in cleared:
                        print(f"- {name}")
                    print()
                else:
                    print("No interrupted recovery artifacts found to clear.")

            effective_allow_expensive = args.allow_expensive
            rejection_file = session_dir / "semantic-rejection.json"
            if rejection_file.exists():
                rejection = load_json(rejection_file)
                effective_allow_expensive = (
                    effective_allow_expensive
                    or rejection.get("allow_expensive") is True
                )
            return continue_rejected_workflow(
                plan=plan,
                plan_file=plan_file,
                task_file=task_file,
                session_dir=session_dir,
                allow_expensive=effective_allow_expensive,
            )

        # A resumed cycle is expected to have tracked task changes already,
        # so ensure_safe_start() must deliberately NOT run here.
        implementation_log = session_dir / "implementation-1.log"
        implementation_summary = session_dir / "implementation-1.md"

        if not recover_completed_implementer_summary(
            implementation_log, implementation_summary
        ):
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
                implementation_summary,
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

        return complete_candidate_workflow(
            plan=plan,
            plan_file=plan_file,
            task_file=task_file,
            session_dir=session_dir,
            allow_expensive=args.allow_expensive,
        )

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

    return complete_candidate_workflow(
        plan=plan,
        plan_file=plan_file,
        task_file=task_file,
        session_dir=session_dir,
        allow_expensive=args.allow_expensive,
    )

if __name__ == "__main__":
    try:
        return_code = main()
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return_code = 130
    except RejectedRecoveryExhausted as exc:
        print("\n===== NOT ACCEPTED =====", file=sys.stderr)
        print(str(exc), file=sys.stderr)
        return_code = 2
    except Exception as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return_code = 1

    print_cycle_cost_summary()
    raise SystemExit(return_code)
