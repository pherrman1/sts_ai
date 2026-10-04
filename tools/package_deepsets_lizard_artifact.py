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
GATE2_RESULTS_SHA256 = "1ecd285c78e69249b6e5f46943d84cc10bc4bb86eea4e912f1c0abe774fef1d9"
GATE2_INTEGRATION_CANDIDATE_SHA256 = "40743022491de57d864dc911b3db1bd7bb7dceb9d60f2481c55145d66864aa25"
DEEPSETS_QUALIFICATION_SHA256 = "0afa5319c21706ef380b76825035514c76dbe694bbafa4ed6293a75ce48b98ce"
STAGE_C_CANDIDATE_SHA256 = "15da76f4ab3d8bdf74f04f17176fcdc4f6a1fe5ea792497a2e3cf12b29964617"
MAGIC = b"COMBAT_TRANSITION_RUNTIME_V2\0"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8"))


def load_gate2_pass(results_path: Path, expected_sha256: str) -> tuple[dict, str]:
    result_bytes = results_path.read_bytes()
    result_sha256 = sha256(result_bytes)
    if expected_sha256 != GATE2_RESULTS_SHA256 or result_sha256 != expected_sha256:
        raise ValueError("Gate 2 result hash does not match the reviewed PASS result")
    result = json.loads(result_bytes)
    if result.get("status") != "PASS" or result.get("classification") != \
            "GATE2_ACTIVE_LIZARD_COMPOSED_RUNTIME_CANARY_PASS":
        raise ValueError("Gate 2 result is not the reviewed PASS classification")
    decision = result.get("decision", {})
    required_true = (
        "all16ProcessesCompleteAndExitZero",
        "allRequestedRowsSidecarsAndTracesValidated",
        "allPairedOutcomeFloorsReached",
        "treatmentHasNonzeroLizardPreparationsAndSamples",
        "treatmentHasZeroLizardSupportFailures",
        "noUnexpectedTreatmentSupportAborts",
        "traceAccountingIdentitiesPass",
        "endHpIsWithinOneAndMaxHp",
        "noSuspiciousStateRngOrNumericalDiagnosticsInLogs",
        "gate3MayProceed",
    )
    if any(decision.get(key) is not True for key in required_true):
        raise ValueError("Gate 2 decision fields do not authorize production packaging")
    frozen = result.get("frozen", {})
    if (frozen.get("sourceCommit") != "5c818c0e30aa20fb178bfde19355c01852afef84" or
            frozen.get("integrationCandidateSha256") != GATE2_INTEGRATION_CANDIDATE_SHA256 or
            frozen.get("cohortSeeds") != list(range(991008, 991016)) or
            frozen.get("runs") != 16 or frozen.get("silverRealCombatsPerRun") != 10000 or
            frozen.get("oocMctsSimulations") != 2048):
        raise ValueError("Gate 2 frozen source, artifact, cohort, or budget mismatch")
    arms = result.get("armAggregates", {})
    treatment = arms.get("treatment", {})
    if (treatment.get("runs") != 8 or
            treatment.get("lizardPreparations", 0) <= 0 or
            treatment.get("lizardSamples", 0) <= 0 or
            treatment.get("lizardSupportFailures") != 0):
        raise ValueError("Gate 2 treatment exercise/support criteria failed")
    runs = result.get("runs", [])
    if len(runs) != 16:
        raise ValueError("Gate 2 result must contain all 16 per-run records")
    for run in runs:
        if run.get("arm") != "treatment" or run.get("unsupportedCombats", 0) == 0:
            continue
        n = run["unsupportedCombats"]
        if (run.get("supportReasons") != {"active_unqualified_lizard": n} or
                run.get("lizardBoundaryExclusions") != n):
            raise ValueError("Gate 2 contains an unclassified treatment support abort")
    evidence = result.get("evidenceFiles")
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError("Gate 2 result is missing its evidence hash map")
    evidence_root = results_path.parent.resolve()
    for relative, expected in evidence.items():
        rel = Path(relative)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("Gate 2 evidence path escapes its packet")
        path = evidence_root / rel
        if not path.is_file() or sha256(path.read_bytes()) != expected:
            raise ValueError(f"Gate 2 evidence hash mismatch: {relative}")
    sidecar = results_path.with_suffix(results_path.suffix + ".sha256")
    if sidecar.is_file() and result_sha256 not in sidecar.read_text(encoding="ascii"):
        raise ValueError("Gate 2 result sidecar hash mismatch")
    return result, result_sha256


def reexport(source: Path, candidate_path: Path, *, production: bool = False,
             gate2_result: dict | None = None,
             gate2_sha256: str | None = None) -> bytes:
    original = source.read_bytes()
    source_sha256 = sha256(original)
    if source_sha256 not in (FAST_SOURCE_SHA256, GATE2_INTEGRATION_CANDIDATE_SHA256):
        raise ValueError("qualified DeepSets artifact identity mismatch")
    if production and source_sha256 != GATE2_INTEGRATION_CANDIDATE_SHA256:
        raise ValueError("production packaging requires the exact Gate 2 input artifact")
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
    if not isinstance(metadata.get("experimentalDeepSets"), dict):
        raise ValueError("DeepSets qualification metadata is missing")
    if production:
        if gate2_result is None or gate2_sha256 != GATE2_RESULTS_SHA256:
            raise ValueError("production packaging requires a reviewed Gate 2 PASS result")
        if metadata["experimentalDeepSets"].get("architecture") != \
                "deepset64_shared_hp_with_dedicated_potion_specialist":
            raise ValueError("production source is not the qualified DeepSets stack")
        if metadata["experimentalDeepSets"].get("requiresEntropicBrewFallback") is not True:
            raise ValueError("production DeepSets artifact lost its Brew fallback contract")
        metadata["experimentalDeepSets"]["qualified"] = True
        metadata["experimentalDeepSets"]["defaultChanged"] = True
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
        "qualified": production,
        "defaultChanged": production,
    }
    if production:
        correction["gate2ResultsSha256"] = gate2_sha256
        correction["gate2Classification"] = gate2_result["classification"]
        correction["gate2FrozenImplementationSha"] = gate2_result["frozen"]["sourceCommit"]
    metadata["activeLizardCorrection"] = correction
    metadata["defaultForOocMcts"] = production
    if production:
        metadata["qualification"]["classification"] = \
            "DEEPSETS_BREW_LIZARD_T2_PRODUCTION_QUALIFIED"
        metadata["productionPromotionEvidence"] = {
            "gate2Classification": gate2_result["classification"],
            "gate2ResultsSha256": gate2_sha256,
            "gate2FrozenImplementationSha": gate2_result["frozen"]["sourceCommit"],
            "deepsetsQualificationClassification": "OOC_HYBRID_QUALITY_CONFIRMED",
            "deepsetsQualificationSummarySha256": DEEPSETS_QUALIFICATION_SHA256,
            "lizardCandidateManifestSha256": STAGE_C_CANDIDATE_SHA256,
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
                        help="emit a production-qualified artifact; requires the reviewed Gate 2 result and its SHA-256")
    parser.add_argument("--gate2-results", type=Path,
                        help="Gate 2 result JSON with verified raw evidence files")
    parser.add_argument("--gate2-results-sha256",
                        help="required reviewed Gate 2 result SHA-256 pin")
    args = parser.parse_args()
    if args.production and (args.gate2_results is None or not args.gate2_results_sha256):
        parser.error("--production requires --gate2-results and --gate2-results-sha256")
    if not args.production and (args.gate2_results is not None or args.gate2_results_sha256):
        parser.error("Gate 2 result arguments are only valid with --production")
    gate2_result = None
    gate2_sha256 = None
    if args.production:
        gate2_result, gate2_sha256 = load_gate2_pass(
            args.gate2_results, args.gate2_results_sha256)
    output = reexport(args.source, args.candidate, production=args.production,
                      gate2_result=gate2_result, gate2_sha256=gate2_sha256)
    output_path = args.output.resolve()
    protected_paths = {args.source.resolve(), args.candidate.resolve()}
    if args.production:
        protected_paths.add(args.gate2_results.resolve())
        protected_paths.add(args.gate2_results.with_suffix(
            args.gate2_results.suffix + ".sha256").resolve())
        evidence_root = args.gate2_results.parent.resolve()
        protected_paths.update(
            (evidence_root / relative).resolve()
            for relative in gate2_result["evidenceFiles"])
    if output_path in protected_paths:
        raise ValueError("output path collides with a pinned input or Gate 2 evidence file")
    if output_path.exists():
        if output_path.read_bytes() != output:
            raise FileExistsError("refusing to overwrite an existing, different artifact")
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(output)
    cursor = len(MAGIC) + 8
    header_size = struct.unpack_from("<I", output, len(MAGIC) + 4)[0]
    payload = output[cursor + header_size:]
    print(json.dumps({
        "output": str(args.output),
        "artifactSha256": sha256(output),
        "tensorPayloadSha256": sha256(payload),
        "tensorPayloadBytes": len(payload),
        "status": "production_default_when_ooc_enabled" if args.production else "integration_candidate",
        "defaultForOocMcts": args.production,
        "gate2ResultsSha256": gate2_sha256,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
