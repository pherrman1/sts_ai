#!/usr/bin/env python3
"""Explicit experimental survival replacement; preserve every other V2 byte."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct

import numpy as np
import torch

from tools import combat_transition_surrogate as base
from tools.combat_transition_survival_deepset_train import SurvivalNet

CHECKPOINT_SHA = "3689593db85974f13b6313c495e7fde4ec4b4fa7d87f3442c8604a47f5e0f05b"
CONTROL_SHA = "e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd"
MAGIC = b"COMBAT_TRANSITION_RUNTIME_V2\0"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_artifact(path):
    data = Path(path).read_bytes()
    if data[:len(MAGIC)] != MAGIC:
        raise ValueError("not a V2 artifact")
    version, length = struct.unpack_from("<II", data, len(MAGIC))
    if version != 2:
        raise ValueError("not V2")
    offset = len(MAGIC) + 8
    metadata = json.loads(data[offset:offset + length])
    offset += length
    tensors = {}
    for name, shape in sorted(metadata["tensors"].items()):
        size = int(np.prod(shape)) * 4
        tensors[name] = data[offset:offset + size]
        if len(tensors[name]) != size:
            raise ValueError("truncated tensor")
        offset += size
    if offset != len(data):
        raise ValueError("trailing bytes")
    return metadata, tensors


def load_candidate(checkpoint, evidence):
    if digest(checkpoint) != CHECKPOINT_SHA:
        raise ValueError("strong-WD checkpoint identity mismatch")
    receipt = json.loads(Path(evidence).read_text())
    if receipt["arms"]["strongWd"]["checkpointSha256"] != CHECKPOINT_SHA:
        raise ValueError("PR217 receipt binding mismatch")
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    if payload["selectedEpoch"] != 20 or payload["experimentSha"] != receipt["executionSha"]:
        raise ValueError("training provenance mismatch")
    encoder = base.DeepSetsEncoder(torch.nn, torch, np.zeros(10), np.ones(10)).net
    model = SurvivalNet(encoder)
    model.load_state_dict(payload["stateDict"], strict=True)
    model.eval().requires_grad_(False)
    if not all(torch.isfinite(value).all() for value in model.state_dict().values()):
        raise ValueError("nonfinite checkpoint")
    return model


def export(control, checkpoint, evidence, output):
    if digest(control) != CONTROL_SHA:
        raise ValueError("current-main control differs")
    model = load_candidate(checkpoint, evidence)
    metadata, original = read_artifact(control)
    metadata = copy.deepcopy(metadata)
    tensors = {name: value for name, value in original.items() if not name.startswith("survival.")}
    shapes = {name: shape for name, shape in metadata["tensors"].items() if not name.startswith("survival.")}
    for name, value in model.state_dict().items():
        target = "survival." + (name.replace("head.", "survival.", 1) if name.startswith("head.") else name)
        array = value.detach().numpy().astype("<f4")
        tensors[target] = array.tobytes()
        shapes[target] = list(array.shape)
    metadata["sources"]["survival"] = CHECKPOINT_SHA
    metadata["experimentalSurvival"] = dict(architecture="deepset64_linear_strongWd",
        checkpointSha256=CHECKPOINT_SHA, controlSha256=CONTROL_SHA, qualified=False)
    metadata["tensors"] = shapes
    header = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
    with Path(output).open("xb") as stream:
        stream.write(MAGIC + struct.pack("<II", 2, len(header)) + header)
        for name in sorted(tensors):
            stream.write(tensors[name])
    return dict(controlSha256=CONTROL_SHA, checkpointSha256=CHECKPOINT_SHA,
        candidateSha256=digest(output), evidenceSha256=digest(evidence),
        unchangedNonSurvivalTensors=sum(not name.startswith("survival.") for name in original),
        defaultChanged=False, qualified=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("control", "checkpoint", "evidence", "output"):
        parser.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(**vars(args)), indent=2))
