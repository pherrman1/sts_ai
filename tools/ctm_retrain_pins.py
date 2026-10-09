#!/usr/bin/env python3
"""Stage the STS_CTM_PINS file through the #418 CTM retrain chain.

Pins are module constants read at import time, so every stage needs every key
its imports read, including keys whose value only a later stage produces.
`init` writes a complete pins file: retrain decisions, the declared HP domain,
and production defaults as placeholders for every key not yet derived (listed
under `pending`). Each later command derives the keys one chain stage
determines from that stage's outputs and writes a new pins file next to the
old one; files are never overwritten. Run the commands in order:

    init       after `ctm_hp_domain.py expand` (D): domain, warm starts, nulls
    corpus     after `ctm_corpus_adapter.py union` (U)
    phase1     after Phase-1 audit/prepare/fit (P1)
    phase2     after `combat_transition_surrogate.py prepare` (P2)
    near-full  after near_full_refit x4, ctm_near_full_inputs, near_full_downstream fit (PARENT)
    hpo        after `combat_transition_attention_hpo.py --frozen-winner` (HPO)
    control    after `export_combat_transition_near_full.py` (STD.native, before any capability)
    teachers   after `combat_transition_shared_encoder_distill.py --teachers-only` (S17)
    distill    after `combat_transition_deepset_distill.py` (S18, no --control-dir)
    downstream after `combat_transition_deepset_downstream.py prepare/fit/compare` (S19);
               a REJECTED compare needs `--override` (singleton-accuracy failures only)
    potion     after `combat_transition_deepset_potion.py` (S20)
    specialist after `combat_transition_deepset_potion_specialist.py --arms C` (S21)
    fast       after `export_combat_transition_deepset_stack.py` (FAST0.native)

The union (stage 3) runs with the `init` pins, since its support predicate
reads the declared HP envelope from the expanded hp.pt. From `phase2` on, the
keys every near-full tool checks (composed_evaluate.verify_data) are final;
later commands must not change them, and `check` verifies that. A derived
name `KEY[field]` sets one field of a dict-valued pin; its other fields keep
production values until their own stage. After `fast` nothing is pending.

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
import struct
import sys

import numpy as np

try:
    from tools import ctm_pins
except ModuleNotFoundError:  # direct invocation from the tools directory
    import ctm_pins

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("init", "corpus", "phase1", "phase2", "near-full", "hpo", "control", "teachers", "distill",
          "downstream", "potion", "specialist", "fast")
NEAR_FULL_COMPONENTS = ("survival", "maxHP", "HP", "potion")
POTION = "combat_transition_deepset_potion.EXPECTED"
SPECIALIST = "combat_transition_deepset_potion_specialist.EXPECTED"
DOWNSTREAM = "combat_transition_deepset_downstream."
EXPORT = "export_combat_transition_deepset_stack."
SEQUENCES = ("rowSequence", "sourceSequence", "splitSequence")
MAGIC = b"COMBAT_TRANSITION_RUNTIME_V2\0"

# Retrain decisions (FULL-RETRAIN-PLAN.md): null disables a production-cohort
# check that a new corpus cannot reproduce; the value is recorded instead.
DECISIONS = {
    "combat_transition_gold_evaluate.FROZEN_COUNTS": None,
    "combat_transition_potion_trajectory_evaluate.PREVIOUS_SUPPORT_ROWS": None,
    "combat_transition_deepset_potion_specialist.CONTROL_REPRODUCTION_REFERENCE_NLL": None,
    # No shared-Attention control run: production already chose the DeepSets student.
    "combat_transition_deepset_distill.EXPECTED_CONTROL": None,
}

# Names each command derives.
DERIVED = {
    "init": ("combat_transition_composed.ARTIFACTS", "combat_transition_composed.HP_CLASS_RANGE",
             "combat_transition_deepset_distill.EXPECTED_HP_CLASS_COUNT", *DECISIONS),
    "corpus": ("combat_transition_attention_ablation.EXPECTED_CORPUS_SHA256",
               "combat_transition_attention_hpo.EXPECTED_CORPUS_SHA256",
               "combat_transition_rng_audit.FROZEN_SHA",
               "combat_transition_surrogate.FROZEN_CORPUS_SHA256",
               EXPORT + "CORPUS_SHA",
               "combat_transition_composed_evaluate.CORPUS"),
    "phase1": ("combat_transition_attention_ablation.EXPECTED_SPLIT_SHA256",
               "combat_transition_attention_hpo.EXPECTED_SPLIT_SHA256",
               "combat_transition_surrogate.FROZEN_SPLIT_SHA256",
               EXPORT + "SPLIT_MANIFEST_SHA",
               "combat_transition_composed_evaluate.SPLIT",
               "combat_transition_attention_hpo.EXPECTED_PREPARED_MANIFEST_SHA256",
               "combat_transition_attention_hpo.EXPECTED_PREPARED_SHA256",
               "combat_transition_attention_hpo_promote.EXPECTED_PREPARED_SHA256",
               EXPORT + "PREPARED_SHA", EXPORT + "PREPARED_MANIFEST_SHA",
               EXPORT + "PREPARED_ROWS", EXPORT + "SCALAR_FIT_ROWS",
               "combat_transition_attention_hpo.EXPECTED_BASELINE_SHA256",
               EXPORT + "SURVIVAL_SHA"),
    "phase2": ("combat_transition_frozen_composition.EXPECTED_HASHES",
               "combat_transition_composed_evaluate.PREPARED",
               "combat_transition_attention_ablation.EXPECTED_SUPPORTED_ROWS",
               "combat_transition_potion_decoder.SUPPORTED_ROWS",
               "combat_transition_frozen_composition.SUPPORTED_SPLIT_COUNTS"),
    "near-full": ("combat_transition_attention_hpo_promote.EXPECTED_BASE_COMPONENTS",
                  "combat_transition_deepset_distill.EXPECTED_TEACHERS",
                  "combat_transition_shared_encoder_distill.EXPECTED",
                  "combat_transition_deepset_distill.EXPECTED_COUNTS",
                  "combat_transition_shared_encoder_distill.UNION_COUNTS",
                  "combat_transition_deepset_potion.UNION_COUNTS",
                  "combat_transition_deepset_potion_specialist.UNION_COUNTS",
                  "combat_transition_deepset_potion_specialist.RECURSIVE_VALIDATION_ROWS",
                  *(DOWNSTREAM + k for k in ("REFERENCE_PREPARATION_SHA", "REFERENCE_CACHE_SHA",
                                             "REFERENCE_DOWNSTREAM_SHA", "SOURCE_SHA", "CACHE_ROWS", "TRAIN_ROWS",
                                             "TRAIN_SOURCES", "ELIGIBLE_VALIDATION_ROWS", "VALIDATION_ROWS",
                                             "VALIDATION_SOURCES")),
                  *(f"{POTION}[{k}]" for k in ("cache", *SEQUENCES, "dedicatedPotionComponent", "sourceSha")),
                  *(f"{SPECIALIST}[{k}]" for k in ("cache", *SEQUENCES, "component"))),
    "hpo": ("combat_transition_attention_hpo_promote.EXPECTED_HPO_EVIDENCE_SHA256",
            "combat_transition_attention_hpo_promote.EXPECTED_HPO_MODEL_SHA256",
            "combat_transition_attention_hpo_promote.WINNER_EPOCHS"),
    "control": (EXPORT + "CONTROL_SHA",),
    "teachers": ("combat_transition_deepset_distill.EXPECTED_TEACHER_OUTPUTS",),
    "distill": (DOWNSTREAM + "DEEPSET_CHECKPOINT_SHA", DOWNSTREAM + "DEEPSET_RECEIPT_SHA",
                DOWNSTREAM + "DEEPSET_NORMALIZATION_ROWS", DOWNSTREAM + "DEEPSET_NORMALIZATION_IDS_SHA",
                f"{POTION}[candidateCheckpoint]", f"{POTION}[candidateReceipt]",
                "combat_transition_deepset_potion.SELECTED_EPOCH", "combat_transition_deepset_potion.EXPERIMENT_SHA",
                f"{SPECIALIST}[encoder]", EXPORT + "TRANSITION_SHA"),
    "downstream": (f"{POTION}[candidateZ]", f"{POTION}[candidateRows]", EXPORT + "DOWNSTREAM_SHA"),
    "potion": (f"{SPECIALIST}[decoder]", f"{SPECIALIST}[attentionReferenceDecoder]",
               f"{SPECIALIST}[attentionReferenceReceipt]"),
    "specialist": (EXPORT + "POTION_SPECIALIST_SHA", EXPORT + "POTION_SELECTED_EPOCH"),
    "fast": ("package_deepsets_lizard_artifact.FAST_SOURCE_SHA256",
             "package_deepsets_lizard_artifact.FAST_PAYLOAD_SHA256"),
}

# Never derived: production warm starts and provenance labels the retrain reuses,
# the frozen HPO winner, and keys no chain stage checks.
KEPT = (
    "combat_transition_composed.BASELINE", "combat_transition_composed.RUNS",
    "combat_transition_attention_hpo_promote.WINNER", DOWNSTREAM + "BASELINE_SHA", f"{POTION}[baseline]",
    "combat_transition_hp_targets.SPLIT", "combat_transition_hp_targets.SPLIT_HASH",
    "combat_transition_relic_trajectory.HP_HASH", "combat_transition_relic_trajectory.POTION_HASH",
    "combat_transition_relic_trajectory.ENCODER_HASH", "combat_transition_stochastic_hp.CONTROL_HASH",
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
    pending = sorted(k for stage in STAGES[1:] for k in DERIVED[stage])
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
    pins = dict(document["pins"])
    for name, value in values.items():
        key, _, field = name.partition("[")
        if field:
            pins[key] = dict(pins[key], **{field.rstrip("]"): value})
        else:
            pins[key] = value
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


def _array_digest(value) -> str:
    """`combat_transition_shared_potion_encoder.digest`: SHA256 of the raw array bytes."""
    return hashlib.sha256(np.asarray(value).tobytes()).hexdigest()


def _json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def near_full(pins_path: Path, parent: Path, out: Path) -> dict:
    """Stages 9-12: the Attention components, the trajectory cache and the downstream cache.

    Also every DeepSets-chain value these outputs determine (teachers, populations,
    reference caches), so the DeepSets stages can import with final values.
    """
    _load(pins_path, "near-full")
    components = {}
    for component in NEAR_FULL_COMPONENTS + ("downstream",):
        folder = parent / f"full-union-{component}-v1"
        artifact = folder / ("downstream.pt" if component == "downstream" else "component.pt")
        digest = sha256(artifact)
        if _json(folder / "fit.json")["artifactSha256"] != digest:
            raise ValueError(f"{component} checkpoint differs from its fit.json")
        components[component] = digest
    trajectory = parent / "potion-trajectory-v2"
    cache_sha = sha256(trajectory / "cache.npz")
    if _json(trajectory / "preparation.json")["cacheSha256"] != cache_sha:
        raise ValueError("trajectory cache differs from its preparation receipt")
    with np.load(trajectory / "cache.npz") as raw:
        cache = {k: raw[k] for k in ("ids", "source", "split", "win")}
    graphs = _json(trajectory / "graphs.json")
    win, split = cache["win"].astype(bool), cache["split"]
    train, validation = np.flatnonzero(win & (split == 0)), np.flatnonzero(win & (split == 1))
    counts = {name: dict(rows=int(len(ids)), sources=int(len(np.unique(cache["source"][ids]))))
              for name, ids in (("TRAIN", train), ("VALIDATION", validation))}
    target = np.concatenate((train, validation))
    sequences = {k: _array_digest(cache[f][target]) for k, f in zip(SEQUENCES, ("ids", "source", "split"))}
    recursive = sum(1 for i in validation if graphs.get(str(int(i)), {}).get("rounds", 0) > 1)

    # Downstream eligibility (combat_transition_deepset_downstream.eligible_train/_validation).
    downstream = parent / "full-union-downstream-v1"
    labels = _json(parent / "full-union-downstream-labels-v1" / "preparation.json")
    source_sha = labels["sourceSha"]
    with np.load(downstream / "cache.npz") as raw:
        flags = raw["observed"].any(-1) | raw["writhing"] | raw["dagger"]
    with (downstream / "affected_rows.jsonl").open(encoding="utf-8") as stream:
        records = [json.loads(line)["index"] for line in stream]
    eligible = win & (flags | np.isin(np.arange(len(cache["ids"])), records))
    d_train, d_validation = np.flatnonzero(eligible & (split == 0)), np.flatnonzero(eligible & (split == 1))
    fit = _json(downstream / "fit.json")
    if (fit["trainRows"], fit["validationRows"]) != (len(d_train), len(d_validation)):
        raise ValueError("downstream eligibility differs from the near-full downstream fit")
    potion_fit = _json(parent / "full-union-potion-v1" / "fit.json")
    if potion_fit["sourceSha"] != source_sha:
        raise ValueError("run near_full_refit and ctm_near_full_inputs at the same commit: the DeepSets "
                         "potion stage binds both to one sourceSha")
    teachers = {k: components[k] for k in ("maxHP", "HP")}
    values = {
        "combat_transition_attention_hpo_promote.EXPECTED_BASE_COMPONENTS": components,
        "combat_transition_deepset_distill.EXPECTED_TEACHERS": teachers,
        "combat_transition_shared_encoder_distill.EXPECTED": teachers,
        "combat_transition_deepset_distill.EXPECTED_COUNTS": counts,
        "combat_transition_shared_encoder_distill.UNION_COUNTS": counts,
        "combat_transition_deepset_potion.UNION_COUNTS": counts,
        "combat_transition_deepset_potion_specialist.UNION_COUNTS": counts,
        "combat_transition_deepset_potion_specialist.RECURSIVE_VALIDATION_ROWS": recursive,
        DOWNSTREAM + "REFERENCE_PREPARATION_SHA": cache_sha,
        DOWNSTREAM + "REFERENCE_CACHE_SHA": sha256(downstream / "cache.npz"),
        DOWNSTREAM + "REFERENCE_DOWNSTREAM_SHA": components["downstream"],
        DOWNSTREAM + "SOURCE_SHA": source_sha,
        DOWNSTREAM + "CACHE_ROWS": int(len(cache["ids"])),
        DOWNSTREAM + "TRAIN_ROWS": int(len(d_train)),
        DOWNSTREAM + "TRAIN_SOURCES": int(len(np.unique(cache["source"][d_train]))),
        DOWNSTREAM + "ELIGIBLE_VALIDATION_ROWS": int(len(d_validation)),
        DOWNSTREAM + "VALIDATION_ROWS": int(len(d_validation)),
        DOWNSTREAM + "VALIDATION_SOURCES": int(len(np.unique(cache["source"][d_validation]))),
        f"{POTION}[cache]": cache_sha, f"{POTION}[dedicatedPotionComponent]": components["potion"],
        f"{POTION}[sourceSha]": source_sha,
        f"{SPECIALIST}[cache]": cache_sha, f"{SPECIALIST}[component]": components["potion"],
        **{f"{POTION}[{k}]": v for k, v in sequences.items()},
        **{f"{SPECIALIST}[{k}]": v for k, v in sequences.items()},
    }
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


def control(pins_path: Path, artifact: Path, out: Path) -> dict:
    _load(pins_path, "control")
    data = artifact.read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError("not a combat transition runtime artifact")
    version, length = struct.unpack_from("<II", data, len(MAGIC))
    header = json.loads(data[len(MAGIC) + 8:len(MAGIC) + 8 + length])
    if header.get("capabilities") or "researchCandidate" in header:
        raise ValueError("the DeepSets export copies the plain Attention export; add capabilities afterwards")
    return _advance(pins_path, "control", {EXPORT + "CONTROL_SHA": sha256(artifact)},
                    {"artifact": str(artifact.resolve())}, out)


def teachers(pins_path: Path, folder: Path, out: Path) -> dict:
    document = _load(pins_path, "teachers")
    result = _json(folder / "results.json")
    if result.get("counts") != document["pins"]["combat_transition_deepset_distill.EXPECTED_COUNTS"]:
        raise ValueError("teacher cache population differs from the near-full counts")
    outputs = {name: sha256(folder / f"teacher-{name}.npy") for name in ("maxHP", "HP")}
    if result["provenance"]["teacherOutputs"] != outputs:
        raise ValueError("teacher outputs differ from their receipt")
    return _advance(pins_path, "teachers", {"combat_transition_deepset_distill.EXPECTED_TEACHER_OUTPUTS": outputs},
                    {"results": sha256(folder / "results.json")}, out)


def distill(pins_path: Path, folder: Path, out: Path) -> dict:
    _load(pins_path, "distill")
    result = _json(folder / "results.json")
    checkpoint, receipt = sha256(folder / "student.pt"), sha256(folder / "results.json")
    if result["checkpointSha256"] != checkpoint:
        raise ValueError("DeepSets student differs from its receipt")
    if result["decision"] != "SHARED_TRANSITION_ENCODER_GO":
        raise ValueError(f"DeepSets distill decision {result['decision']}: the DeepSets stages require GO")
    values = {
        DOWNSTREAM + "DEEPSET_CHECKPOINT_SHA": checkpoint, DOWNSTREAM + "DEEPSET_RECEIPT_SHA": receipt,
        DOWNSTREAM + "DEEPSET_NORMALIZATION_ROWS": result["scalarNormalization"]["rows"],
        DOWNSTREAM + "DEEPSET_NORMALIZATION_IDS_SHA": result["scalarNormalization"]["rowIdsSha256"],
        f"{POTION}[candidateCheckpoint]": checkpoint, f"{POTION}[candidateReceipt]": receipt,
        "combat_transition_deepset_potion.SELECTED_EPOCH": result["selectedEpoch"],
        "combat_transition_deepset_potion.EXPERIMENT_SHA": result["experimentSha"],
        f"{SPECIALIST}[encoder]": checkpoint, EXPORT + "TRANSITION_SHA": checkpoint,
    }
    return _advance(pins_path, "distill", values, {"results": receipt}, out)


OVERRIDABLE_DOWNSTREAM_FAILURE = "singleton exact-label accuracy drop exceeds 0.5pp"


def downstream_override(qualification_path: Path, override_path: Path) -> str:
    """Accept a REJECTED downstream compare only through a recorded override.

    The override binds the exact qualification receipt and its failure list,
    names who approved it and why, and may waive only singleton exact-label
    accuracy failures; NLL, finite/legal and support failures are never waivable.
    """
    qualification, override = _json(qualification_path), _json(override_path)
    if override.get("schema") != "ctm_gate_override_v1" or override.get("stage") != "downstream":
        raise ValueError("override is not a ctm_gate_override_v1 for the downstream stage")
    if override.get("qualificationSha256") != sha256(qualification_path):
        raise ValueError("override does not bind this qualification.json")
    if qualification["decision"] != "DEEPSET_DOWNSTREAM_REJECTED" or qualification.get("finiteAndLegal") is not True:
        raise ValueError("override applies only to a finite/legal DEEPSET_DOWNSTREAM_REJECTED compare")
    failures = qualification.get("failures") or []
    if not failures or override.get("failures") != failures:
        raise ValueError("override failures differ from the qualification failures")
    if not all(f.endswith(OVERRIDABLE_DOWNSTREAM_FAILURE) for f in failures):
        raise ValueError("override may waive only singleton exact-label accuracy failures")
    if not all(isinstance(override.get(k), str) and override[k].strip() for k in ("approval", "reason")):
        raise ValueError("override must name its approval and reason")
    if not isinstance(override.get("evidence"), dict) or not override["evidence"]:
        raise ValueError("override must carry its evidence")
    return sha256(override_path)


def downstream(pins_path: Path, folder: Path, out: Path, override: Path | None = None) -> dict:
    _load(pins_path, "downstream")
    representation = _json(folder / "representation.json")
    z = sha256(folder / "z_deepset.npy")
    if representation["candidateZSha256"] != z:
        raise ValueError("DeepSets representation differs from its receipt")
    head = sha256(folder / "downstream.pt")
    qualification = _json(folder / "qualification.json")
    inputs = {"representation": sha256(folder / "representation.json"),
              "qualification": sha256(folder / "qualification.json")}
    if override is not None:
        inputs["override"] = downstream_override(folder / "qualification.json", override)
    elif qualification["decision"] != "DEEPSET_DOWNSTREAM_GO":
        raise ValueError(f"the DeepSets downstream head must pass compare (require GO, got {qualification['decision']})")
    if qualification["candidate"]["checkpointSha256"] != head:
        raise ValueError("downstream.pt differs from the qualified candidate")
    values = {f"{POTION}[candidateZ]": z, f"{POTION}[candidateRows]": representation["generatedRows"],
              EXPORT + "DOWNSTREAM_SHA": head}
    return _advance(pins_path, "downstream", values, inputs, out)


def potion(pins_path: Path, folder: Path, out: Path) -> dict:
    _load(pins_path, "potion")
    # A: the dedicated (Attention) potion encoder's decoder; B: the DeepSets candidate's.
    values = {f"{SPECIALIST}[decoder]": sha256(folder / "B.pt"),
              f"{SPECIALIST}[attentionReferenceDecoder]": sha256(folder / "A.pt"),
              f"{SPECIALIST}[attentionReferenceReceipt]": sha256(folder / "results.json")}
    return _advance(pins_path, "potion", values, {"results": sha256(folder / "results.json")}, out)


def specialist(pins_path: Path, folder: Path, out: Path) -> dict:
    _load(pins_path, "specialist")
    import torch
    epoch = torch.load(folder / "C.pt", map_location="cpu", weights_only=False)["selectedEpoch"]
    values = {EXPORT + "POTION_SPECIALIST_SHA": sha256(folder / "C.pt"), EXPORT + "POTION_SELECTED_EPOCH": int(epoch)}
    return _advance(pins_path, "specialist", values, {"results": sha256(folder / "results.json")}, out)


def fast(pins_path: Path, artifact: Path, out: Path) -> dict:
    _load(pins_path, "fast")
    data = artifact.read_bytes()
    if not data.startswith(MAGIC):
        raise ValueError("not a combat transition runtime artifact")
    _, length = struct.unpack_from("<II", data, len(MAGIC))
    payload = data[len(MAGIC) + 8 + length:]
    values = {"package_deepsets_lizard_artifact.FAST_SOURCE_SHA256": hashlib.sha256(data).hexdigest(),
              "package_deepsets_lizard_artifact.FAST_PAYLOAD_SHA256": hashlib.sha256(payload).hexdigest()}
    return _advance(pins_path, "fast", values, {"artifact": str(artifact.resolve())}, out)


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


STEPS = {"corpus": corpus, "phase1": phase1, "phase2": phase2, "near-full": near_full, "hpo": hpo,
         "control": control, "teachers": teachers, "distill": distill, "downstream": downstream,
         "potion": potion, "specialist": specialist, "fast": fast}
FOLDERS = {"corpus": "--union", "phase1": "--p1", "phase2": "--p2", "near-full": "--parent", "hpo": "--hpo-dir",
           "control": "--artifact", "teachers": "--dir", "distill": "--dir", "downstream": "--dir",
           "potion": "--dir", "specialist": "--dir", "fast": "--artifact"}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init"); p.add_argument("--domain-dir", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    for name, flag in FOLDERS.items():
        p = sub.add_parser(name); p.add_argument("--pins", type=Path, required=True)
        p.add_argument(flag, dest="folder", type=Path, required=True)
        p.add_argument("--out", type=Path, required=True)
        if name == "downstream":
            p.add_argument("--override", type=Path, help="ctm_gate_override_v1 JSON accepting a REJECTED compare")
    p = sub.add_parser("check"); p.add_argument("--pins", type=Path, required=True)
    p.add_argument("--previous", type=Path)
    args = parser.parse_args(argv)
    if args.command == "init":
        result = init(args.domain_dir, args.out)
        result = dict(pending=len(result["pending"]))
    elif args.command == "check":
        result = check(args.pins, args.previous)
    else:
        extra = dict(override=args.override) if args.command == "downstream" else {}
        result = STEPS[args.command](args.pins, args.folder, args.out, **extra)
        result = dict(stages=[s["stage"] for s in result["stages"]], pending=len(result["pending"]))
    print(json.dumps(result, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
