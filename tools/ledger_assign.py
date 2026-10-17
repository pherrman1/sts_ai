#!/usr/bin/env python3
"""Assign ledger section (§) and ADR numbers when a PR is merged, not when it is written.

PRs write placeholders instead of numbers:
  §TBD, §TBD-a, §TBD-b ...    ledger sections; each distinct label gets one number. Every label needs a
                              ledger heading line "## §TBD... — title" in a ledger file.
  ADR-TBD, ADR-TBD-a ...      ADR numbers (4 digits). The ADR file is decisions/TBD-<slug>.md; its first
                              ADR-TBD token says which label it is. Links to it use that file name.

  assign  [--base REF] [--skip N,N...] [--dry-run]
      Run on the PR branch right before merging, after the base (normally origin/main) is merged in.
      Numbers continue from the highest § heading / ADR file on the base; --skip lists numbers that are reserved
      elsewhere. Rewrites the placeholders in every file the branch changed and renames TBD ADR files.
  check REVIEWED NEW [--base REF]
      Confirms that NEW differs from REVIEWED only by a clean merge of the base and by this numbering, so a
      reviewed PASS still covers NEW. Exit 0 = numbering-only.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

SEC = re.compile(r"§TBD(?:-([a-z0-9]+))?\b")
ADR = re.compile(r"ADR-TBD(?:-([a-z0-9]+))?\b")
ADR_FILE = re.compile(r"^decisions/TBD-(.+\.md)$")
HEADING = re.compile(r"^#+ §(\d+)(?![\d-])", re.M)  # not the dated §2026-08-10 headings
TBD_HEADING = re.compile(r"^#+ §TBD(?:-([a-z0-9]+))?\b", re.M)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def ledger_paths(ref: str) -> list[str]:
    names = git("ls-tree", "-r", "--name-only", ref, "--", "EXPERIMENTS.md", "docs/experiments").split()
    return [n for n in names if n == "EXPERIMENTS.md" or re.fullmatch(r"docs/experiments/ledger-\d+\.md", n)]


def max_section(ref: str) -> int:
    best = 0
    for p in ledger_paths(ref):
        for m in HEADING.finditer(git("show", f"{ref}:{p}")):
            best = max(best, int(m.group(1)))
    return best


def max_adr(ref: str) -> int:
    nums = [int(m.group(1)) for n in git("ls-tree", "--name-only", ref, "decisions/").split()
            if (m := re.match(r"decisions/(\d{4})-", n))]
    return max(nums, default=0)


def plan(base: str, skip: set[int]) -> tuple[dict, dict, list[str]]:
    """Return ({label: §n}, {label: adr n}, changed text files)."""
    changed = [f for f in git("diff", "--name-only", f"{base}...HEAD").split() if Path(f).is_file()]
    texts = {}
    for f in changed:
        try:
            texts[f] = Path(f).read_text()
        except UnicodeDecodeError:
            continue
    sec_order: list[str] = []
    for p in ledger_paths("HEAD"):
        if p in texts:
            for m in TBD_HEADING.finditer(texts[p]):
                lab = m.group(1) or ""
                if lab not in sec_order:
                    sec_order.append(lab)
    used = {m.group(1) or "" for t in texts.values() for m in SEC.finditer(t)}
    orphans = used - set(sec_order)
    if orphans:
        raise SystemExit(f"§TBD labels without a ledger heading: {sorted(orphans)}")
    nxt, secs = max_section(base), {}
    for lab in sec_order:
        nxt += 1
        while nxt in skip:
            nxt += 1
        secs[lab] = nxt
    adr_labels = list(adr_file_labels(changed).values())
    for t in texts.values():
        for m in ADR.finditer(t):
            if (m.group(1) or "") not in adr_labels:
                raise SystemExit(f"ADR-TBD label '{m.group(1) or ''}' has no decisions/TBD-*.md file")
    if len(adr_labels) != len(set(adr_labels)):
        raise SystemExit("two TBD ADR files share a label; use ADR-TBD-a, ADR-TBD-b in their headings")
    n, adrs = max_adr(base), {}
    for lab in sorted(adr_labels):
        n += 1
        adrs[lab] = n
    return secs, adrs, list(texts)


def rewrite(text: str, secs: dict, adrs: dict, renames: dict) -> str:
    text = SEC.sub(lambda m: f"§{secs[m.group(1) or '']}", text)
    text = ADR.sub(lambda m: f"ADR-{adrs[m.group(1) or '']:04d}", text)
    for old, new in renames.items():
        text = text.replace(Path(old).name, Path(new).name)
    return text


def adr_file_labels(files: list[str]) -> dict:
    """{decisions/TBD-*.md: label}, the label being that of the file's first ADR-TBD token."""
    out = {}
    for f in files:
        if ADR_FILE.match(f) and Path(f).is_file():
            m = ADR.search(Path(f).read_text())
            if not m:
                raise SystemExit(f"{f} has no ADR-TBD token in it")
            out[f] = m.group(1) or ""
    return out


def adr_renames(files: list[str], adrs: dict) -> dict:
    return {f: f"decisions/{adrs[lab]:04d}-{ADR_FILE.match(f).group(1)}" for f, lab in adr_file_labels(files).items()}


def cmd_assign(a) -> int:
    if subprocess.run(["git", "merge-base", "--is-ancestor", a.base, "HEAD"]).returncode != 0:
        raise SystemExit(f"{a.base} is not merged into HEAD; merge it first")
    skip = {int(x) for x in a.skip.split(",") if x.strip()} if a.skip else set()
    secs, adrs, files = plan(a.base, skip)
    all_changed = git("diff", "--name-only", f"{a.base}...HEAD").split()
    renames = adr_renames(all_changed, adrs)
    if not secs and not adrs:
        print("no placeholders")
        return 0
    for lab, n in secs.items():
        print(f"§TBD{'-' + lab if lab else ''} -> §{n}")
    for lab, n in adrs.items():
        print(f"ADR-TBD{'-' + lab if lab else ''} -> ADR-{n:04d}")
    for old, new in renames.items():
        print(f"rename {old} -> {new}")
    if a.dry_run:
        return 0
    for f in files:
        t = Path(f).read_text()
        nt = rewrite(t, secs, adrs, renames)
        if nt != t:
            Path(f).write_text(nt)
    for old, new in renames.items():
        subprocess.run(["git", "mv", old, new], check=True)
    print("done; commit with: git commit -am 'Assign ledger/ADR numbers at merge'")
    return 0


def cmd_check(a) -> int:
    reviewed, new = a.reviewed, a.new
    parents = git("rev-list", "--parents", "-n", "1", new).split()[1:]
    if len(parents) != 1:
        raise SystemExit("NEW must be a single numbering commit")
    p = parents[0]
    ptree = git("rev-parse", f"{p}^{{tree}}").strip()
    if git("rev-parse", p).strip() != git("rev-parse", reviewed).strip():
        pp = git("rev-list", "--parents", "-n", "1", p).split()[1:]
        if len(pp) != 2 or git("rev-parse", pp[0]).strip() != git("rev-parse", reviewed).strip():
            raise SystemExit("NEW's parent is neither REVIEWED nor a merge of REVIEWED with the base")
        clean = subprocess.run(["git", "merge-tree", "--write-tree", reviewed, pp[1]], capture_output=True, text=True)
        if clean.returncode != 0 or clean.stdout.split()[0] != ptree:
            raise SystemExit("the base merge was not a clean automatic merge; it needs a delta review")
        if subprocess.run(["git", "merge-base", "--is-ancestor", pp[1], a.base]).returncode != 0:
            raise SystemExit(f"the merged commit {pp[1][:12]} is not on {a.base}")
    bad = []
    status = [l.split("\t") for l in git("diff", "--name-status", "--no-renames", p, new).splitlines()]
    added = {path for st, path in status if st == "A"}
    for st, path in status:
        if st == "M":
            pair = (path, path)
        elif st == "D" and (m := ADR_FILE.match(path)):
            hits = [a for a in added if re.fullmatch(r"decisions/\d{4}-" + re.escape(m.group(1)), a)]
            if len(hits) != 1:
                bad.append(f"{st}\t{path}")
                continue
            pair = (path, hits[0])
            added.discard(hits[0])
        elif st == "A":
            continue
        else:
            bad.append(f"{st}\t{path}")
            continue
        if not same_but_numbers(git("show", f"{p}:{pair[0]}"), git("show", f"{new}:{pair[1]}")):
            bad.append(f"{st}\t{path}")
    bad += [f"A\t{a}" for a in sorted(added)]
    if bad:
        print("not numbering-only:\n  " + "\n  ".join(bad))
        return 1
    print("numbering-only: OK")
    return 0


def same_but_numbers(old: str, cur: str) -> bool:
    """True when cur equals old with each placeholder replaced by a number."""
    pat = re.escape(old)
    pat = re.sub(r"§TBD(?:\\-[a-z0-9]+)?", lambda m: r"§\d+", pat)
    pat = re.sub(r"ADR\\-TBD(?:\\-[a-z0-9]+)?", lambda m: r"ADR\-\d{4}", pat)
    pat = re.sub(r"TBD\\-", lambda m: r"\d{4}\-", pat)
    return pat != re.escape(old) and re.fullmatch(pat, cur, re.S) is not None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("assign")
    s.add_argument("--base", default="origin/main")
    s.add_argument("--skip", default="")
    s.add_argument("--dry-run", action="store_true")
    c = sub.add_parser("check")
    c.add_argument("reviewed")
    c.add_argument("new")
    c.add_argument("--base", default="origin/main")
    a = ap.parse_args(argv)
    return cmd_assign(a) if a.cmd == "assign" else cmd_check(a)


if __name__ == "__main__":
    sys.exit(main())
