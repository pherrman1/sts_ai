#!/usr/bin/env python3
"""Re-export the qualified DeepSets tensor payload with frozen Lizard metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


FAST_SOURCE_SHA256 = "a23c0f86593fef2380c3efee3cf75783bf2b5e714395ec93237fac19376bfd1a"
FAST_PAYLOAD_SHA256 = "429f9dc018a6b9de231657df4aba787bddc2de2e4cecb2e7989e167c37813139"
CANDIDATE_SHA256 = "15da76f4ab3d8bdf74f04f17176fcdc4f6a1fe5ea792497a2e3cf12b29964617"
QR_SHA256 = "9f8fb965b24fbd8da1f9600fc9ca0f243e5e9069c47067123c88e36e9f5ebcf9"
R_MODEL_SHA256 = "fbf29bf742e3c40b18a358386509a74ced54e97a2a7e760ff988de5c14a335a8"
MAGIC = b"COMBAT_TRANSITION_RUNTIME_V2\0"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8"))


def reexport(source: Path, candidate_path: Path, *, production: bool) -> bytes:
    original = source.read_bytes()
    if sha256(original) != FAST_SOURCE_SHA256:
        raise ValueError("qualified DeepSets artifact hash mismatch")
    if not original.startswith(MAGIC):
        raise ValueError("qualified DeepSets artifact magic mismatch")
    cursor = len(MAGIC)
    version, header_size = struct.unpack_from("<II", original, cursor)
    cursor += 8
    if version != 2 or header_size <= 0 or header_size > 1024 * 1024:
        raise ValueError("qualified DeepSets artifact header mismatch")
    header_bytes = original[cursor:cursor + header_size]
    payload = original[cursor + header_size:]
    if len(header_bytes) != header_size or sha256(payload) != FAST_PAYLOAD_SHA256:
        raise ValueError("qualified DeepSets tensor payload identity mismatch")

    candidate_bytes = candidate_path.read_bytes()
    if sha256(candidate_bytes) != CANDIDATE_SHA256:
        raise ValueError("frozen Lizard candidate manifest hash mismatch")
    candidate = json.loads(candidate_bytes)
    qr_name = candidate.get("rArtifact", {}).get("path", "")
    qr_path = candidate_path.parent / Path(qr_name).name
    qr_bytes = qr_path.read_bytes()
    if sha256(qr_bytes) != QR_SHA256:
        raise ValueError("frozen Lizard q/r artifact hash mismatch")
    qr = json.loads(qr_bytes)
    r_model = qr.get("rModel")
    if canonical_sha256(r_model) != R_MODEL_SHA256:
        raise ValueError("frozen Lizard r model hash mismatch")
    if candidate.get("candidateId") != "active-lizard-mechanical-q-learned-r-t2":
        raise ValueError("unexpected active-Lizard candidate identity")
    if candidate.get("rArtifact", {}).get("rModelSha256") != R_MODEL_SHA256:
        raise ValueError("candidate does not bind frozen r-model hash")

    metadata = json.loads(header_bytes)
    correction = {
        "candidateId": candidate["candidateId"],
        "candidateManifestSha256": CANDIDATE_SHA256,
        "frozenQrArtifactSha256": QR_SHA256,
        "rModelSha256": R_MODEL_SHA256,
        "qMode": candidate["qMode"],
        "qDefinition": "q = 1 - pOrdinaryWin",
        "rMode": candidate["rMode"],
        "rFeatureOrder": candidate["rFeatureOrder"],
        "treatment": candidate["treatment"],
        "t2Rule": candidate["t2Rule"],
        "rModel": {
            "featureMean": r_model["featureMean"],
            "featureScale": r_model["featureScale"],
            "standardizedCoefficients": r_model["standardizedCoefficients"],
        },
        "supportBoundaries": [
            "active_lizard_entropic_brew_unsupported",
            "fairy_potion_exact_boundary",
            "mark_of_bloom_exact_path",
        ],
        "status": "production_default_when_ooc_enabled" if production else "integration_candidate",
        "qualified": bool(production),
        "defaultChanged": bool(production),
    }
    metadata["activeLizardCorrection"] = correction
    metadata["defaultForOocMcts"] = bool(production)
    if production:
        metadata["experimentalDeepSets"]["qualified"] = True
        metadata["experimentalDeepSets"]["defaultChanged"] = True
        metadata["qualification"]["classification"] = (
            "DEEPSETS_BREW_LIZARD_T2_PRODUCTION_QUALIFIED"
        )
        metadata["qualification"]["promotionEvidence"] = {
            "deepSetsBrewFallback": {
                "pullRequest": 351,
                "pairedRuns": 512,
                "controlWins": 277,
                "hybridWins": 292,
                "pairedDifferencePp": 2.9297,
                "paired95CiPp": [-1.7578, 7.6172],
                "nonInferiorityMarginPp": -5.0,
            },
            "activeLizard": {
                "pullRequest": 330,
                "candidateManifestSha256": CANDIDATE_SHA256,
                "frozenQrArtifactSha256": QR_SHA256,
            },
            "integrationEvidence": "docs/experiments/evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27/README.md",
        }

    header = json.dumps(metadata, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=False).encode("utf-8")
    return MAGIC + struct.pack("<II", 2, len(header)) + header + payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="exact PR #351 DeepSets fast artifact")
    parser.add_argument("candidate", type=Path, help="frozen Lizard candidate manifest")
    parser.add_argument("output", type=Path, help="new native artifact path")
    parser.add_argument("--production", action="store_true",
                        help="mark the stack qualified and default for enabled OOC MCTS")
    args = parser.parse_args()
    output = reexport(args.source, args.candidate, production=args.production)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(output)
    cursor = len(MAGIC) + 8
    header_size = struct.unpack_from("<I", output, len(MAGIC) + 4)[0]
    payload = output[cursor + header_size:]
    print(json.dumps({
        "output": str(args.output),
        "artifactSha256": sha256(output),
        "tensorPayloadSha256": sha256(payload),
        "tensorPayloadBytes": len(payload),
        "production": args.production,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
