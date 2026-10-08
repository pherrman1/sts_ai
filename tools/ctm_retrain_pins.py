#!/usr/bin/env python3
"""Stage the STS_CTM_PINS file through the #418 CTM retrain chain.

Pins are module constants read at import time, so every stage needs every key
its imports read, including keys whose value only a later stage produces.
`init` writes a complete pins file: retrain decisions, the declared HP domain,
and production defaults as placeholders for every key not yet derived (listed
under `pending`). Each later command derives the keys one chain stage
determines from that stage's outputs and writes a new pins file next to the
old one; files are never overwritten. Run the commands in order:

    init      after `ctm_hp_domain.py expand` (D)      domain, warm starts, nulls
    corpus    after `ctm_corpus_adapter.py union` (U)  corpus SHA and path
    phase1    after Phase-1 audit/prepare/fit (P1)     split, prepared arrays, baselines
    phase2    after `combat_transition_surrogate.py prepare` (P2)
    near-full after near_full_refit x4 + near_full_downstream fit (PARENT)
    hpo       after `combat_transition_attention_hpo.py --frozen-winner` (HPO)

The union (stage 3) runs with the `init` pins, since its support predicate
reads the declared HP envelope from the expanded hp.pt. From `phase2` on, the
keys every near-full tool checks (composed_evaluate.verify_data) are final;
later commands must not change them, and `check` verifies that. Keys the
DeepSets chain (PR10b) derives stay pending.

    python tools/ctm_retrain_pins.py init --domain-dir D --out pins-0.json
    python tools/ctm_retrain_pins.py corpus --pins pins-0.json --union U --out pins-1.json
    python tools/ctm_retrain_pins.py check --pins pins-1.json
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

try:
    from tools import ctm_pins
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_pins

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("init", "corpus", "phase1", "phase2", "near-full", "hpo")
NEAR_FULL_COMPONENTS = ("survival", "maxHP", "HP", "potion")

# Retrain decisions (FULL-RETRAIN-PLAN.md): null disables a production-cohort
# count check that a new corpus cannot reproduce; the value is recorded instead.
DECISIONS = {
    "combat_transition_gold_evaluate.FROZEN_COUNTS": None,
    "combat_transition_potion_trajectory_evaluate.PREVIOUS_SUPPORT_ROWS": None,
    "combat_transition_deepset_potion_specialist.CONTROL_REPRODUCTION_REFERENCE_NLL": None,
}

# Keys each command derives. Everything else keeps its production value: warm
# starts (ARTIFACTS other than hp/relic), the frozen HPO winner, provenance
# labels, and keys no chain stage checks.
DERIVED = {
    "init": ("combat_transition_composed.ARTIFACTS", "combat_transition_composed.HP_CLASS_RANGE",
             "combat_transition_deepset_distill.EXPECTED_HP_CLASS_COUNT", *DECISIONS),
    "corpus": ("combat_transition_attention_ablation.EXPECTED_CORPUS_SHA256",
               "combat_transition_attention_hpo.EXPECTED_CORPUS_SHA256",
               "combat_transition_rng_audit.FROZEN_SHA",
               "combat_transition_surrogate.FROZEN_CORPUS_SHA256",
               "export_combat_transition_deepset_stack.CORPUS_SHA",
               "combat_transition_composed_evaluate.CORPUS"),
    "phase1": ("combat_transition_attention_ablation.EXPECTED_SPLIT_SHA256",
               "combat_transition_attention_hpo.EXPECTED_SPLIT_SHA256",
               "combat_transition_surrogate.FROZEN_SPLIT_SHA256",
               "export_combat_transition_deepset_stack.SPLIT_MANIFEST_SHA",
               "combat_transition_composed_evaluate.SPLIT",
               "combat_transition_attention_hpo.EXPECTED_PREPARED_MANIFEST_SHA256",
               "combat_transition_attention_hpo.EXPECTED_PREPARED_SHA256",
               "combat_transition_attention_hpo_promote.EXPECTED_PREPARED_SHA256",
               "export_combat_transition_deepset_stack.PREPARED_SHA",
               "export_combat_transition_deepset_stack.PREPARED_MANIFEST_SHA",
               "export_combat_transition_deepset_stack.PREPARED_ROWS",
               "export_combat_transition_deepset_stack.SCALAR_FIT_ROWS",
               "combat_transition_attention_hpo.EXPECTED_BASELINE_SHA256",
               "export_combat_transition_deepset_stack.SURVIVAL_SHA"),
    "phase2": ("combat_transition_frozen_composition.EXPECTED_HASHES",
               "combat_transition_composed_evaluate.PREPARED",
               "combat_transition_attention_ablation.EXPECTED_SUPPORTED_ROWS",
               "combat_transition_potion_decoder.SUPPORTED_ROWS",
               "combat_transition_frozen_composition.SUPPORTED_SPLIT_COUNTS"),
    "near-full": ("combat_transition_attention_hpo_promote.EXPECTED_BASE_COMPONENTS",),
    "hpo": ("combat_transition_attention_hpo_promote.EXPECTED_HPO_EVIDENCE_SHA256",
            "combat_transition_attention_hpo_promote.EXPECTED_HPO_MODEL_SHA256",
            "combat_transition_attention_hpo_promote.WINNER_EPOCHS"),
}

# Derived later by the DeepSets chain (PR10b); production placeholders until then.
DEEPSETS = (
    "combat_transition_deepset_distill.EXPECTED_CONTROL", "combat_transition_deepset_distill.EXPECTED_COUNTS",
    "combat_transition_deepset_distill.EXPECTED_TEACHERS", "combat_transition_deepset_distill.EXPECTED_TEACHER_OUTPUTS",
    "combat_transition_deepset_downstream.CACHE_ROWS", "combat_transition_deepset_downstream.DEEPSET_CHECKPOINT_SHA",
    "combat_transition_deepset_downstream.DEEPSET_NORMALIZATION_IDS_SHA",
    "combat_transition_deepset_downstream.DEEPSET_NORMALIZATION_ROWS",
    "combat_transition_deepset_downstream.DEEPSET_RECEIPT_SHA",
    "combat_transition_deepset_downstream.ELIGIBLE_VALIDATION_ROWS",
    "combat_transition_deepset_downstream.REFERENCE_CACHE_SHA",
    "combat_transition_deepset_downstream.REFERENCE_DOWNSTREAM_SHA",
    "combat_transition_deepset_downstream.REFERENCE_PREPARATION_SHA",
    "combat_transition_deepset_downstream.SOURCE_SHA", "combat_transition_deepset_downstream.TRAIN_ROWS",
    "combat_transition_deepset_downstream.TRAIN_SOURCES", "combat_transition_deepset_downstream.VALIDATION_ROWS",
    "combat_transition_deepset_downstream.VALIDATION_SOURCES",
    "combat_transition_deepset_potion.EXPECTED", "combat_transition_deepset_potion.EXPERIMENT_SHA",
    "combat_transition_deepset_potion.SELECTED_EPOCH", "combat_transition_deepset_potion.UNION_COUNTS",
    "combat_transition_deepset_potion_specialist.EXPECTED",
    "combat_transition_deepset_potion_specialist.RECURSIVE_VALIDATION_ROWS",
    "combat_transition_deepset_potion_specialist.UNION_COUNTS",
    "combat_transition_shared_encoder_distill.EXPECTED", "combat_transition_shared_encoder_distill.UNION_COUNTS",
    "export_combat_transition_deepset_stack.CONTROL_SHA", "export_combat_transition_deepset_stack.DOWNSTREAM_SHA",
    "export_combat_transition_deepset_stack.POTION_SELECTED_EPOCH",
    "export_combat_transition_deepset_stack.POTION_SPECIALIST_SHA",
    "export_combat_transition_deepset_stack.TRANSITION_SHA",
    "package_deepsets_lizard_artifact.FAST_PAYLOAD_SHA256", "package_deepsets_lizard_artifact.FAST_SOURCE_SHA256",
)

# composed_evaluate.verify_data records these (ARTIFACTS hashes, data paths and
# prepared hashes) and later stages re-check them: final from `phase2` on.
VERIFY_DATA_KEYS = (
    "combat_transition_composed.ARTIFACTS", "combat_transition_composed_evaluate.CORPUS",
    "combat_transition_composed_evaluate.SPLIT", "combat_transition_composed_evaluate.PREPARED",
    "combat_transition_frozen_composition.EXPECTED_HASHES", "combat_transition_rng_audit.FROZEN_SHA",
    "combat_transition_attention_ablation.EXPECTED_SPLIT_SHA256",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _jsonable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def production_values() -> dict:
    """Every declared key with its production default (pins must be inactive)."""
    if os.environ.get(ctm_pins.ENV):
        raise ValueError(f"unset {ctm_pins.ENV} to read the production defaults")
    sys.path.insert(0, str(ROOT))
    values = {}
    for key, source in ctm_pins.declared_keys().items():
        try:
            values[key] = ast.literal_eval(source)
        except ValueError:
            # A non-literal default (paths, the ARTIFACTS table): the module constant holds it.
            module, name = key.split(".", 1)
            values[key] = _jsonable(getattr(importlib.import_module(f"tools.{module}"), name))
    return values


def _write(out: Path, document: dict) -> dict:
    with Path(out).open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(document, indent=1, sort_keys=True) + "\n")
    return document


def _check_complete(pins: dict) -> None:
    declared = set(ctm_pins.declared_keys())
    if set(pins) != declared:
        raise ValueError(f"pins differ from the declared keys: missing {sorted(declared - set(pins))}, "
                         f"unknown {sorted(set(pins) - declared)}")


def init(domain_dir: Path, out: Path) -> dict:
    receipt = json.loads((domain_dir / "receipt.json").read_text(encoding="utf-8"))
    if receipt.get("schema") != "ctm_hp_domain_expansion_v1":
        raise ValueError("not a ctm_hp_domain expand receipt")
    for name in ("hp", "relic"):
        if sha256(domain_dir / f"{name}.pt") != receipt["outputs"][name]:
            raise ValueError(f"{name}.pt differs from the expansion receipt")
    pins = production_values()
    artifacts = dict(pins["combat_transition_composed.ARTIFACTS"])
    artifacts["hp"] = [str((domain_dir / "hp.pt").resolve()), receipt["outputs"]["hp"]]
    artifacts["relic"] = [str((domain_dir / "relic.pt").resolve()), receipt["outputs"]["relic"]]
    domain = receipt["domain"]
    pins.update({"combat_transition_composed.ARTIFACTS": artifacts,
                 "combat_transition_composed.HP_CLASS_RANGE": [domain["min"], domain["max"]],
                 "combat_transition_deepset_distill.EXPECTED_HP_CLASS_COUNT": domain["classes"]},
                **DECISIONS)
    if receipt["pins"]["combat_transition_composed.HP_CLASS_RANGE"] != [domain["min"], domain["max"]]:
        raise ValueError("expansion receipt pins disagree with its domain")
    _check_complete(pins)
    pending = sorted(k for stage in STAGES[1:] for k in DERIVED[stage]) + sorted(DEEPSETS)
    return _write(out, dict(schema=ctm_pins.SCHEMA, pins=pins, pending=pending,
                            stages=[dict(stage="init", inputs={"domainReceipt": sha256(domain_dir / "receipt.json")},
                                         domain=domain)]))


def _load(pins_path: Path, stage: str) -> dict:
    """The previous pins file, which must end with the stage before `stage`."""
    document = json.loads(Path(pins_path).read_text(encoding="utf-8"))
    if document.get("schema") != ctm_pins.SCHEMA:
        raise ValueError("not a pins file")
    done = [s["stage"] for s in document.get("stages", [])]
    if done != list(STAGES[:len(done)]) or len(done) >= len(STAGES) or STAGES[len(done)] != stage:
        raise ValueError(f"stage {stage!r} cannot follow {done}")
    return document


def _advance(pins_path: Path, stage: str, values: dict, inputs: dict, out: Path) -> dict:
    document = _load(pins_path, stage)
    if set(values) != set(DERIVED[stage]):
        raise ValueError(f"{stage}: derived keys differ from its declaration")
    pins = dict(document["pins"], **values)
    _check_complete(pins)
    pending = [k for k in document["pending"] if k not in values]
    return _write(out, dict(document, pins=pins, pending=pending,
                            stages=document["stages"] + [dict(stage=stage, inputs=inputs,
                                                              previousPinsSha256=sha256(pins_path))]))


def corpus(pins_path: Path, union: Path, out: Path) -> dict:
    _load(pins_path, "corpus")
    manifest = json.loads((union / "corpus.jsonl.manifest.json").read_text(encoding="utf-8"))
    if manifest.get("forcedSetup") != "union":
        raise ValueError("not a ctm_corpus_adapter union")
    data = union / "corpus.jsonl"
    digest = sha256(data)
    if digest != manifest["csv"]["sha256"]:
        raise ValueError("union corpus differs from its manifest")
    values = {k: digest for k in DERIVED["corpus"] if k != "combat_transition_composed_evaluate.CORPUS"}
    values["combat_transition_composed_evaluate.CORPUS"] = str(data.resolve())
    return _advance(pins_path, "corpus", values, {"corpusManifest": sha256(union / "corpus.jsonl.manifest.json")}, out)


def phase1(pins_path: Path, p1: Path, out: Path) -> dict:
    document = _load(pins_path, "phase1")
    split, prepared, manifest_path = p1 / "split_manifest.json", p1 / "prepared.npz", p1 / "prepared_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest["corpusSha256"] != document["pins"]["combat_transition_surrogate.FROZEN_CORPUS_SHA256"]:
        raise ValueError("Phase-1 prepared arrays are not from the pinned corpus")
    evidence = json.loads((p1 / "model_evidence.json").read_text(encoding="utf-8"))
    attention, deepsets = sha256(p1 / "attention.pt"), sha256(p1 / "deepsets.pt")
    if (evidence["modelArtifacts"]["attentionSha256"], evidence["modelArtifacts"]["deepsetsSha256"]) != (attention, deepsets):
        raise ValueError("Phase-1 checkpoints differ from model_evidence.json")
    split_sha, prepared_sha, manifest_sha = sha256(split), sha256(prepared), sha256(manifest_path)
    values = {
        "combat_transition_attention_ablation.EXPECTED_SPLIT_SHA256": split_sha,
        "combat_transition_attention_hpo.EXPECTED_SPLIT_SHA256": split_sha,
        "combat_transition_surrogate.FROZEN_SPLIT_SHA256": split_sha,
        "export_combat_transition_deepset_stack.SPLIT_MANIFEST_SHA": split_sha,
        "combat_transition_composed_evaluate.SPLIT": str(split.resolve()),
        "combat_transition_attention_hpo.EXPECTED_PREPARED_MANIFEST_SHA256": manifest_sha,
        "combat_transition_attention_hpo.EXPECTED_PREPARED_SHA256": prepared_sha,
        "combat_transition_attention_hpo_promote.EXPECTED_PREPARED_SHA256": prepared_sha,
        "export_combat_transition_deepset_stack.PREPARED_SHA": prepared_sha,
        "export_combat_transition_deepset_stack.PREPARED_MANIFEST_SHA": manifest_sha,
        "export_combat_transition_deepset_stack.PREPARED_ROWS": int(manifest["rows"]),
        "export_combat_transition_deepset_stack.SCALAR_FIT_ROWS": int(manifest["counts"]["0"]) + int(manifest["counts"]["1"]),
        "combat_transition_attention_hpo.EXPECTED_BASELINE_SHA256": attention,
        "export_combat_transition_deepset_stack.SURVIVAL_SHA": deepsets,
    }
    return _advance(pins_path, "phase1", values, {"modelEvidence": sha256(p1 / "model_evidence.json")}, out)


def phase2(pins_path: Path, p2: Path, out: Path) -> dict:
    document = _load(pins_path, "phase2")
    manifest = json.loads((p2 / "prepared_manifest.json").read_text(encoding="utf-8"))
    if manifest["corpusSha256"] != document["pins"]["combat_transition_surrogate.FROZEN_CORPUS_SHA256"]:
        raise ValueError("Phase-2 arrays are not from the pinned corpus")
    hashes = dict(document["pins"]["combat_transition_frozen_composition.EXPECTED_HASHES"])
    # The .pt entries are production warm starts that only tools outside the chain read.
    for name in ("prepared.npz", "prepared_manifest.json", "target_spec.json"):
        hashes[name] = sha256(p2 / name)
    counts = manifest["counts"]
    values = {
        "combat_transition_frozen_composition.EXPECTED_HASHES": hashes,
        "combat_transition_composed_evaluate.PREPARED": str(p2.resolve()),
        "combat_transition_attention_ablation.EXPECTED_SUPPORTED_ROWS": int(counts["supported"]),
        "combat_transition_potion_decoder.SUPPORTED_ROWS": int(counts["supported"]),
        "combat_transition_frozen_composition.SUPPORTED_SPLIT_COUNTS": [
            int(counts["supportedTrain"]), int(counts["supportedValidation"]), int(counts["supportedTest"])],
    }
    return _advance(pins_path, "phase2", values, {"preparedManifest": hashes["prepared_manifest.json"]}, out)


def near_full(pins_path: Path, parent: Path, out: Path) -> dict:
    _load(pins_path, "near-full")
    components = {}
    for component in NEAR_FULL_COMPONENTS + ("downstream",):
        folder = parent / f"full-union-{component}-v1"
        artifact = folder / ("downstream.pt" if component == "downstream" else "component.pt")
        digest = sha256(artifact)
        if json.loads((folder / "fit.json").read_text(encoding="utf-8"))["artifactSha256"] != digest:
            raise ValueError(f"{component} checkpoint differs from its fit.json")
        components[component] = digest
    values = {"combat_transition_attention_hpo_promote.EXPECTED_BASE_COMPONENTS": components}
    return _advance(pins_path, "near-full", values, {"parent": str(parent.resolve())}, out)


def hpo(pins_path: Path, folder: Path, out: Path) -> dict:
    document = _load(pins_path, "hpo")
    evidence = json.loads((folder / "attention_hpo_evidence.json").read_text(encoding="utf-8"))
    winner = document["pins"]["combat_transition_attention_hpo_promote.WINNER"]
    if evidence["winner"]["candidate"]["name"] != winner:
        raise ValueError(f"HPO winner is not the frozen {winner}")
    values = {
        "combat_transition_attention_hpo_promote.EXPECTED_HPO_EVIDENCE_SHA256": sha256(folder / "attention_hpo_evidence.json"),
        "combat_transition_attention_hpo_promote.EXPECTED_HPO_MODEL_SHA256": sha256(folder / "attention_tuned.pt"),
        "combat_transition_attention_hpo_promote.WINNER_EPOCHS": int(evidence["winner"]["selectedEpochs"]),
    }
    return _advance(pins_path, "hpo", values, {"evidence": values[
        "combat_transition_attention_hpo_promote.EXPECTED_HPO_EVIDENCE_SHA256"]}, out)


def check(pins_path: Path, previous: Path | None = None) -> dict:
    """Completeness, and (with --previous) that the verify_data keys did not change after phase2."""
    document = json.loads(Path(pins_path).read_text(encoding="utf-8"))
    _check_complete(document["pins"])
    stages = [s["stage"] for s in document["stages"]]
    changed = []
    if previous is not None:
        before = json.loads(Path(previous).read_text(encoding="utf-8"))
        if "phase2" in [s["stage"] for s in before["stages"]]:
            changed = [k for k in VERIFY_DATA_KEYS if before["pins"][k] != document["pins"][k]]
    if changed:
        raise ValueError(f"keys recorded by verify_data changed after phase2: {changed}")
    return dict(stages=stages, pending=document["pending"], pinsSha256=sha256(pins_path))


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init"); p.add_argument("--domain-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    for name, flag in (("corpus", "--union"), ("phase1", "--p1"), ("phase2", "--p2"),
                       ("near-full", "--parent"), ("hpo", "--hpo-dir")):
        p = sub.add_parser(name); p.add_argument("--pins", type=Path, required=True)
        p.add_argument(flag, dest="folder", type=Path, required=True)
        p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("check"); p.add_argument("--pins", type=Path, required=True)
    p.add_argument("--previous", type=Path)
    args = parser.parse_args(argv)
    if args.command == "init":
        result = init(args.domain_dir, args.out)
        result = dict(pending=len(result["pending"]))
    elif args.command == "check":
        result = check(args.pins, args.previous)
    else:
        step = {"corpus": corpus, "phase1": phase1, "phase2": phase2, "near-full": near_full, "hpo": hpo}[args.command]
        result = step(args.pins, args.folder, args.out)
        result = dict(stages=[s["stage"] for s in result["stages"]], pending=len(result["pending"]))
    print(json.dumps(result, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
