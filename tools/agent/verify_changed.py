#!/usr/bin/env python3
"""Run the verification tier that a change needs, chosen from its changed paths.

Tiers (the highest one any changed path needs wins; see AGENTS.md "Verification tiers"):

  docs    docs/ and other Markdown only: repository health only.
  python  Python/shell tooling only (tools/, tests/*.py, *.sh, ...): repository health, the test modules that
          name a changed module, and the CTest entries whose command names a changed file (when a build exists).
          No C++ build.
  native  Anything compiled (src/, include/, apps/, bindings/, tests/*.cpp, CMake, submodules): everything above,
          plus an incremental Debug build in build/linux-gcc-debug (reused, never wiped) and
          `ctest -L 'core|smoke'` in parallel with a per-test timeout. This is the CI gate.

`--tier native` forces the CI gate, e.g. for engine fixes and default changes. Release builds are never part of
verification: they add -O3 -flto (about 30 minutes on 4 cores) and test nothing the Debug gate does not.

  python3 tools/agent/verify_changed.py                 # diff against origin/main, run the needed tier
  python3 tools/agent/verify_changed.py --dry-run       # print the plan only
  python3 tools/agent/verify_changed.py --tier native   # engine fix / default change: full CI gate
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TIERS = ("docs", "python", "native")
NATIVE_PREFIXES = ("src/", "include/", "apps/", "bindings/", "cmake/", "json", "pybind11")
NATIVE_FILES = ("CMakeLists.txt", "CMakePresets.json", ".gitmodules")
NATIVE_SUFFIXES = (".cpp", ".cc", ".h", ".hpp", ".cmake")
# Pre-existing flaky or slow tests (project memory, 2026-11-22). A timeout or failure here is reported as such.
KNOWN_FLAKY = ("test_run_train_resume", "az_eval_cache_ema_amber", "az_eval_cache_compact")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def changed_paths(base: str) -> list[str]:
    merge_base = git("merge-base", base, "HEAD").strip()
    paths = set(git("diff", "--name-only", merge_base).split())          # committed + staged + unstaged
    paths |= set(git("ls-files", "--others", "--exclude-standard").split())  # new untracked files
    return sorted(paths)


def tier_of(path: str) -> str:
    if path in NATIVE_FILES or path.startswith(NATIVE_PREFIXES) or path.endswith(NATIVE_SUFFIXES):
        return "native"
    if path.startswith("docs/") or path.endswith((".md", ".txt")):
        return "docs"
    return "python"


def affected_test_modules(paths: list[str]) -> list[str]:
    """tests/**/test_*.py that changed, or that name a changed .py/.sh file or import its module."""
    tests = sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").rglob("test_*.py"))
    picked = {p for p in paths if p in tests}
    stems = {Path(p).stem for p in paths if p.endswith((".py", ".sh")) and p not in tests and (ROOT / p).exists()}
    stems.discard("__init__")
    if stems:
        alt = "|".join(map(re.escape, sorted(stems)))
        # A file name (selfplay.py), an import (import/from selfplay, tools.az_bench.selfplay), not a bare word.
        pat = re.compile(rf"\b({alt})\.(py|sh)\b|\bimport\s+({alt})\b|\bfrom\s+(\w+\.)*({alt})\s+import\b"
                         rf"|\b\w+\.({alt})\b(?!\.(py|sh))")
        for t in tests:
            if pat.search((ROOT / t).read_text(errors="replace")):
                picked.add(t)
    return sorted(picked)


def affected_ctests(paths: list[str], build_dir: Path) -> list[str]:
    """CTest entries whose command line names a changed file (path or module stem)."""
    if not (build_dir / "CTestTestfile.cmake").exists():
        return []
    out = subprocess.run(["ctest", "--test-dir", str(build_dir), "--show-only=json-v1"],
                         capture_output=True, text=True, check=True).stdout
    keys = [p for p in paths if (ROOT / p).is_file()]
    keys += [Path(p).with_suffix("").as_posix().replace("/", ".") for p in keys if p.endswith(".py")]
    names = []
    for t in json.loads(out).get("tests", []):
        cmd = " ".join(t.get("command", []))
        if any(k in cmd for k in keys):
            names.append(t["name"])
    return names


def repo_health(base: str, paths: list[str]) -> str:
    """tools/repo_health.py, failing only on what this change adds: main itself may carry broken doc links."""
    proc = subprocess.run([sys.executable, "tools/repo_health.py", "--baseline", base, "--json"], cwd=ROOT,
                          capture_output=True, text=True)
    try:
        hard = json.loads(proc.stdout)["hard_failures"]
    except (json.JSONDecodeError, KeyError):
        print(proc.stdout, proc.stderr)
        return f"FAIL (exit {proc.returncode}, no report)"
    links = hard.pop("broken_current_documentation_references", [])
    new = [b for b in links if b["source"] in set(paths)]
    for key, items in list(hard.items()) + [("broken_current_documentation_references", new)]:
        for item in items:
            print(f"  {key}: {item}")
    if len(links) > len(new):
        print(f"  ({len(links) - len(new)} broken doc link(s) in files this change does not touch: pre-existing, ignored)")
    return "FAIL" if hard or new else "PASS"


def run(label: str, cmd, timeout: float | None = None) -> tuple[str, float]:
    print(f"\n=== {label}" + ("" if callable(cmd) else f"\n$ {' '.join(cmd)}"), flush=True)
    t0 = time.monotonic()
    try:
        if callable(cmd):
            status = cmd()
        else:
            rc = subprocess.run(cmd, cwd=ROOT, timeout=timeout).returncode
            status = "PASS" if rc == 0 else f"FAIL (exit {rc})"
    except subprocess.TimeoutExpired:
        status = f"TIMEOUT after {timeout:.0f} s"
    dt = time.monotonic() - t0
    print(f"--- {label}: {status} in {dt:.0f} s", flush=True)
    return status, dt


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="origin/main", help="ref to diff against (default origin/main)")
    ap.add_argument("--tier", choices=("auto",) + TIERS, default="auto",
                    help="auto = from changed paths; native = full CI gate (engine fixes, default changes)")
    ap.add_argument("--build-dir", default="build/linux-gcc-debug", help="reused incremental Debug build directory")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2, help="build and ctest parallelism")
    ap.add_argument("--test-timeout", type=int, default=600, help="per CTest test seconds (default 600)")
    ap.add_argument("--module-timeout", type=int, default=900, help="per Python test module seconds (default 900)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    args = ap.parse_args(argv)

    paths = changed_paths(args.base)
    need = max((tier_of(p) for p in paths), key=TIERS.index, default="docs")
    tier = need if args.tier == "auto" else max(need, args.tier, key=TIERS.index)
    build_dir = ROOT / args.build_dir
    print(f"{len(paths)} changed path(s) vs {args.base}; tier needed: {need}; running: {tier}")
    for p in paths:
        print(f"  [{tier_of(p):6}] {p}")

    plan: list[tuple[str, object, float | None]] = [
        ("repository health", lambda: repo_health(args.base, paths), None)]
    ml = importlib.util.find_spec("torch") is not None
    if tier == "native":
        if not (build_dir / "CMakeCache.txt").exists():
            configure = ["cmake", "-S", ".", "-B", str(build_dir), "-DCMAKE_BUILD_TYPE=Debug", "-DCMAKE_CXX_COMPILER=g++"]
            if shutil.which("ccache"):
                configure.append("-DCMAKE_CXX_COMPILER_LAUNCHER=ccache")
            plan.append(("configure Debug (first time only)", configure, None))
        plan.append(("incremental Debug build", ["cmake", "--build", str(build_dir), "--parallel", str(args.jobs)], None))
        ctest = ["ctest", "--test-dir", str(build_dir), "-L", "core|smoke", "-j", str(args.jobs),
                 "--timeout", str(args.test_timeout), "--output-on-failure"]
        if not ml:
            ctest += ["-LE", "needs-ml-python"]
        plan.append(("ctest core|smoke (CI gate)", ctest, None))
    elif tier == "python":
        names = affected_ctests(paths, build_dir)
        if names:
            regex = "^(" + "|".join(map(re.escape, names)) + ")$"
            plan.append((f"affected ctest ({len(names)})", ["ctest", "--test-dir", str(build_dir), "-R", regex, "-j",
                         str(args.jobs), "--timeout", str(args.test_timeout), "--output-on-failure"], None))
        elif not (build_dir / "CTestTestfile.cmake").exists():
            print(f"note: no build in {args.build_dir}; CTest entries that run changed tools are not selected")
    if tier in ("python", "native"):
        for mod in affected_test_modules(paths):
            plan.append((f"pytest {mod}", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", mod],
                         args.module_timeout))

    if args.dry_run:
        print("\nplan:")
        for label, cmd, _ in plan:
            print(f"  {label}" + ("" if callable(cmd) else f": {' '.join(cmd)}"))
        return 0
    results = [(label, *run(label, cmd, to)) for label, cmd, to in plan]
    print("\n=== summary")
    for label, status, dt in results:
        print(f"  {status:22} {dt:6.0f} s  {label}")
    if any(s != "PASS" for _, s, _ in results):
        print(f"Known flaky (pre-existing, report as such if they are the only failures): {', '.join(KNOWN_FLAKY)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
