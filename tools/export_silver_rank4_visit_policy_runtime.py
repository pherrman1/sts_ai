#!/usr/bin/env python3
"""Freeze the PR #87 rank-4 NPZ as the compact native Silver runtime artifact."""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

import numpy as np


MAGIC = b"SVPRV001"
VERSION = 1
STATE_WIDTH = 1766
ACTION_WIDTH = 22
RANK = 4


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_string(out, value: str) -> None:
    encoded = value.encode("utf-8")
    if len(encoded) > 0xFFFF:
        raise ValueError("runtime string too large")
    out.write(struct.pack("<H", len(encoded)))
    out.write(encoded)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_npz", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    source_hash = digest(args.source_npz)
    with np.load(args.source_npz, allow_pickle=False) as data:
        names = [str(value) for value in data["feature_names"]]
        widths = (int(data["state_width"][0]), int(data["action_width"][0]), int(data["rank"][0]))
        if widths != (STATE_WIDTH, ACTION_WIDTH, RANK) or len(names) != STATE_WIDTH + ACTION_WIDTH:
            raise SystemExit("source NPZ width/rank mismatch")
        suffix = ["aIsCard", "aIsPotion", "aIsEndTurn", "aIsSelect", "aCardId", "aCardCost",
                  "aCardUpg", "aCardAtk", "aCardSkl", "aCardPow", "aTargetsEnemy", "aTargetHp",
                  "aPlayOrder", "aObtainWeight", "aSelectSize", "aSelTotalCost", "aSelAtk", "aSelSkl",
                  "aSelPow", "aSelUpgraded", "aSelPlayOrder", "aSelObtainWeight"]
        if names[-ACTION_WIDTH:] != suffix:
            raise SystemExit("source NPZ action suffix/order mismatch")
        vectors = [np.asarray(data[name], dtype="<f8") for name in ("baseline_weights", "mean", "scale")]
        active = np.asarray(data["active"], dtype="u1")
        u, v = np.asarray(data["u"], dtype="<f8"), np.asarray(data["v"], dtype="<f8")
    if any(array.shape != (STATE_WIDTH + ACTION_WIDTH,) for array in vectors) or active.shape != (STATE_WIDTH + ACTION_WIDTH,):
        raise SystemExit("source NPZ vector shape mismatch")
    if u.shape != (STATE_WIDTH, RANK) or v.shape != (ACTION_WIDTH, RANK):
        raise SystemExit("source NPZ factor shape mismatch")
    if not all(np.isfinite(array).all() for array in [*vectors, u, v]) or np.any(vectors[2] <= 0):
        raise SystemExit("source NPZ contains invalid numeric values")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as out:
        out.write(MAGIC)
        out.write(struct.pack("<IIII", VERSION, STATE_WIDTH, ACTION_WIDTH, RANK))
        write_string(out, source_hash)
        write_string(out, args.source_commit)
        for name in names:
            write_string(out, name)
        for vector in vectors:
            out.write(np.ascontiguousarray(vector).tobytes(order="C"))
        out.write(np.ascontiguousarray(active).tobytes(order="C"))
        out.write(np.ascontiguousarray(u).tobytes(order="C"))
        out.write(np.ascontiguousarray(v).tobytes(order="C"))
    print(f"runtime_artifact={args.output} sha256={digest(args.output)} source_npz_sha256={source_hash}")


if __name__ == "__main__":
    main()
