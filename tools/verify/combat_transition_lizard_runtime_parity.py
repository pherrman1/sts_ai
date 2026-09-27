#!/usr/bin/env python3
"""Deterministic parity and dispatch checks for the frozen active-Lizard CTM path."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import combat_transition_composed as composed
from tools import combat_transition_lizard_mechanical_q as lizard_reference
from tools import combat_transition_lizard_minimal as lizard_minimal
from tools import combat_transition_rng_audit as rng_audit

EVIDENCE = ROOT / "docs/experiments/evidence/lizard_tail_mechanical_q_ctm_integration_2026-09-27"
EXPECTED = {
    "candidate": "15da76f4ab3d8bdf74f04f17176fcdc4f6a1fe5ea792497a2e3cf12b29964617",
    "qr": "9f8fb965b24fbd8da1f9600fc9ca0f243e5e9069c47067123c88e36e9f5ebcf9",
    "selection": "68c4e6e4c20596464338e3b8ab44ea0bae8bc4a431d7f3de765a944dc8063493",
    "pairs": "d60bf8004234abf6549997ab4cff12da6650cc50d4f42b2d6bceb6a07f5cdf73",
    "pairsManifest": "c0269eb57ce3fe4eeb2890e7d58f06a2b778f62da43fb9345612e42aa69bc78b",
    "lizardMinimal": "2465502731defca4ace9cfcd84eb222a8330b206297f50aaba55e1ad34e584eb",
    "lizardMechanicalQ": "fcee01d2319d40719cddcb6a6c81ff888ea2720b873d7223b7abe0683192bdbf",
    "sourceAssignment": "752fd7cc3769a065478c0045593944a0822e24909db7cd374397a0f464ae964a",
}
MAGIC = b"COMBAT_TRANSITION_RUNTIME_V2\0"
TOLERANCE = 1e-4


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_native(path: Path) -> tuple[dict, dict[str, bytes]]:
    data = path.read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError("fast artifact is not a V2 runtime")
    version, header_size = __import__("struct").unpack_from("<II", data, len(MAGIC))
    if version != 2:
        raise ValueError("fast artifact version differs")
    offset = len(MAGIC) + 8
    metadata = json.loads(data[offset:offset + header_size])
    offset += header_size
    tensors: dict[str, bytes] = {}
    for name, shape in sorted(metadata["tensors"].items()):
        size = int(np.prod(shape)) * 4
        tensors[name] = data[offset:offset + size]
        if len(tensors[name]) != size:
            raise ValueError("fast artifact tensor is truncated: " + name)
        offset += size
    if offset != len(data):
        raise ValueError("fast artifact has trailing tensor bytes")
    return metadata, tensors


def python_deepsets_survival(artifact: Path):
    metadata, tensor_bytes = parse_native(artifact)
    from tools import combat_transition_surrogate as base

    class RuntimeSurvival(torch.nn.Module):
        def __init__(self):
            super().__init__()
            encoder = base.DeepSetsEncoder(torch.nn, torch, np.zeros(10, np.float32),
                                           np.ones(10, np.float32))
            self.encoder = encoder.net
            self.survival = torch.nn.Linear(64, 1)

        def forward(self, inputs):
            return self.survival(self.encoder(*inputs)).reshape(-1)

    model = RuntimeSurvival()
    state = {}
    for name, value in tensor_bytes.items():
        if name.startswith("survival."):
            shape = metadata["tensors"][name]
            state[name.removeprefix("survival.")] = torch.from_numpy(
                np.frombuffer(value, dtype="<f4").copy().reshape(shape))
    model.load_state_dict(state, strict=True)
    model.eval().requires_grad_(False)
    torch.set_num_threads(1)

    def predict(predictor_input: dict) -> float:
        arrays = composed.visible_arrays(predictor_input)
        inputs = composed.base._torch_inputs(arrays, np.asarray([0]), "cpu", torch,
                                             trim_padding=True)
        with torch.inference_mode():
            return float(torch.sigmoid(model(inputs)).item())

    return metadata, predict


def strip_lizard_predictor(value: dict) -> dict:
    result = copy.deepcopy(value)
    result["relics"] = [r for r in result["relics"] if int(r["relicId"]) != 35]
    for index, relic in enumerate(result["relics"]):
        relic["orderIndex"] = index
    return result


def strip_lizard_state(value: dict) -> dict:
    result = copy.deepcopy(value)
    result["relics"] = [r for r in result["relics"] if int(r["id"]) != 35]
    result["relicBits"][35 // 64] = int(result["relicBits"][35 // 64]) & ~(1 << (35 % 64))
    return result


def mutate_potion(predictor: dict, pre: dict, name: str) -> None:
    potion_id = composed.base._POTION_IDS[name]
    try:
        slot = next(x["slot"] for x in predictor["potions"] if int(x["potionId"]) == 1)
    except StopIteration as error:
        raise ValueError("dispatch seed has no empty potion slot") from error
    predictor["potions"][slot]["potionId"] = potion_id
    predictor["globals"]["potionCount"] += 1
    pre["potions"][slot] = potion_id
    pre["potionCount"] += 1


def dispatch_fixtures(pair_rows: list[dict]) -> list[dict]:
    pair = pair_rows[0]
    no_tail = pair["noTail"]
    active = pair["activeTail"]
    rows = []

    def add(name: str, predictor: dict, pre: dict) -> None:
        rows.append({"name": name, "predictorInput": predictor, "preState": pre})

    add("ordinary_deepsets", copy.deepcopy(no_tail["predictorInput"]),
        copy.deepcopy(no_tail["transition"]["pre"]))

    brew_pi, brew_pre = copy.deepcopy(no_tail["predictorInput"]), copy.deepcopy(no_tail["transition"]["pre"])
    mutate_potion(brew_pi, brew_pre, "ENTROPIC_BREW")
    add("brew_attention", brew_pi, brew_pre)

    active_pi, active_pre = copy.deepcopy(active["predictorInput"]), copy.deepcopy(active["transition"]["pre"])
    add("active_lizard_correction", active_pi, active_pre)

    brew_tail_pi, brew_tail_pre = copy.deepcopy(active_pi), copy.deepcopy(active_pre)
    mutate_potion(brew_tail_pi, brew_tail_pre, "ENTROPIC_BREW")
    add("lizard_brew_fail_closed", brew_tail_pi, brew_tail_pre)

    fairy_pi, fairy_pre = copy.deepcopy(active_pi), copy.deepcopy(active_pre)
    mutate_potion(fairy_pi, fairy_pre, "FAIRY_POTION")
    add("fairy_exact_boundary", fairy_pi, fairy_pre)

    bloom_pi, bloom_pre = copy.deepcopy(active_pi), copy.deepcopy(active_pre)
    bloom_id = composed.base._RELIC_IDS["MARK_OF_THE_BLOOM"]
    bloom_pi["relics"].append({"relicId": bloom_id, "data": 0,
                               "orderIndex": len(bloom_pi["relics"])})
    bloom_pre["relics"].append({"id": bloom_id, "data": 0})
    bloom_pre["relicBits"][bloom_id // 64] = int(bloom_pre["relicBits"][bloom_id // 64]) | (1 << (bloom_id % 64))
    add("mark_bloom_existing", bloom_pi, bloom_pre)

    middle_pi, middle_pre = copy.deepcopy(active_pi), copy.deepcopy(active_pre)
    tail_id = composed.base._RELIC_IDS["LIZARD_TAIL"]
    tail_index = next(i for i, relic in enumerate(middle_pi["relics"])
                      if int(relic["relicId"]) == tail_id)
    added_id = next(composed.base._RELIC_IDS[name]
                    for name in ("ANCHOR", "STONE_CALENDAR", "CLOAK_CLASP")
                    if composed.base._RELIC_IDS[name] not in {
                        int(relic["relicId"]) for relic in middle_pi["relics"]})
    middle_pi["relics"].insert(tail_index + 1, {"relicId": added_id, "data": 0,
                                               "orderIndex": tail_index + 1})
    middle_pre["relics"].insert(tail_index + 1, {"id": added_id, "data": 0})
    middle_pre["relicBits"][added_id // 64] = int(middle_pre["relicBits"][added_id // 64]) | (1 << (added_id % 64))
    for index, relic in enumerate(middle_pi["relics"]):
        relic["orderIndex"] = index
    add("active_lizard_middle_tail", middle_pi, middle_pre)

    spent_pi, spent_pre = copy.deepcopy(active_pi), copy.deepcopy(active_pre)
    next(relic for relic in spent_pi["relics"] if int(relic["relicId"]) == tail_id)["data"] = 0
    next(relic for relic in spent_pre["relics"] if int(relic["id"]) == tail_id)["data"] = 0
    add("spent_lizard_native_path", spent_pi, spent_pre)
    return rows


def verify(args: argparse.Namespace) -> dict:
    candidate_path = args.evidence / "mechanical_q_candidate.json"
    qr_path = args.evidence / "frozen_qr_artifact.json"
    selection_path = args.evidence / "fresh_target_selection.json"
    pairs_path = args.evidence / "fresh_targeted_pairs.jsonl"
    pairs_manifest_path = args.evidence / "fresh_targeted_pairs.jsonl.manifest.json"
    hashes = {
        "candidate": sha256(candidate_path), "qr": sha256(qr_path),
        "selection": sha256(selection_path), "pairs": sha256(pairs_path),
        "pairsManifest": sha256(pairs_manifest_path),
        "lizardMinimal": sha256(ROOT / "tools/combat_transition_lizard_minimal.py"),
        "lizardMechanicalQ": sha256(ROOT / "tools/combat_transition_lizard_mechanical_q.py"),
        "sourceAssignment": sha256(args.evidence / "source_assignment.json"),
    }
    if hashes != EXPECTED:
        raise ValueError(f"frozen Stage-C evidence identity mismatch: {hashes}")
    candidate, qr, candidate_sha = lizard_reference.load_candidate(
        candidate_path, EXPECTED["candidate"])
    selection = json.loads(selection_path.read_text())
    if selection.get("candidateManifestSha256") != candidate_sha or selection.get("rArtifactSha256") != EXPECTED["qr"]:
        raise ValueError("selection provenance does not bind frozen Lizard artifacts")

    pairs = [json.loads(line) for line in pairs_path.read_text().splitlines() if line]
    targets = {(int(x["sourceSeed"]), int(x["fightIdx"])): x for x in selection["targets"]}
    if len(pairs) != 320 or len(targets) != 320:
        raise ValueError("the frozen Stage-C selection must contain exactly 320 rows")

    metadata, py_survival = python_deepsets_survival(args.fast)
    support_models = SimpleNamespace(
        ready=True,
        classes=np.arange(-160, 144, dtype=np.int64),
        domain=metadata["domain"],
        delta_values=np.asarray(metadata["domain"]["maxHpDeltaValues"], dtype=np.int64),
        trained_groups=("turns", "attacks", "cards", "shuffles"),
        encounter_names=rng_audit.encounter_names(),
    )

    command = [str(args.probe), "--lizard-parity", str(args.fast), str(args.standard),
               str(pairs_path), str(selection_path)]
    native_run = subprocess.run(command, capture_output=True, text=True, check=False, cwd=ROOT)
    if native_run.returncode != 0:
        raise RuntimeError(
            "native Lizard parity probe failed\n"
            f"stdout:\n{native_run.stdout}\nstderr:\n{native_run.stderr}"
        )
    native_rows = [json.loads(line) for line in native_run.stdout.splitlines() if line]
    by_key = {(int(x["sourceSeed"]), int(x["fightIdx"])): x for x in native_rows}
    if len(by_key) != 320:
        raise ValueError("native Lizard parity did not cover all 320 selected rows")

    errors = {key: 0.0 for key in ("pOrdinaryWin", "pReserveWin", "qTailConsumed",
                                   "rWinGivenConsumed", "classProbabilities")}
    support_count = 0
    for pair in pairs:
        active = pair["activeTail"]
        key = (int(active["sourceSeed"]), int(active["fightIdx"]))
        target = targets[key]
        no_tail = pair["noTail"]
        if target["predictorInput"] != no_tail["predictorInput"] or target["preState"] != no_tail["transition"]["pre"]:
            raise ValueError(f"Stage-C target row no longer matches paired source state: {key}")
        active_pi = active["predictorInput"]
        active_pre = active["transition"]["pre"]
        if strip_lizard_predictor(active_pi) != target["predictorInput"] or strip_lizard_state(active_pre) != target["preState"]:
            raise ValueError(f"active Tail row does not bind the frozen no-Tail target: {key}")

        python_support, reason = lizard_reference._eligible_support(active_pre, active_pi, support_models)
        if not python_support or reason is not None:
            raise ValueError(f"Python frozen reference excludes selected Stage-C row {key}: {reason}")
        ordinary_input = strip_lizard_predictor(active_pi)
        reserve_input = copy.deepcopy(ordinary_input)
        g = reserve_input["globals"]
        g["curHp"] = min(int(g["maxHp"]), int(g["curHp"]) + int(g["maxHp"]) // 2)
        ordinary_pre = strip_lizard_state(active_pre)
        reserve_pre = copy.deepcopy(ordinary_pre)
        reserve_pre["curHp"] = g["curHp"]
        t2_input_hp = lizard_minimal.hp_treatment(
            int(active_pre["curHp"]), int(active_pre["maxHp"]), "T2_revive")
        t2_input = copy.deepcopy(ordinary_input)
        t2_input["globals"]["curHp"] = t2_input_hp
        t2_pre = copy.deepcopy(ordinary_pre)
        t2_pre["curHp"] = t2_input_hp
        if composed.full_support_reasons(ordinary_pre, ordinary_input, support_models):
            raise ValueError(f"ordinary stripped state outside Python support: {key}")
        if composed.full_support_reasons(reserve_pre, reserve_input, support_models):
            raise ValueError(f"reserve-shifted state outside Python support: {key}")
        if composed.full_support_reasons(t2_pre, t2_input, support_models):
            raise ValueError(f"T2-transformed state outside Python support: {key}")

        expected_po, expected_pr = py_survival(ordinary_input), py_survival(reserve_input)
        expected_q, expected_r, expected_classes = lizard_reference.predict(expected_po, expected_pr, qr)
        native = by_key[key]["prediction"]
        if not native["supported"] or native["reason"] != "supported":
            raise ValueError(f"native support differs from Python reference at {key}: {native['reason']}")
        support_count += 1
        row_values = {
            "pOrdinaryWin": abs(float(native["pOrdinaryWin"]) - expected_po),
            "pReserveWin": abs(float(native["pReserveWin"]) - expected_pr),
            "qTailConsumed": abs(float(native["qTailConsumed"]) - expected_q),
            "rWinGivenConsumed": abs(float(native["rWinGivenConsumed"]) - expected_r),
            "classProbabilities": max(abs(float(a) - float(b)) for a, b in
                                       zip(native["classProbabilities"], expected_classes, strict=True)),
        }
        for name, error in row_values.items():
            errors[name] = max(errors[name], error)
            if error > TOLERANCE:
                raise ValueError(f"native/Python {name} parity error {error} exceeds {TOLERANCE} at {key}")
        branches = by_key[key]["branches"]
        native_prediction = by_key[key]["prediction"]
        if int(native_prediction["t2HeadInputHp"]) != t2_input_hp:
            raise ValueError(f"native T2 head-input HP differs from frozen Python treatment at {key}")
        ordinary_branch = branches["ordinaryWin"]
        if (not ordinary_branch["tailPresent"] or ordinary_branch["tailData"] != 1
                or not ordinary_branch["tailBit"] or not ordinary_branch["relicBitsPreserved"]
                or not ordinary_branch["hpLegal"] or not ordinary_branch["rngContract"]):
            raise ValueError(f"ordinary winning branch invariant failed at {key}")
        consumed_branch = branches["consumedWin"]
        if (not consumed_branch["tailPresent"] or consumed_branch["tailData"] != 0
                or not consumed_branch["tailBit"] or not consumed_branch["relicBitsPreserved"]
                or not consumed_branch["t2HeadInputApplied"] or not consumed_branch["hpClassLegal"]
                or not consumed_branch["t2ConditionalIdentity"]
                or not consumed_branch["hpLegal"] or not consumed_branch["rngContract"]
                or not consumed_branch["potionCount"]):
            raise ValueError(f"T2 consumed-win branch invariant failed at {key}")
        actual_post_hp = int(consumed_branch["actualPostHp"])
        actual_hp_delta = int(consumed_branch["hpDelta"])
        if actual_post_hp != t2_input_hp + actual_hp_delta:
            raise ValueError(f"T2 signed-HP sample does not start from the frozen transformed HP at {key}")
        if not branches["consumedLoss"]["death"]:
            raise ValueError(f"consumed-loss class did not end in death at {key}")

    dispatch = dispatch_fixtures(pairs)
    with tempfile.TemporaryDirectory(prefix="lizard-ctm-dispatch-") as directory:
        fixture_path = Path(directory) / "dispatch.jsonl"
        fixture_path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in dispatch))
        result = subprocess.run([str(args.probe), "--lizard-dispatch", str(args.fast),
                                 str(args.standard), str(fixture_path)], capture_output=True,
                               text=True, check=False, cwd=ROOT)
    if result.returncode != 0:
        raise RuntimeError(
            "native Lizard dispatch probe failed\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    dispatch_rows = {row["name"]: row for row in
                     (json.loads(line) for line in result.stdout.splitlines() if line)}
    expected_names = {row["name"] for row in dispatch}
    if set(dispatch_rows) != expected_names or len(dispatch_rows) != 8:
        raise ValueError("dispatch fixture result set differs")
    if not dispatch_rows["ordinary_deepsets"]["supported"]:
        raise ValueError("ordinary DeepSets route failed")
    if not dispatch_rows["brew_attention"]["supported"]:
        raise ValueError("Brew did not route to supported standard Attention fallback")
    if not dispatch_rows["active_lizard_correction"]["supported"] or not dispatch_rows["active_lizard_correction"]["predictionSupported"]:
        raise ValueError("active Lizard correction did not route")
    middle = dispatch_rows["active_lizard_middle_tail"]
    if not middle["supported"] or not middle["predictionSupported"]:
        raise ValueError("active Lizard with a later relic did not retain correction support")
    spent = dispatch_rows["spent_lizard_native_path"]
    if not spent["supported"] or spent["predictionSupported"] or spent["predictionReason"] != "active_lizard_predictor_state_mismatch":
        raise ValueError("spent Lizard Tail did not stay on the ordinary native path")
    if dispatch_rows["lizard_brew_fail_closed"]["supported"] or dispatch_rows["lizard_brew_fail_closed"]["reason"] != "active_lizard_entropic_brew_unsupported":
        raise ValueError("active Lizard plus Brew did not fail closed")
    fairy = dispatch_rows["fairy_exact_boundary"]
    if fairy["predictionReason"] != "fairy_potion_exact_boundary" or fairy["supported"] or fairy["reason"] != "active_unqualified_lizard":
        raise ValueError("Fairy boundary did not remain on the existing fail-closed path")
    bloom = dispatch_rows["mark_bloom_existing"]
    if not bloom["supported"] or bloom["predictionReason"] != "mark_of_bloom_exact_path":
        raise ValueError("Mark of the Bloom did not retain existing support behavior")
    metrics = json.loads(result.stderr.strip())
    if metrics["fallbackPreparations"] != 1 or metrics["lizardSamples"] != 2 or metrics["lizardSupportFailures"] < 1 or metrics["lizardBoundaryExclusions"] < 1:
        raise ValueError(f"dispatch metrics do not prove routing/exclusions: {metrics}")

    summary = {
        "schema": "active_lizard_deepsets_native_parity_v1",
        "rows": support_count,
        "tolerance": TOLERANCE,
        "maxAbsoluteErrors": errors,
        "supportMismatches": 0,
        "semanticMismatches": 0,
        "forcedBranchChecksPerRow": 3,
        "conditionalT2ChildIdentityRows": support_count,
        "dispatchFixtures": {
            "rows": len(dispatch_rows),
            "ordinaryDeepSets": dispatch_rows["ordinary_deepsets"]["supported"],
            "brewAttention": dispatch_rows["brew_attention"]["supported"],
            "activeLizard": dispatch_rows["active_lizard_correction"]["supported"],
            "middleTail": middle["supported"],
            "spentTail": spent["supported"],
            "lizardBrew": dispatch_rows["lizard_brew_fail_closed"]["reason"],
            "fairy": fairy["reason"],
            "markBloom": bloom["reason"],
            "metrics": metrics,
        },
        "frozenEvidenceHashes": hashes,
        "candidateId": candidate["candidateId"],
        "rArtifactSha256": EXPECTED["qr"],
        "fastArtifactSha256": sha256(args.fast),
        "fastTensorPayloadSha256": hashlib.sha256(b"".join(
            value for name, value in sorted(parse_native(args.fast)[1].items()))).hexdigest(),
    }
    if args.output:
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", required=True, type=Path)
    parser.add_argument("--fast", required=True, type=Path)
    parser.add_argument("--standard", required=True, type=Path)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    parser.add_argument("--output", type=Path)
    result = verify(parser.parse_args())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
