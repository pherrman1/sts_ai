#!/usr/bin/env python3
"""Write reproducible provenance for a paired S3 geometry/exposure run."""

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ENV_PREFIXES = ("STS_", "OMP_NUM_THREADS")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("output", type=Path)
    p.add_argument("--command", required=True)
    p.add_argument("--geometry", required=True)
    p.add_argument("--exposure", required=True)
    p.add_argument("--seeds", required=True)
    p.add_argument("--sims", type=int, required=True)
    p.add_argument("--boss-multiplier", type=int, required=True)
    p.add_argument("--particles", type=int, required=True)
    p.add_argument("--threads", type=int, required=True)
    p.add_argument("--ascension", type=int, required=True)
    p.add_argument("--result", required=True)
    p.add_argument("--vnet-alpha", type=float, required=True)
    p.add_argument("--require-clean", action="store_true")
    p.add_argument("--model", action="append", default=[])
    args = p.parse_args()
    models = {}
    for raw in args.model:
        name, path = raw.split("=", 1)
        models[name] = {"path": path, "sha256": sha256(path)}
    environment = {
        k: v for k, v in sorted(os.environ.items())
        if k.startswith(ENV_PREFIXES)
    }
    dirty = bool(git("status", "--porcelain", "--untracked-files=all"))
    if args.require_clean and dirty:
        raise SystemExit("refusing authoritative provenance: worktree is dirty")
    data = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git("rev-parse", "HEAD"),
        "git_dirty": dirty,
        "command": args.command,
        "geometry_artifact": args.geometry,
        "exposure_artifact": args.exposure,
        "result_artifact": args.result,
        "seeds": args.seeds,
        "ascension": args.ascension,
        "simulation_count_base": args.sims,
        "boss_simulation_multiplier": args.boss_multiplier,
        "particles": args.particles,
        "threads": args.threads,
        "fair_rng_regime": os.environ.get("STS_FAIR", "unset"),
        "vnet_alpha": args.vnet_alpha,
        "models": models,
        "environment": environment,
    }
    args.output.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()