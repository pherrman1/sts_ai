#!/usr/bin/env python3
"""Build an explicitly unqualified V2 artifact from the selected DeepSets checkpoints."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CONTROL_SHA = "e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd"
SURVIVAL_SHA = "328c65f150ac7daa9db7dc7e2047b77cf8b88ef3c09b3da8ef57d75b7a2fd4c3"
TRANSITION_SHA = "bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663"
DOWNSTREAM_SHA = "c00ed677b8b2b2854fb62982247853982bc58d9fc20afdd96c593bcc6c07423a"
POTION_SHA = "06eda953b523ed6b3b9dbc3031bf44408c3bc67f0bc8b7862d28c150448819c1"
CORPUS_SHA = "74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde"
SPLIT_MANIFEST_SHA = "e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32"
PREPARED_SHA = "a642671d0956f36405b837755cdf3dfb3c4870cde4a1d6f251046ffc8205a1c9"
PREPARED_MANIFEST_SHA = "fdf1ca760c971b212e60d9cb86beec78afae6b124958aa53c56a8aea5bb92f51"
MAGIC = b"COMBAT_TRANSITION_RUNTIME_V2\0"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(tensors, shapes, name, value):
    array = value.detach().cpu().contiguous().numpy().astype("<f4")
    if not np.isfinite(array).all():
        raise ValueError(f"nonfinite tensor {name}")
    tensors[name] = array.tobytes(order="C")
    shapes[name] = list(array.shape)


def read_artifact(path):
    data = Path(path).read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError("control is not a V2 artifact")
    version, length = struct.unpack_from("<II", data, len(MAGIC))
    if version != 2:
        raise ValueError("control version differs")
    offset = len(MAGIC) + 8
    metadata = json.loads(data[offset:offset + length])
    offset += length
    tensors = {}
    for name, shape in sorted(metadata["tensors"].items()):
        size = int(np.prod(shape)) * 4
        tensors[name] = data[offset:offset + size]
        if len(tensors[name]) != size:
            raise ValueError("truncated control tensor")
        offset += size
    if offset != len(data):
        raise ValueError("trailing control bytes")
    return metadata, tensors


def split_for_seed(seed):
    raw = hashlib.sha256(f"combat-transition-model-v1:{int(seed)}".encode()).digest()
    bucket = int.from_bytes(raw[:8], "big") % 100
    return 0 if bucket < 80 else 1 if bucket < 90 else 2


def export(control, survival_checkpoint, prepared, transition_checkpoint,
           downstream_checkpoint, potion_checkpoint, output):
    if digest(control) != CONTROL_SHA:
        raise ValueError("control artifact identity mismatch")
    for path, expected in ((survival_checkpoint, SURVIVAL_SHA),
                           (transition_checkpoint, TRANSITION_SHA),
                           (downstream_checkpoint, DOWNSTREAM_SHA),
                           (potion_checkpoint, POTION_SHA)):
        if digest(path) != expected:
            raise ValueError(f"checkpoint identity mismatch: {path}")

    metadata, tensors = read_artifact(control)
    metadata = copy.deepcopy(metadata)
    shapes = copy.deepcopy(metadata["tensors"])
    replaced = ("survival.", "max_hp.", "hp.", "potion_encoder.")
    tensors = {name: value for name, value in tensors.items()
               if not name.startswith(replaced)}
    shapes = {name: shape for name, shape in shapes.items()
              if not name.startswith(replaced)}

    # Phase-1 was refit on TRAIN+VALIDATION. Rebuild its exact continuous-global
    # normalization from the bound prepared array and source-group split rule.
    prepared_dir = Path(prepared).parent
    prepared_manifest_path = prepared_dir / "prepared_manifest.json"
    split_manifest_path = prepared_dir / "split_manifest.json"
    if digest(prepared) != PREPARED_SHA:
        raise ValueError("Phase-1 prepared array identity mismatch")
    if digest(prepared_manifest_path) != PREPARED_MANIFEST_SHA:
        raise ValueError("Phase-1 prepared manifest identity mismatch")
    prepared_manifest = json.loads(prepared_manifest_path.read_text())
    if (prepared_manifest.get("corpusSha256") != CORPUS_SHA or
            prepared_manifest.get("rows") != 510030 or
            digest(split_manifest_path) != SPLIT_MANIFEST_SHA):
        raise ValueError("Phase-1 prepared corpus/split identity mismatch")
    with np.load(prepared, allow_pickle=False) as archive:
        source = archive["sourceSeed"]
        split = np.fromiter((split_for_seed(int(seed)) for seed in source),
                            dtype=np.int8, count=len(source))
        fit = archive["globals_continuous"][split < 2]
        # Match NumPy's default float32 accumulation used by the Phase-1 fit.
        mean = fit.mean(axis=0)
        std = fit.std(axis=0)
    if fit.shape != (458589, 10) or not np.isfinite(mean).all() or not np.isfinite(std).all():
        raise ValueError("Phase-1 TRAIN+VALIDATION normalization population differs")
    inv = (1.0 / np.maximum(std, 1e-6)).astype(np.float32)
    mean_sha = hashlib.sha256(mean.astype("<f4", copy=False).tobytes()).hexdigest()
    inv_sha = hashlib.sha256(inv.astype("<f4", copy=False).tobytes()).hexdigest()

    survival = torch.load(survival_checkpoint, map_location="cpu", weights_only=False)
    if set(survival) != {"card_id.weight", "relic_id.weight", "potion_id.weight", "potion_slot.weight",
                         "global_category.0.weight", "global_category.1.weight", "global_category.2.weight",
                         "global_category.3.weight", "card_mlp.0.weight", "card_mlp.0.bias", "card_mlp.2.weight",
                         "card_mlp.2.bias", "relic_mlp.0.weight", "relic_mlp.0.bias", "relic_mlp.2.weight",
                         "relic_mlp.2.bias", "potion_mlp.0.weight", "potion_mlp.0.bias", "potion_mlp.2.weight",
                         "potion_mlp.2.bias", "global_mlp.0.weight", "global_mlp.0.bias", "trunk.0.weight",
                         "trunk.0.bias", "trunk.2.weight", "trunk.2.bias", "win.weight", "win.bias", "hp.weight", "hp.bias"}:
        raise ValueError("Phase-1 DeepSets checkpoint tensor schema differs")
    survival_prefix = "survival.encoder."
    put(tensors, shapes, survival_prefix + "scalar_mean", torch.from_numpy(mean))
    put(tensors, shapes, survival_prefix + "scalar_inv", torch.from_numpy(inv))
    for name, value in survival.items():
        if name.startswith("hp."):
            continue  # auxiliary Phase-1 winning-HP head is not the survival predictor
        target = "survival.survival." + name.removeprefix("win.") if name.startswith("win.") else survival_prefix + name
        put(tensors, shapes, target, value)

    transition = torch.load(transition_checkpoint, map_location="cpu", weights_only=False)
    state = transition["stateDict"]
    encoder = {key.removeprefix("encoder."): value for key, value in state.items() if key.startswith("encoder.")}
    if len(encoder) != 28:
        raise ValueError("shared DeepSets encoder tensor count differs")
    for group in ("max_hp", "hp", "potion_encoder"):
        for name, value in encoder.items():
            put(tensors, shapes, f"{group}.encoder.{name}", value)
    for name, value in transition["maxHpHeadStateDict"].items():
        put(tensors, shapes, f"max_hp.max_hp_delta.{name}", value)
    for name, value in state.items():
        if name.startswith("delta_embedding."):
            put(tensors, shapes, "hp." + name, value)
        elif name.startswith("hp."):
            put(tensors, shapes, "hp." + name, value)

    potion = torch.load(potion_checkpoint, map_location="cpu", weights_only=False)["stateDict"]
    for name, value in potion.items():
        put(tensors, shapes, "potion." + name, value)

    downstream = torch.load(downstream_checkpoint, map_location="cpu", weights_only=False)["stateDict"]
    for name, value in downstream.items():
        put(tensors, shapes, name, value)

    metadata["sources"].update(survival=SURVIVAL_SHA, maxHP=TRANSITION_SHA,
        HP=TRANSITION_SHA, potion=POTION_SHA, downstream=DOWNSTREAM_SHA)
    metadata["experimentalSurvival"] = dict(architecture="deepset64_phase1_v1",
        checkpointSha256=SURVIVAL_SHA, controlSha256=CONTROL_SHA,
        preparedSha256=PREPARED_SHA, preparedManifestSha256=PREPARED_MANIFEST_SHA,
        scalarMeanSha256=mean_sha, scalarInvSha256=inv_sha, qualified=False)
    metadata["experimentalDeepSets"] = dict(architecture="deepset64_shared_transition",
        controlSha256=CONTROL_SHA, maxHpHpCheckpointSha256=TRANSITION_SHA,
        downstreamCheckpointSha256=DOWNSTREAM_SHA, potionCheckpointSha256=POTION_SHA,
        potionOfflineDecision="DEEPSET_POTION_REJECTED", qualified=False)
    metadata["tensors"] = shapes
    header = json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()
    with Path(output).open("xb") as stream:
        stream.write(MAGIC + struct.pack("<II", 2, len(header)) + header)
        for name in sorted(tensors):
            stream.write(tensors[name])
    return dict(output=str(Path(output).resolve()), candidateSha256=digest(output),
        controlSha256=CONTROL_SHA, survivalCheckpointSha256=SURVIVAL_SHA,
        preparedSha256=PREPARED_SHA, preparedManifestSha256=PREPARED_MANIFEST_SHA,
        scalarMeanSha256=mean_sha, scalarInvSha256=inv_sha,
        maxHpHpCheckpointSha256=TRANSITION_SHA, downstreamCheckpointSha256=DOWNSTREAM_SHA,
        potionCheckpointSha256=POTION_SHA, potionOfflineDecision="DEEPSET_POTION_REJECTED",
        qualified=False, defaultChanged=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("control", "survival-checkpoint", "prepared", "transition-checkpoint",
                  "downstream-checkpoint", "potion-checkpoint", "output"):
        parser.add_argument("--" + field, type=Path, required=True)
    args = vars(parser.parse_args())
    print(json.dumps(export(**{key.replace("-", "_"): value for key, value in args.items()}), indent=2))
