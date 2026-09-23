#!/usr/bin/env python3
"""Export the one frozen SilverPriorNetV1 checkpoint for native inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import torch

EXPECTED_CHECKPOINT = "b756c3e6576bdb53085f24aeb1102e4e2fe55fd7469c55546c99f068ccf40e24"
EXPECTED_RELEASE = "b32d8d79b44ee799af05892e79e45fb146f4859df58364722d7cd92531bd8419"
EXPECTED_BINDING = "7febae9df90e427ad5db631a2004ff4c4cdd579346d22d25b3e1f4532af96e17"
EXPECTED_SELECTION = "ed91b3bb4c6983be3701333320f1e6c12f7332e3e371ac24b857a76a47d3b5ed"
EXPECTED_VOCAB = "7e07db8b10618d7c1e9b9b1b31d8196950c03060c54fd4d25fd057ac7918cd46"
EXPECTED_TAU = 1.179975000005129


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def export(checkpoint: Path, vocabulary_path: Path, output: Path) -> str:
    if sha(checkpoint) != EXPECTED_CHECKPOINT:
        raise ValueError("checkpoint SHA-256 does not match frozen T2")
    vocab = json.loads(vocabulary_path.read_text())
    vocab_body = {k: v for k, v in vocab.items() if k != "sha256"}
    if vocab.get("sha256") != EXPECTED_VOCAB or hashlib.sha256(canonical(vocab_body)).hexdigest() != EXPECTED_VOCAB:
        raise ValueError("compact vocabulary is not the frozen vocabulary")
    cp = torch.load(checkpoint, map_location="cpu", weights_only=False)
    cfg = cp.get("config", {})
    if (cp.get("arm") != "T2" or cfg.get("seed") != 20260922
            or cfg.get("architecture") != "SilverPriorNetV1"
            or cp.get("tau") != EXPECTED_TAU
            or cfg.get("release_sha256") != EXPECTED_RELEASE
            or cfg.get("binding_sha256") != EXPECTED_BINDING
            or cfg.get("selection_sha256") != EXPECTED_SELECTION
            or cfg.get("vocabulary_sha256") != EXPECTED_VOCAB):
        raise ValueError("checkpoint metadata does not match frozen release")
    tensors = {}
    for name, tensor in cp["state_dict"].items():
        tensors[name] = tensor.detach().cpu().contiguous().tolist()
    body = {
        "schema": "silver_prior_native_v1", "architecture": "SilverPriorNetV1",
        "model_schema": 1, "arm": "T2", "seed": 20260922, "tau": EXPECTED_TAU,
        "checkpoint_sha256": EXPECTED_CHECKPOINT,
        "release_sha256": EXPECTED_RELEASE, "binding_sha256": EXPECTED_BINDING,
        "selection_sha256": EXPECTED_SELECTION, "vocabulary_sha256": EXPECTED_VOCAB,
        "dimensions": {"context": 144, "card_embedding": [158,32],
            "monster_embedding": [2048,16], "potion_embedding": [256,16],
            "candidate_outputs": 1, "hidden": [128,96], "parameter_count": 232665},
        "vocabulary": vocab["canonical_to_compact"],
        "normalization": {k: torch.as_tensor(v).detach().cpu().tolist()
                          for k, v in cp["normalization"].items()},
        "state_dict": tensors,
    }
    body["artifact_sha256"] = hashlib.sha256(canonical(body)).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=output.name + ".", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(canonical(body) + b"\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, output)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return sha(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--vocabulary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    digest = export(args.checkpoint, args.vocabulary, args.output)
    print(json.dumps({"output": str(args.output), "sha256": digest,
                      "checkpoint_sha256": EXPECTED_CHECKPOINT}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
