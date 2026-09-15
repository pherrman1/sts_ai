#!/usr/bin/env python3
"""Promote the reviewed Phase-1 HPO winner into a near-full survival component."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import torch

try:
    from tools import combat_transition_attention_ablation as attention
    from tools import combat_transition_model_experiment as phase1
except ModuleNotFoundError:
    import combat_transition_attention_ablation as attention
    import combat_transition_model_experiment as phase1


SCHEMA = "combat_transition_attention_hpo_promotion_v1"
EXPECTED_HPO_EVIDENCE_SHA256 = "3a4ac8859f9e31f5912449a6c8a1376e7f4e3306791c7e60508cc7e9d956a24c"
EXPECTED_HPO_MODEL_SHA256 = "005f860d847a773c363170d2473fc8f3f77b4beab501c5db44833d2ac8e1e987"
EXPECTED_PREPARED_SHA256 = "a642671d0956f36405b837755cdf3dfb3c4870cde4a1d6f251046ffc8205a1c9"
EXPECTED_BASE_PARENT_ARTIFACT_SHA256 = "22c855e0667a58a73835505672b0ae6d03f12e9fb8d64f08893810199246e94e"
EXPECTED_BASE_COMPONENTS = {
    "survival": "e150180a9112f52a94cfa60770adb6c0a48517a7d94a4c26f6e5896e85269c18",
    "maxHP": "2c5b54d0a9420a9d0e3ab9a26f32b9900c4869490e4af49627009cde21efb4b0",
    "HP": "0c8b5aa8c5218d6cd6102b768cc86a474c9ef30953d4b034caedcc41a426109b",
    "potion": "ae1a1411990d272579de10564edb48c7f2ec1d14f1c72dacf5390a1415a0f1db",
    "downstream": "d07ead94b3abb9d12f272337e18aece6acd261cc4a39a36b21b82f904236af91",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def refit_ids(split_id: np.ndarray) -> np.ndarray:
    return np.concatenate((np.flatnonzero(split_id == 0),
                           np.flatnonzero(split_id == 1)))


def split_hpo_state(state: dict[str, torch.Tensor], scalar_mean: np.ndarray,
                    scalar_std: np.ndarray) -> tuple[dict, dict]:
    encoder = {
        "scalar_mean": torch.as_tensor(scalar_mean, dtype=torch.float32),
        "scalar_inv": torch.as_tensor(1.0 / np.maximum(scalar_std, 1e-6), dtype=torch.float32),
    }
    survival = {}
    for name, value in state.items():
        if name.startswith("win."):
            survival[name.removeprefix("win.")] = value
        elif not name.startswith("hp."):
            encoder[name] = value
    if set(survival) != {"weight", "bias"}:
        raise ValueError("HPO checkpoint does not contain the expected survival head")
    return encoder, survival


def verify_parity(arrays: dict, ids: np.ndarray, hpo_state: dict, encoder_state: dict,
                  survival_state: dict, mean: np.ndarray, std: np.ndarray) -> float:
    hpo = phase1.AttentionModel(
        torch, phase1.MAX_CARDS, phase1.MAX_RELICS, mean, std
    )
    hpo.device = torch.device("cpu")
    hpo.net.load_state_dict(hpo_state)
    promoted = attention.AttentionPointControlNet(torch, mean, std)
    promoted.net.encoder.load_state_dict(encoder_state)
    promoted.net.survival.load_state_dict(survival_state)
    hpo.net.eval(); promoted.net.eval()
    maximum = 0.0
    with torch.inference_mode():
        for start in range(0, len(ids), 256):
            chosen = ids[start:start + 256]
            values = phase1._torch_values(hpo, arrays, chosen)
            expected = torch.sigmoid(hpo.net(*values)[0])
            actual = torch.sigmoid(promoted.net(*values)[0])
            maximum = max(maximum, float(torch.max(torch.abs(expected - actual))))
    if maximum > 1e-7:
        raise ValueError(f"promoted survival prediction differs by {maximum}")
    return maximum


def create_shadow_parent(base_parent: Path, output_parent: Path) -> None:
    base_resolved = base_parent.resolve()
    output_resolved = output_parent.resolve()
    if output_resolved == base_resolved or base_resolved in output_resolved.parents:
        raise ValueError("output parent must be outside the base parent")
    if output_parent.exists():
        raise FileExistsError(f"refusing to overwrite {output_parent}")
    output_parent.mkdir(parents=True)
    for child in base_parent.iterdir():
        if child.name in {"full-union-survival-v1", "full-union-downstream-v1"}:
            continue
        (output_parent / child.name).symlink_to(child.resolve(), target_is_directory=child.is_dir())


def validate_base_parent(base_parent: Path) -> dict:
    receipts = {}
    for component, expected in EXPECTED_BASE_COMPONENTS.items():
        folder = base_parent / f"full-union-{component}-v1"
        receipt = json.loads((folder / "fit.json").read_text(encoding="utf-8"))
        artifact = folder / ("downstream.pt" if component == "downstream" else "component.pt")
        if receipt.get("artifactSha256") != expected or sha256(artifact) != expected:
            raise ValueError(f"base-parent {component} checkpoint differs")
        receipts[component] = receipt
    expected_upstream = {key: value for key, value in EXPECTED_BASE_COMPONENTS.items()
                         if key != "downstream"}
    preparation = json.loads((base_parent / "full-union-downstream-v1" /
                              "preparation.json").read_text(encoding="utf-8"))
    if preparation.get("upstreamBindings") != expected_upstream:
        raise ValueError("base-parent downstream preparation bindings differ")
    if receipts["downstream"].get("preparation") != preparation:
        raise ValueError("base-parent downstream fit/preparation receipts differ")
    return {"downstreamPreparation": preparation, "downstreamFit": receipts["downstream"]}


def rebind_downstream(base_parent: Path, output_parent: Path, base: dict,
                      survival_sha256: str, reviewed_commit: str) -> None:
    source = base_parent / "full-union-downstream-v1"
    target = output_parent / "full-union-downstream-v1"
    target.mkdir()
    for child in source.iterdir():
        if child.name in {"preparation.json", "fit.json"}:
            continue
        (target / child.name).symlink_to(child.resolve(), target_is_directory=child.is_dir())
    note = {
        "schemaVersion": SCHEMA,
        "sourceSha": reviewed_commit,
        "reason": "survival is not an input to downstream cache encoding or heads",
        "oldSurvivalSha256": EXPECTED_BASE_COMPONENTS["survival"],
        "newSurvivalSha256": survival_sha256,
        "downstreamArtifactUnchanged": True,
    }
    preparation = dict(base["downstreamPreparation"])
    preparation["upstreamBindings"] = dict(preparation["upstreamBindings"])
    preparation["upstreamBindings"]["survival"] = survival_sha256
    preparation["survivalBindingRebound"] = note
    fit = dict(base["downstreamFit"])
    fit["preparation"] = preparation
    fit["survivalBindingRebound"] = note
    (target / "preparation.json").write_text(
        json.dumps(preparation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (target / "fit.json").write_text(
        json.dumps(fit, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def promote(args) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    head = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"],
                          check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
    if head != args.reviewed_commit:
        raise ValueError("current HEAD does not match --reviewed-commit")
    if subprocess.run(["git", "-C", str(repo_root), "status", "--porcelain"],
                      check=True, text=True, stdout=subprocess.PIPE).stdout:
        raise ValueError("repository must be clean at the reviewed commit")

    evidence_path = Path(args.hpo_evidence)
    model_path = Path(args.hpo_model)
    prepared_path = Path(args.prepared)
    base_parent = Path(args.base_parent)
    output_parent = Path(args.output_parent)
    if sha256(evidence_path) != EXPECTED_HPO_EVIDENCE_SHA256:
        raise ValueError("HPO evidence hash differs")
    if sha256(model_path) != EXPECTED_HPO_MODEL_SHA256:
        raise ValueError("HPO model hash differs")
    if sha256(prepared_path) != EXPECTED_PREPARED_SHA256:
        raise ValueError("prepared array hash differs")
    if sha256(repo_root / "selfplay/models/combat_transition_near_full_except_smoke_v2.native") != EXPECTED_BASE_PARENT_ARTIFACT_SHA256:
        raise ValueError("tracked near-full baseline artifact differs")
    base = validate_base_parent(base_parent)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    winner = evidence["winner"]
    if winner["candidate"]["name"] != "hp_weight_2" or winner["selectedEpochs"] != 13:
        raise ValueError("HPO winner metadata differs")

    with np.load(prepared_path, allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    # Preserve the exact concatenation order used by the HPO winner's refit.
    combined = refit_ids(arrays["split_id"])
    mean = arrays["globals_continuous"][combined].mean(0)
    std = arrays["globals_continuous"][combined].std(0)
    hpo_state = torch.load(model_path, map_location="cpu", weights_only=True)
    encoder_state, survival_state = split_hpo_state(hpo_state, mean, std)
    parity_groups = []
    for split in (0, 1, 2):
        group = np.flatnonzero(arrays["split_id"] == split)
        parity_groups.append(group[np.linspace(0, len(group) - 1, 512, dtype=np.int64)])
    check_ids = np.concatenate(parity_groups)
    maximum = verify_parity(arrays, check_ids, hpo_state, encoder_state,
                            survival_state, mean, std)

    create_shadow_parent(base_parent, output_parent)
    component_dir = output_parent / "full-union-survival-v1"
    component_dir.mkdir()
    metadata = {
        "schemaVersion": SCHEMA,
        "sourceSha": head,
        "component": "survival",
        "origin": "targeted Phase-1 attention HPO winner",
        "hpoEvidenceSha256": EXPECTED_HPO_EVIDENCE_SHA256,
        "hpoModelSha256": EXPECTED_HPO_MODEL_SHA256,
        "preparedSha256": EXPECTED_PREPARED_SHA256,
        "normalizationPopulation": "TRAIN+VALIDATION rows from frozen Phase-1 split",
        "normalizationRows": int(len(combined)),
        "parityRows": int(len(check_ids)),
        "maxAbsoluteSurvivalProbabilityError": maximum,
        "winner": winner,
        "supportChanged": False,
    }
    component_path = component_dir / "component.pt"
    torch.save({"encoderStateDict": encoder_state,
                "headStateDicts": [survival_state], "metadata": metadata}, component_path)
    metadata["artifactSha256"] = sha256(component_path)
    (component_dir / "fit.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    rebind_downstream(base_parent, output_parent, base,
                      metadata["artifactSha256"], head)
    print(json.dumps({"outputParent": str(output_parent.resolve()), **metadata}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hpo-evidence", required=True)
    parser.add_argument("--hpo-model", required=True)
    parser.add_argument("--prepared", required=True)
    parser.add_argument("--base-parent", required=True)
    parser.add_argument("--output-parent", required=True)
    parser.add_argument("--reviewed-commit", required=True)
    promote(parser.parse_args())


if __name__ == "__main__":
    main()
