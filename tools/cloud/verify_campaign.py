#!/usr/bin/env python3
"""Verify every worker delivery of a tools/cloud/worker.sh campaign in one pass.

For each worker W in 1..workers this checks that SHARE/wWW.tar and SHARE/wWW.DONE.json exist, that the tar's
sha256 equals DONE.json's tar_sha256, that DONE.json lists exactly the units units.txt assigns to W, that the tar
holds a .done marker for each of them and no other unit or .failed marker, and that the tar's FROZEN.txt names
this campaign, worker, code commit and binary and the same campaign-file hashes as the lead's checkout. All
workers must report the same run commit. It prints one line per worker and a summary, and exits 0 only when
every worker is OK. Run it from the lead's own container: a worker's local byte compare after upload may be served
from the share's local cache, so it is not proof of delivery. The facts come from the files, never from chat.

With "schedule queue" in the manifest, units are not tied to workers. Each finished unit is its own tar,
SHARE/units/<unit id>.wWW.tar. Then every unit of units.txt needs at least one such tar that holds its .done
marker, no .failed marker and a FROZEN.txt that matches worker WW, and all tars must name one run commit. A unit
run by two workers is reported as a duplicate (the first tar in name order is used). The worker DONE.json files
are listed but not required. --extract DEST unpacks the used tar of every unit into DEST (out/units/...), the
layout the static workers' tars have, for the campaign's analysis script.

Usage: python3 tools/cloud/verify_campaign.py CAMPAIGN_DIR [--share DIR] [--json] [--extract DEST]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from pathlib import Path


def read_manifest(path: Path) -> dict:
    keys: dict = {"input": []}
    for line in path.read_text().splitlines():
        parts = line.split()
        if not parts or parts[0].startswith("#"):
            continue
        if parts[0] == "input":
            keys["input"].append(parts[1:])
        else:
            keys[parts[0]] = " ".join(parts[1:])
    return keys


def unit_lines(path: Path) -> list[str]:
    return [l.rstrip("\n") for l in path.read_text().splitlines()
            if l.strip() and not l.lstrip().startswith("#")]


def unit_id(line: str) -> str:
    # Same mapping as worker.sh: tr -c 'A-Za-z0-9._-' '_'
    return re.sub(r"[^A-Za-z0-9._-]", "_", line)


def assigned(units: list[str], workers: int, w: int) -> list[str]:
    return [u for i, u in enumerate(units) if i % workers + 1 == w]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def frozen_expected(d: Path, m: dict, w: int) -> tuple[str, list[str]]:
    """(identity line without run=, hash lines) that worker w's FROZEN.txt must carry."""
    head = f"campaign={m['name']} worker={w} code={m['code_commit']} binary={m['binary_sha256']}"
    return head, [f"{sha256(d / n)}  {n}" for n in ("campaign.manifest", "units.txt", "run_unit.sh")]


def check_frozen(text: str, d: Path, m: dict, w: int) -> tuple[str | None, str | None]:
    """Return (run commit, error)."""
    lines = text.splitlines()
    if not lines:
        return None, "FROZEN.txt empty"
    run = re.search(r"\brun=([0-9a-f]{40})\b", lines[0])
    head = re.sub(r" run=[0-9a-f]{40}", "", lines[0])
    want_head, want_hashes = frozen_expected(d, m, w)
    if head != want_head or not run:
        return None, f"FROZEN.txt identity '{lines[0]}' does not match the manifest"
    if lines[1:] != want_hashes:
        return None, "FROZEN.txt campaign-file hashes differ from the lead's checkout"
    return run.group(1), None


def check_worker(share: Path, units: list[str], workers: int, w: int, d: Path, m: dict) -> tuple[str, str, str | None]:
    tag = f"w{w:02d}"
    tar, done = share / f"{tag}.tar", share / f"{tag}.DONE.json"
    if not done.exists() or not tar.exists():
        return "MISSING", f"{'tar ' if not tar.exists() else ''}{'DONE.json' if not done.exists() else ''}".strip(), None
    try:
        meta = json.loads(done.read_text())
    except (OSError, ValueError) as e:
        return "BAD", f"DONE.json unreadable: {e}", None
    want = assigned(units, workers, w)
    if meta.get("worker") != w:
        return "BAD", f"DONE.json says worker {meta.get('worker')}", None
    if meta.get("units") != want:
        return "BAD", f"DONE.json lists {len(meta.get('units') or [])} units, units.txt assigns {len(want)}", None
    got = sha256(tar)
    if got != meta.get("tar_sha256"):
        return "BAD", f"tar sha256 {got[:12]} != DONE.json {str(meta.get('tar_sha256'))[:12]}", None
    try:
        with tarfile.open(tar) as t:
            names = set(t.getnames())
            fz = t.extractfile("FROZEN.txt") if "FROZEN.txt" in names else None
            frozen = fz.read().decode() if fz else ""
    except (OSError, tarfile.TarError, UnicodeDecodeError) as e:
        return "BAD", f"tar unreadable: {e}", None
    missing = [u for u in want if f"out/units/{unit_id(u)}.done" not in names]
    if missing:
        return "BAD", f"{len(missing)} unit markers missing, first: {missing[0]}", None
    ids = {unit_id(u) for u in want}
    stray = sorted({n.split("/")[2] for n in names if n.startswith("out/units/") and n.count("/") >= 2}
                   - {f"{i}{x}" for i in ids for x in ("", ".done", ".log")})
    if stray:
        return "BAD", f"tar has unexpected unit entries, first: {stray[0]}", None
    run, err = check_frozen(frozen, d, m, w)
    if err:
        return "BAD", err, None
    return "OK", f"{len(want)} units, run {run[:12]}, tar {got[:12]}, {meta.get('finished_utc', '?')}", run


def check_unit_tar(tar: Path, uid: str, d: Path, m: dict) -> tuple[str | None, str | None]:
    """(run commit, error) for one queue-mode unit tar."""
    w = re.search(r"\.w(\d+)\.tar$", tar.name)
    try:
        with tarfile.open(tar) as t:
            names = set(t.getnames())
            fz = t.extractfile("FROZEN.txt") if "FROZEN.txt" in names else None
            frozen = fz.read().decode() if fz else ""
    except (OSError, tarfile.TarError, UnicodeDecodeError) as e:
        return None, f"tar unreadable: {e}"
    if f"out/units/{uid}.done" not in names:
        return None, "no .done marker"
    if f"out/units/{uid}.failed" in names:
        return None, ".failed marker"
    stray = sorted(n for n in names if n.startswith("out/units/") and n.split("/")[2] not in (uid, f"{uid}.done", f"{uid}.log"))
    if stray:
        return None, f"unexpected entry {stray[0]}"
    return check_frozen(frozen, d, m, int(w.group(1)))


def main_queue(a, d: Path, m: dict, share: Path, units: list[str]) -> int:
    udir = share / "units"
    tars = sorted(udir.glob("*.tar")) if udir.is_dir() else []
    by_unit: dict[str, list[Path]] = {}
    for t in tars:
        by_unit.setdefault(re.sub(r"\.w\d+\.tar$", "", t.name), []).append(t)
    rows, runs, used = [], set(), {}
    for u in units:
        uid = unit_id(u)
        cands, errs = by_unit.get(uid, []), []
        for t in cands:
            run, err = check_unit_tar(t, uid, d, m)
            if err:
                errs.append(f"{t.name}: {err}")
            elif uid not in used:
                used[uid] = t
                runs.add(run)
        if uid in used:
            dup = len(cands) - 1
            rows.append((uid, "OK", f"{used[uid].name}{f' (+{dup} duplicate)' if dup else ''}"))
        else:
            rows.append((uid, "BAD" if errs else "MISSING", "; ".join(errs) or "no tar"))
    if len(runs) > 1:
        rows = [(i, "BAD" if s == "OK" else s, f"units ran different run commits: {sorted(r[:12] for r in runs)}"
                 if s == "OK" else x) for i, s, x in rows]
    extra = sorted(set(by_unit) - {unit_id(u) for u in units})
    done = sorted(p.name for p in share.glob("w*.DONE.json"))
    ok = all(s == "OK" for _, s, _ in rows) and not extra
    if a.json:
        print(json.dumps({"units": [{"unit": i, "state": s, "detail": x} for i, s, x in rows],
                          "extra_tars": extra, "worker_done": done, "ok": ok}, indent=1))
    else:
        for i, s, x in rows:
            if s != "OK" or "duplicate" in x:
                print(f"{i} {s:7s} {x}")
        n = {s: sum(1 for _, t, _ in rows if t == s) for s in ("OK", "MISSING", "BAD")}
        print(f"units OK {n['OK']} MISSING {n['MISSING']} BAD {n['BAD']} of {len(rows)}; duplicates "
              f"{sum(1 for _, _, x in rows if 'duplicate' in x)}; tars for unknown units {len(extra)}; "
              f"run {sorted(r[:12] for r in runs)}; worker DONE.json: {len(done)}/{m['workers']}")
    if a.extract and ok:
        dest = Path(a.extract)
        for uid, t in used.items():
            with tarfile.open(t) as tf:
                tf.extractall(dest, members=[x for x in tf.getmembers() if x.name.startswith("out/units/")],
                              filter="data")
        print(f"extracted {len(used)} units to {dest}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("campaign")
    ap.add_argument("--share", help="override the manifest's share dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--extract", help="queue schedule: unpack every verified unit into this dir (only if all OK)")
    a = ap.parse_args(argv)
    d = Path(a.campaign)
    m = read_manifest(d / "campaign.manifest")
    workers = int(m["workers"])
    share = Path(a.share or m["share"])
    units = unit_lines(d / "units.txt")
    if len({unit_id(u) for u in units}) != len(units):
        raise SystemExit("units.txt has two units with the same id")
    if m.get("schedule", "static") == "queue":
        return main_queue(a, d, m, share, units)
    checked = [(w, *check_worker(share, units, workers, w, d, m)) for w in range(1, workers + 1)]
    runs = {r for _, s, _, r in checked if s == "OK"}
    rows = []
    for w, s, x, r in checked:
        if s == "OK" and len(runs) > 1:
            s, x = "BAD", f"workers ran different run commits: {sorted(c[:12] for c in runs)}"
        rows.append((w, s, x))
    if a.json:
        print(json.dumps([{"worker": w, "state": s, "detail": x} for w, s, x in rows], indent=1))
    else:
        for w, s, x in rows:
            print(f"w{w:02d} {s:7s} {x}")
        for state in ("OK", "MISSING", "BAD"):
            ws = [str(w) for w, s, _ in rows if s == state]
            print(f"{state}: {' '.join(ws) if ws else '-'}")
    return 0 if all(s == "OK" for _, s, _ in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
