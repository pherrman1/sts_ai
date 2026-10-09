#!/usr/bin/env python3
"""Run one frozen campaign arm/shard; no queueing or adaptive selection."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("manifest", type=Path)
    p.add_argument("arm")
    p.add_argument("seed_lo", type=int)
    p.add_argument("count", type=int)
    p.add_argument("output", type=Path)
    p.add_argument("--trace", action="store_true")
    p.add_argument("--tree-profile", action="store_true")
    p.add_argument("--combat-audit", action="store_true")
    p.add_argument("--public-combat", action="store_true")
    p.add_argument("--timeout", type=int, default=3600)
    a = p.parse_args()
    m = json.loads(a.manifest.read_text())
    root = Path(m["root"])
    binary = Path(m["binary"])
    assert a.arm in m["profiles"]["arms"], a.arm
    assert a.count > 0
    allowed = set(m["allowed_seeds"])
    assert set(range(a.seed_lo, a.seed_lo + a.count)) <= allowed, "unreserved seeds"
    assert digest(binary) == m["binary_sha256"], "binary changed"
    for path, expected in m["artifacts"].items():
        assert digest(root / path) == expected, f"artifact changed: {path}"
    out = a.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    paths = {k: Path(str(out) + suffix) for k, suffix in {
        "csv": ".csv", "meta": ".csv.meta.json", "log": ".log",
        "trace": ".trace.jsonl", "tree": ".tree.jsonl", "receipt": ".receipt.json",
        "profile": ".profile.jsonl", "strategic": ".strategic.jsonl",
        "combat": ".combat.jsonl", "public": ".public.jsonl"}.items()}
    assert not any(os.path.lexists(v) for v in paths.values()), "refusing existing outputs"
    env = dict(m["profiles"]["common"])
    env.update(m["profiles"]["arms"][a.arm])
    env["STS_EXECUTABLE_GIT_SHA"] = m["source_sha"]
    if a.trace:
        env["STS_OOC_DECISION_TRACE"] = str(paths["trace"])
        env["STS_OOC_STRATEGIC_TRACE"] = str(paths["strategic"])
        env["STS_RUN_PROFILE"] = str(paths["profile"])
    if a.tree_profile:
        env["STS_SILVER_TREE_PROFILE"] = str(paths["tree"])
    if a.combat_audit:
        env["STS_SILVER_USELESS_TRACE"] = str(paths["combat"])
    if a.public_combat:
        target = env.get("STS_SILVER_PUBLIC_TARGET", "")
        assert target and int(target.split(":")[0]) in range(a.seed_lo, a.seed_lo + a.count), "unbound public target"
        env["STS_SILVER_PUBLIC_TRACE"] = str(paths["public"])
    cmd = ["bash", "tools/seed_guard.sh", str(binary), "bestbench", "10000",
           str(a.count), "0", str(a.seed_lo), str(paths["csv"])]
    receipt = {"manifest": str(a.manifest.resolve()), "manifest_sha256": digest(a.manifest),
               "arm": a.arm, "command": cmd, "environment": env,
               "source_sha": m["source_sha"], "binary_sha256": m["binary_sha256"],
               "started_epoch": time.time(), "pid": os.getpid(), "status": "running"}
    with paths["receipt"].open("x") as f:
        json.dump(receipt, f, indent=2)
    start = time.monotonic()
    with paths["log"].open("x") as log:
        try:
            result = subprocess.run(cmd, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=a.timeout)
            receipt.update(status="completed" if result.returncode == 0 else "failed",
                           exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            receipt.update(status="timeout", exit_code=124)
    receipt["wall_seconds"] = time.monotonic() - start
    receipt["finished_epoch"] = time.time()
    receipt["outputs"] = {k: {"path": str(v), "sha256": digest(v), "bytes": v.stat().st_size}
                          for k, v in paths.items() if k != "receipt" and v.exists()}
    paths["receipt"].write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in ("arm", "status", "exit_code", "wall_seconds")}))
    return receipt["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
