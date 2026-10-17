#!/usr/bin/env python3
"""Assign ledger section (§) and ADR numbers when a PR is merged, not when it is written.

PRs write placeholders instead of numbers, in Markdown files:
  §TBD, §TBD-a, §TBD-b ...    ledger sections; each label gets one number. Every label needs exactly one ledger
                              heading line "## §TBD... — title" in a ledger shard (EXPERIMENTS.md or
                              docs/experiments/ledger-NN.md).
  ADR-TBD, ADR-TBD-a ...      ADR numbers (4 digits). The ADR file is decisions/TBD-<slug>.md; its first
                              ADR-TBD token says which label it is. Links to it use that file name.
Only changed *.md files are rewritten, and placeholders inside `code spans` or fenced code blocks are left alone,
so documentation can talk about the placeholders without being rewritten.

  assign [--base REF] [--skip 517-523] [--skip-adr 45,46] [--dry-run]
      Run on a clean PR branch right before merging, after the base (normally origin/main) is merged in.
      Numbers continue above the highest § heading / ADR file on the base and on the branch; --skip and
      --skip-adr list numbers reserved by work still in flight. Rewrites the placeholders and renames TBD ADR
      files in the working tree; commit the result as one commit.
  check REVIEWED NEW [--base REF] [--skip ...] [--skip-adr ...]
      Proves that NEW = (REVIEWED, or a clean automatic merge of REVIEWED with a base commit) + exactly the
      rewrite `assign` computes against REF with the same skip lists, and that REF is merged into NEW.
      Exit 0 means the review of REVIEWED still covers NEW. Use the same --skip/--skip-adr as the assign.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

SEC = re.compile(r"§TBD(?:-([a-z0-9]+))?\b")
ADR = re.compile(r"ADR-TBD(?:-([a-z0-9]+))?\b")
ADR_FILE = re.compile(r"^decisions/TBD-(.+\.md)$")
HEADING = re.compile(r"^#+ §(\d+)(?![\d-])", re.M)  # not the dated §2026-08-10 headings
TBD_HEADING = re.compile(r"^#+ §TBD(?:-([a-z0-9]+))?\b")
FENCE = re.compile(r"^\s*(```|~~~)")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def ok(*args: str) -> bool:
    return subprocess.run(["git", *args], capture_output=True).returncode == 0


def show(ref: str, path: str) -> str:
    return git("show", f"{ref}:{path}")


def is_ledger(path: str) -> bool:
    return path == "EXPERIMENTS.md" or re.fullmatch(r"docs/experiments/ledger-\d+\.md", path) is not None


def parse_skip(text: str) -> set[int]:
    out: set[int] = set()
    for part in filter(None, (p.strip() for p in (text or "").split(","))):
        lo, _, hi = part.partition("-")
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


def outside_code(text: str, fn) -> str:
    """Apply fn to the parts of a Markdown text that are not fenced blocks or `code spans`."""
    out, fenced = [], False
    for line in text.splitlines(keepends=True):
        if FENCE.match(line):
            fenced = not fenced
            out.append(line)
        elif fenced:
            out.append(line)
        else:
            parts = line.split("`")
            out.append("`".join(fn(p) if i % 2 == 0 else p for i, p in enumerate(parts)))
    return "".join(out)


def tokens(text: str, pat: re.Pattern) -> list[str]:
    found: list[str] = []
    outside_code(text, lambda p: found.extend(m.group(1) or "" for m in pat.finditer(p)) or p)
    return found


def max_section(ref: str) -> int:
    names = git("ls-tree", "-r", "--name-only", ref, "--", "EXPERIMENTS.md", "docs/experiments").split()
    return max((int(m.group(1)) for n in names if is_ledger(n) for m in HEADING.finditer(show(ref, n))), default=0)


def max_adr(ref: str) -> int:
    return max((int(m.group(1)) for n in git("ls-tree", "--name-only", ref, "decisions/").split()
                if (m := re.match(r"decisions/(\d{4})-", n))), default=0)


def next_free(start: int, count: int, skip: set[int]) -> list[int]:
    out, n = [], start
    while len(out) < count:
        n += 1
        if n not in skip:
            out.append(n)
    return out


def plan(base: str, ref: str, skip: set[int], skip_adr: set[int]):
    """Return (secs, adrs, renames, {path_at_ref: new_text}) for the placeholders in ref's changed *.md files."""
    changed = [f for f in git("diff", "--name-only", "--no-renames", "--diff-filter=AMR", f"{base}...{ref}").split()
               if f.endswith(".md")]
    texts = {f: show(ref, f) for f in changed}
    sec_order: list[str] = []
    for f in changed:
        if not is_ledger(f):
            continue
        fenced = False
        for line in texts[f].splitlines():
            if FENCE.match(line):
                fenced = not fenced
            elif not fenced and (m := TBD_HEADING.match(line)):
                lab = m.group(1) or ""
                if lab in sec_order:
                    raise SystemExit(f"two ledger headings use §TBD{'-' + lab if lab else ''}; give each its own label")
                sec_order.append(lab)
    used = {lab for t in texts.values() for lab in tokens(t, SEC)}
    if used - set(sec_order):
        raise SystemExit(f"§TBD labels without a ledger heading: {sorted(used - set(sec_order))}")
    secs = dict(zip(sec_order, next_free(max(max_section(base), max_section(ref)), len(sec_order), skip)))
    adr_files: dict[str, str] = {}
    for f in changed:
        if ADR_FILE.match(f):
            labs = tokens(texts[f], ADR)
            if not labs:
                raise SystemExit(f"{f} has no ADR-TBD token outside code")
            adr_files[f] = labs[0]
    labels = sorted(adr_files.values())
    if len(labels) != len(set(labels)):
        raise SystemExit("two TBD ADR files share a label; use ADR-TBD-a, ADR-TBD-b in their headings")
    for t in texts.values():
        for lab in tokens(t, ADR):
            if lab not in labels:
                raise SystemExit(f"ADR-TBD label '{lab}' has no decisions/TBD-*.md file")
    adrs = dict(zip(labels, next_free(max(max_adr(base), max_adr(ref)), len(labels), skip_adr)))
    renames = {f: f"decisions/{adrs[lab]:04d}-{ADR_FILE.match(f).group(1)}" for f, lab in adr_files.items()}

    def fix(part: str) -> str:
        part = SEC.sub(lambda m: f"§{secs[m.group(1) or '']}", part)
        part = ADR.sub(lambda m: f"ADR-{adrs[m.group(1) or '']:04d}", part)
        for old, new in renames.items():
            part = part.replace(os.path.basename(old), os.path.basename(new))
        return part

    rewritten = {f: outside_code(t, fix) for f, t in texts.items()}
    return secs, adrs, renames, {f: t for f, t in rewritten.items() if t != texts[f] or f in renames}


def report(secs: dict, adrs: dict, renames: dict) -> None:
    for lab, n in secs.items():
        print(f"§TBD{'-' + lab if lab else ''} -> §{n}")
    for lab, n in adrs.items():
        print(f"ADR-TBD{'-' + lab if lab else ''} -> ADR-{n:04d}")
    for old, new in renames.items():
        print(f"rename {old} -> {new}")


def cmd_assign(a) -> int:
    if not ok("merge-base", "--is-ancestor", a.base, "HEAD"):
        raise SystemExit(f"{a.base} is not merged into HEAD; merge it first")
    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise SystemExit("working tree has uncommitted changes; commit them first")
    secs, adrs, renames, new = plan(a.base, "HEAD", parse_skip(a.skip), parse_skip(a.skip_adr))
    if not new:
        print("no placeholders")
        return 0
    report(secs, adrs, renames)
    if a.dry_run:
        return 0
    for f, text in new.items():
        dest = renames.get(f, f)
        if dest != f:
            subprocess.run(["git", "mv", f, dest], check=True)
        with open(dest, "w") as fh:
            fh.write(text)
    print(f"done; commit, then reviewers run: python3 tools/ledger_assign.py check <reviewed> <new> --base {a.base}"
          + (f" --skip {a.skip}" if a.skip else "") + (f" --skip-adr {a.skip_adr}" if a.skip_adr else ""))
    return 0


def cmd_check(a) -> int:
    reviewed, new_c = git("rev-parse", a.reviewed).strip(), git("rev-parse", a.new).strip()
    parents = git("rev-list", "--parents", "-n", "1", new_c).split()[1:]
    if len(parents) != 1:
        raise SystemExit("NEW must be a single numbering commit")
    p = parents[0]
    if p != reviewed:
        pp = git("rev-list", "--parents", "-n", "1", p).split()[1:]
        if len(pp) != 2 or pp[0] != reviewed:
            raise SystemExit("NEW's parent is neither REVIEWED nor a merge of REVIEWED with a base commit")
        clean = subprocess.run(["git", "merge-tree", "--write-tree", reviewed, pp[1]], capture_output=True, text=True)
        if clean.returncode != 0 or clean.stdout.split()[0] != git("rev-parse", f"{p}^{{tree}}").strip():
            raise SystemExit("the base merge was not a clean automatic merge; it needs a delta review")
        if not ok("merge-base", "--is-ancestor", pp[1], a.base):
            raise SystemExit(f"the merged commit {pp[1][:12]} is not on {a.base}")
    if not ok("merge-base", "--is-ancestor", a.base, new_c):
        raise SystemExit(f"{a.base} is not merged into NEW; numbers may collide with entries merged since")
    secs, adrs, renames, expected = plan(a.base, p, parse_skip(a.skip), parse_skip(a.skip_adr))
    want = {renames.get(f, f): t for f, t in expected.items()}
    gone = set(renames)
    bad = []
    for line in git("diff", "--name-status", "--no-renames", p, new_c).splitlines():
        st, path = line.split("\t", 1)
        if st == "D" and path in gone:
            gone.discard(path)
        elif st in ("M", "A") and path in want:
            if show(new_c, path) != want.pop(path):
                bad.append(f"{path}: differs from the computed numbering")
        else:
            bad.append(f"{st} {path}: not part of the numbering")
    bad += [f"{f}: expected numbering change missing" for f in sorted(want)]
    bad += [f"{f}: expected rename missing" for f in sorted(gone)]
    report(secs, adrs, renames)
    if bad:
        print("not numbering-only:\n  " + "\n  ".join(bad))
        return 1
    print("numbering-only: OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    os.chdir(git("rev-parse", "--show-toplevel").strip())
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("assign", "check"):
        s = sub.add_parser(name)
        if name == "check":
            s.add_argument("reviewed")
            s.add_argument("new")
        else:
            s.add_argument("--dry-run", action="store_true")
        s.add_argument("--base", default="origin/main")
        s.add_argument("--skip", default="", help="reserved § numbers, e.g. 517-523")
        s.add_argument("--skip-adr", default="", help="reserved ADR numbers, e.g. 45,46")
    a = ap.parse_args(argv)
    return cmd_assign(a) if a.cmd == "assign" else cmd_check(a)


if __name__ == "__main__":
    sys.exit(main())
