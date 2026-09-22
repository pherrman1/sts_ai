#!/usr/bin/env python3
"""Prepare frozen Silver root priors, seal replay inputs, and judge replay rows."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import silver_prior_dataset as dataset
import silver_prior_projection as projection
import train_silver_prior as trainer

CORPUS_SHA = {
    "release": "b32d8d79b44ee799af05892e79e45fb146f4859df58364722d7cd92531bd8419",
    "binding": "7febae9df90e427ad5db631a2004ff4c4cdd579346d22d25b3e1f4532af96e17",
    "selection": "ed91b3bb4c6983be3701333320f1e6c12f7332e3e371ac24b857a76a47d3b5ed",
    "vocabulary": "7e07db8b10618d7c1e9b9b1b31d8196950c03060c54fd4d25fd057ac7918cd46",
}
CHECKPOINT_SHA = "b756c3e6576bdb53085f24aeb1102e4e2fe55fd7469c55546c99f068ccf40e24"
TAU = 1.179975000005129
ARMS = ("A_UCT", "U_UNIFORM", "M_LEARNED", "O_ORACLE_L")
EXPERIMENT_ID = "silver-prior-root-screen-v1/20260922"
BOOTSTRAPS = 10_000


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_jsonl(path: Path, rows) -> None:
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"refusing existing evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush()


def softmax(values, temperature=1.0):
    values = np.asarray(values, dtype=np.float64)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all() or temperature <= 0:
        raise ValueError("invalid softmax input")
    scaled = values / temperature
    exp = np.exp(scaled - scaled.max())
    probs = exp / exp.sum()
    if not np.isfinite(probs).all() or np.any(probs <= 0) or not math.isclose(float(probs.sum()), 1.0, abs_tol=1e-12):
        raise ValueError("invalid normalized prior")
    return probs.tolist()


def sealed_manifests(corpus: Path):
    corpus = Path(corpus)
    release, binding, selection, vocab, plan = [dataset.read(corpus / name) for name in
        ("release.json", "binding.json", "selection.json", "vocabulary.json", "plan.json")]
    for value in (release, binding, selection, plan):
        dataset.check_seal(value)
    projection.validate_vocabulary(vocab)
    if {"release": release["sha256"], "binding": binding["sha256"],
            "selection": selection["sha256"], "vocabulary": vocab["sha256"]} != CORPUS_SHA:
        raise ValueError("frozen corpus hash mismatch")
    if (not release["training_ready"] or release["binding_sha256"] != binding["sha256"]
            or release["selection_sha256"] != selection["sha256"]
            or binding["plan_sha256"] != plan["sha256"]
            or selection["plan_sha256"] != plan["sha256"]
            or plan["vocabulary_sha256"] != vocab["sha256"]
            or selection["pilot"]):
        raise ValueError("frozen corpus binding mismatch")
    return corpus, release, binding, selection, vocab, plan


def selected_hashes(release, allowed_paths):
    """Resolve only requested VALIDATION artifact hashes from the sealed release."""
    allowed_paths = set(allowed_paths)
    found = {}
    for item in release["files"]:
        path = item["path"]
        if path in allowed_paths:
            if path in found:
                raise ValueError("duplicate selected artifact in release")
            found[path] = item["sha256"]
    if set(found) != allowed_paths:
        raise ValueError("selected validation artifacts missing from release")
    return found


def read_validation_l_shard(corpus: Path, relative: str):
    if not relative.startswith("shards/L/") or not relative.endswith(".json.gz"):
        raise ValueError("preparation may read only selected L shards")
    return dataset.read(Path(corpus) / relative)


def validate_action_alignment(native_order, action_rows, values):
    if (not native_order or len(set(native_order)) != len(native_order)
            or len(native_order) != len(values) or len(action_rows) != len(native_order)
            or [row.get("fingerprint") for row in action_rows] != list(native_order)):
        raise ValueError("native-order action/value alignment mismatch")


def selected_validation(selection, quarantine):
    """Return only the predeclared VALIDATION-J roots; never uses other splits."""
    rows = [entry for entry in selection["entries"]
            if entry.get("split") == "VALIDATION" and entry.get("judge_selected") is True
            and entry["root"]["root_id"] not in quarantine]
    if len(rows) != 64 or len({e["root"]["root_id"] for e in rows}) != 64:
        raise ValueError("expected exactly 64 eligible preselected VALIDATION-J roots")
    if len({e["root"]["source_seed"] for e in rows}) != 64:
        raise ValueError("validation roots must have 64 unique source seeds")
    return rows


def validate_checkpoint(path: Path):
    if sha256(path) != CHECKPOINT_SHA:
        raise ValueError("frozen checkpoint SHA-256 mismatch")
    cp = torch.load(path, map_location="cpu", weights_only=True)
    validate_checkpoint_metadata(cp)
    return cp


def validate_checkpoint_metadata(cp):
    cfg = cp.get("config", {})
    if (cp.get("arm") != "T2" or cfg.get("seed") != 20260922 or cp.get("tau") != TAU
            or cfg.get("architecture") != "SilverPriorNetV1"
            or cfg.get("temperatures", {}).get("T2") != TAU
            or any(cfg.get(f"{key}_sha256") != value for key, value in CORPUS_SHA.items())
            or set(cp) != {"state_dict", "config", "normalization", "arm", "tau", "epoch"}):
        raise ValueError("frozen checkpoint metadata mismatch")


def root_replay_seed(root_id, replicate):
    identity = f"{EXPERIMENT_ID}/{root_id}/{replicate}".encode()
    value = 1469598103934665603
    for byte in identity:
        value = ((value ^ byte) * 1099511628211) & ((1 << 64) - 1)
    return value or 1


def validation_j_path(corpus: Path, entry):
    if entry.get("split") != "VALIDATION" or entry.get("judge_selected") is not True:
        raise ValueError("analyzer may open only preselected VALIDATION J records")
    return Path(corpus) / "raw" / "J" / f"{dataset.identity_hash(entry['root'])}.json.gz"


def prepare(corpus: Path, checkpoint: Path, out_dir: Path):
    corpus, release, binding, selection, vocab, plan = sealed_manifests(corpus)
    cp = validate_checkpoint(checkpoint)
    quarantine = set(release.get("quarantined_roots", []))
    entries = selected_validation(selection, quarantine)
    selected_l_paths = [f"shards/L/{dataset.identity_hash(entry['root'])}.json.gz" for entry in entries]
    checksums = selected_hashes(release, selected_l_paths)
    root_rows, model_rows = [], []
    prepared = []
    for entry in entries:
        capture = entry["root"]
        relative = f"shards/L/{dataset.identity_hash(capture)}.json.gz"
        expected_hash = checksums.get(relative)
        if expected_hash is None or dataset.file_hash(corpus / relative) != expected_hash:
            raise ValueError("selected validation L shard is absent or has a hash mismatch")
        stored = read_validation_l_shard(corpus, relative)
        dataset.check_seal(stored)
        job = dataset.job_for(entry, plan, binding["executable_git_sha"], role="L")
        if stored != dataset.shard(stored["replay"], job, vocab):
            raise ValueError("selected L shard projection or labels do not match frozen job")
        root = stored["replay"]["job"]["root"]
        if root["root_id"] != capture["root_id"] or root["state_hash"] != capture["state_hash"]:
            raise ValueError("capture/L root mismatch")
        native = list(root["native_order"])
        actions = stored["replay"]["actions"]
        validate_action_alignment(native, actions, stored["values"])
        root_rows.append(root)
        model_rows.append((stored["observation"], stored["values"], capture["source_seed"], capture["root_id"]))
        prepared.append((root, stored, relative, expected_hash))

    model = trainer.SilverPriorNetV1(len(trainer._numeric_fields(model_rows[0][0])))
    model.load_state_dict(cp["state_dict"])
    model.normalization = cp["normalization"]
    full = trainer.collate_rows(model_rows)
    predictions = trainer.predict_prepared(model, full, "cpu")
    prior_rows = []
    for (root, stored, shard_path, shard_sha), prediction in zip(prepared, predictions, strict=True):
        native = list(root["native_order"])
        logits = prediction["logits"]
        values = stored["values"]
        if len(logits) != len(native) or len(values) != len(native):
            raise ValueError("model/L/native action length mismatch")
        learned = softmax(logits)
        oracle = softmax(values, TAU)
        uniform = [1.0 / len(native)] * len(native)
        l_teacher_seeds = sorted({rep["rng_identity"] for action in stored["replay"]["actions"]
                                  for rep in action["replicates"]})
        prior_rows.append({"root_id": root["root_id"], "source_seed": root["source_seed"],
            "state_hash": root["state_hash"], "native_order": native,
            "checkpoint_sha256": CHECKPOINT_SHA, "learned_logits": logits,
            "learned_prior": learned, "oracle_l_prior": oracle, "uniform_prior": uniform,
            "L_values": values, "L_values_sha256": hashlib.sha256(
                json.dumps(values, separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
            "L_teacher_rng_identities": l_teacher_seeds,
            "L_shard_sha256": shard_sha, "L_shard_path": shard_path})

    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"refusing existing preparation directory: {out_dir}")
    out_dir.mkdir(parents=True)
    roots_path, priors_path = out_dir / "roots.jsonl", out_dir / "priors.jsonl"
    write_jsonl(roots_path, root_rows)
    write_jsonl(priors_path, prior_rows)
    seal = {"schema": "silver_prior_root_screen_preparation_v1", "status": "SEALED",
        "checkpoint_sha256": CHECKPOINT_SHA, "release_sha256": CORPUS_SHA["release"],
        "binding_sha256": CORPUS_SHA["binding"], "selection_sha256": CORPUS_SHA["selection"],
        "vocabulary_sha256": CORPUS_SHA["vocabulary"], "roots": len(root_rows),
        "source_seeds": len({r["source_seed"] for r in root_rows}),
        "roots_sha256": sha256(roots_path), "priors_sha256": sha256(priors_path),
        "raw_J_opened": False, "experiment_id": EXPERIMENT_ID}
    (out_dir / "preparation-seal.json").write_text(json.dumps(seal, indent=2, sort_keys=True) + "\n")
    return seal


def run_replay(executable: Path, prep_dir: Path, out_path: Path):
    executable, prep_dir, out_path = Path(executable), Path(prep_dir), Path(out_path)
    seal_path = prep_dir / "preparation-seal.json"
    seal = json.loads(seal_path.read_text())
    if (seal.get("status") != "SEALED" or sha256(prep_dir / "roots.jsonl") != seal["roots_sha256"]
            or sha256(prep_dir / "priors.jsonl") != seal["priors_sha256"]):
        raise ValueError("preparation seal/hash mismatch")
    if out_path.exists():
        raise FileExistsError(f"refusing existing replay output: {out_path}")
    subprocess.run([str(executable), str(prep_dir / "roots.jsonl"), str(prep_dir / "priors.jsonl"),
                    str(out_path), sha256(executable)], check=True)
    rows = sum(1 for line in out_path.open() if line.strip())
    if rows != 1024:
        raise ValueError(f"expected 1024 completed replay rows, got {rows}")
    replay_seal = {"schema": "silver_prior_root_screen_replay_v1", "status": "SEALED",
        "rows": rows, "replay_sha256": sha256(out_path), "executable_sha256": sha256(executable),
        "roots_sha256": seal["roots_sha256"], "priors_sha256": seal["priors_sha256"],
        "experiment_id": EXPERIMENT_ID}
    Path(str(out_path) + ".seal.json").write_text(json.dumps(replay_seal, indent=2, sort_keys=True) + "\n")
    return replay_seal


def bootstrap_paired(differences, seed):
    values = np.asarray(differences, dtype=np.float64)
    if values.shape != (64,) or not np.isfinite(values).all():
        raise ValueError("paired bootstrap requires 64 finite source-seed units")
    rng = np.random.default_rng(seed)
    samples = rng.integers(0, len(values), size=(BOOTSTRAPS, len(values)))
    means = values[samples].mean(axis=1)
    return {"mean": float(values.mean()), "ci95": [float(x) for x in np.quantile(means, [0.025, 0.975])],
            "bootstrap_replicates": BOOTSTRAPS, "unit": "source_seed", "seed": seed}


def classify(m_u, m_a, o_u):
    m_u_pass, m_a_pass, o_u_pass = m_u["ci95"][1] < 0, m_a["ci95"][1] < 0, o_u["ci95"][1] < 0
    if m_u_pass and m_a_pass:
        return "LEARNED_PRIOR_ROOT_REPLAY_CONFIRMED"
    if m_u_pass and not m_a_pass:
        return "LEARNED_PRIOR_PUCT_SIGNAL_ONLY"
    if not m_u_pass and o_u_pass:
        return "LEARNED_PRIOR_SEARCH_HEADROOM_NOT_CAPTURED"
    return "ROOT_PUCT_HEADROOM_NOT_CONFIRMED"


def judge(corpus: Path, prepared_dir: Path, replay_path: Path, out_path: Path):
    replay_path, out_path = Path(replay_path), Path(out_path)
    prepared_dir = Path(prepared_dir)
    seal_path = Path(str(replay_path) + ".seal.json")
    seal = json.loads(seal_path.read_text())
    if seal.get("status") != "SEALED" or seal.get("rows") != 1024 or sha256(replay_path) != seal.get("replay_sha256"):
        raise ValueError("replay JSONL must be complete and sealed before J is opened")
    prepared_seal = json.loads((prepared_dir / "preparation-seal.json").read_text())
    roots_path, priors_path = prepared_dir / "roots.jsonl", prepared_dir / "priors.jsonl"
    if (prepared_seal.get("status") != "SEALED"
            or sha256(roots_path) != prepared_seal.get("roots_sha256")
            or sha256(priors_path) != prepared_seal.get("priors_sha256")
            or seal.get("roots_sha256") != prepared_seal.get("roots_sha256")
            or seal.get("priors_sha256") != prepared_seal.get("priors_sha256")):
        raise ValueError("prepared roots/priors do not match the replay seal")
    prepared_roots = [json.loads(line) for line in roots_path.read_text().splitlines() if line.strip()]
    prepared_priors = [json.loads(line) for line in priors_path.read_text().splitlines() if line.strip()]
    root_by_id = {row["root_id"]: row for row in prepared_roots}
    prior_by_id = {row["root_id"]: row for row in prepared_priors}
    if len(root_by_id) != 64 or len(prior_by_id) != 64:
        raise ValueError("prepared input root count or identity is invalid")
    replay = [json.loads(line) for line in replay_path.read_text().splitlines() if line.strip()]
    if len(replay) != 1024:
        raise ValueError("replay row count mismatch")
    corpus, release, binding, selection, vocab, plan = sealed_manifests(corpus)
    entries = selected_validation(selection, set(release.get("quarantined_roots", [])))
    by_id = {entry["root"]["root_id"]: entry for entry in entries}
    if set(root_by_id) != set(by_id) or set(prior_by_id) != set(by_id):
        raise ValueError("prepared inputs do not match the selected validation roots")
    selected_j_paths = [f"raw/J/{dataset.identity_hash(entry['root'])}.json.gz" for entry in entries]
    checksums = selected_hashes(release, selected_j_paths)
    grouped = {}
    for row in replay:
        if row.get("schema") != "silver_prior_root_replay_v1" or row.get("arm") not in ARMS or row.get("simulations") != 32:
            raise ValueError("invalid replay row")
        rid, arm, rep = row["root_id"], row["arm"], row["replicate"]
        if rid not in by_id or rep not in range(4):
            raise ValueError("replay references a non-validation root or bad replicate")
        root = by_id[rid]["root"]
        if row["source_seed"] != root["source_seed"] or row["state_hash"] != root["state_hash"]:
            raise ValueError("replay source/state identity mismatch")
        if (root_by_id[rid]["state_hash"] != root["state_hash"]
                or root_by_id[rid]["native_order"] != root["native_order"]
                or prior_by_id[rid]["native_order"] != root["native_order"]):
            raise ValueError("prepared root/prior surface mismatch")
        prior_key = {
            "U_UNIFORM": "uniform_prior", "M_LEARNED": "learned_prior",
            "O_ORACLE_L": "oracle_l_prior"}.get(arm)
        expected_prior = [] if arm == "A_UCT" else prior_by_id[rid][prior_key]
        if (row.get("prior") != expected_prior
                or row.get("executable_sha256") != seal.get("executable_sha256")
                or row.get("silver_upstream_sha") != "84ab3ead9d88c01c4be09a6773fb9a947f57d5ff"):
            raise ValueError("replay prior or executable provenance mismatch")
        key = (rid, arm, rep)
        if key in grouped: raise ValueError("duplicate replay row")
        if row["search_seed"] != root_replay_seed(rid, rep):
            raise ValueError("replay seed does not match frozen experiment identity")
        grouped[key] = row
    if len(grouped) != 1024 or set((r, a, n) for r in by_id for a in ARMS for n in range(4)) != set(grouped):
        raise ValueError("incomplete root/arm/replicate replay grid")
    for rid in by_id:
        for rep in range(4):
            if len({grouped[(rid, arm, rep)]["search_seed"] for arm in ARMS}) != 1:
                raise ValueError("paired replay arms do not share search seed")

    # This loop constructs paths only from the 64 preselected VALIDATION roots.
    j_values, j_rng_identities, j_manifest = {}, {}, []
    for rid, entry in by_id.items():
        root = entry["root"]
        path = validation_j_path(corpus, entry)
        relative = path.relative_to(corpus).as_posix()
        expected = checksums.get(relative)
        if expected is None or dataset.file_hash(path) != expected:
            raise ValueError("selected VALIDATION J shard absent or hash mismatch")
        raw = dataset.read(path)
        job = dataset.job_for(entry, plan, binding["executable_git_sha"], role="J")
        values = dataset.validate_raw(raw, job)
        if len(values) != len(root["native_order"]):
            raise ValueError("J action surface mismatch")
        fingerprints = [action["fingerprint"] for action in raw["actions"]]
        if fingerprints != root["native_order"]:
            raise ValueError("J native-order surface mismatch")
        j_values[rid] = dict(zip(fingerprints, values, strict=True))
        j_rng_identities[rid] = {rep["rng_identity"] for action in raw["actions"]
                                 for rep in action["replicates"]}
        j_manifest.append({"root_id": rid, "source_seed": root["source_seed"],
                           "path": relative, "sha256": expected})

    for rid in by_id:
        for rep in range(4):
            seed = grouped[(rid, ARMS[0], rep)]["search_seed"]
            if seed in j_rng_identities[rid]:
                raise ValueError("replay RNG collides with J teacher identity")

    per_root = {arm: [] for arm in ARMS}
    root_ids = sorted(by_id)
    for rid in root_ids:
        j = j_values[rid]
        best = max(j.values())
        for arm in ARMS:
            regrets, best_hits, times = [], [], []
            for rep in range(4):
                row = grouped[(rid, arm, rep)]
                selected = row["selected_action_fingerprint"]
                if selected not in j: raise ValueError("replay selected an unknown action")
                regrets.append(best - j[selected]); best_hits.append(j[selected] == best)
                times.append(row["search_wall_micros"])
            per_root[arm].append({"root_id": rid, "source_seed": by_id[rid]["root"]["source_seed"],
                "mean_j_regret": float(np.mean(regrets)), "j_best_rate": float(np.mean(best_hits)),
                "mean_search_wall_micros": float(np.mean(times))})

    rng_seeds = {"M_LEARNED_minus_U_UNIFORM": 20260922,
                 "M_LEARNED_minus_A_UCT": 20260923,
                 "O_ORACLE_L_minus_U_UNIFORM": 20260924}
    contrasts = {}
    for name, left, right in (("M_LEARNED_minus_U_UNIFORM", "M_LEARNED", "U_UNIFORM"),
                              ("M_LEARNED_minus_A_UCT", "M_LEARNED", "A_UCT"),
                              ("O_ORACLE_L_minus_U_UNIFORM", "O_ORACLE_L", "U_UNIFORM")):
        d = [a["mean_j_regret"] - b["mean_j_regret"]
             for a, b in zip(per_root[left], per_root[right], strict=True)]
        contrasts[name] = bootstrap_paired(d, rng_seeds[name])
        contrasts[name]["improved_roots"] = sum(x < 0 for x in d)
        contrasts[name]["worsened_roots"] = sum(x > 0 for x in d)
        contrasts[name]["tied_roots"] = sum(x == 0 for x in d)
    arm_summary = {}
    for arm in ARMS:
        vals = per_root[arm]
        regrets = [r["mean_j_regret"] for r in vals]
        arm_summary[arm] = {"mean_j_regret": float(np.mean(regrets)),
            "median_j_regret": float(np.median(regrets)),
            "j_best_selection_probability": float(np.mean([r["j_best_rate"] for r in vals])),
            "mean_search_wall_micros": float(np.mean([r["mean_search_wall_micros"] for r in vals]))}
    result = {"schema": "silver_prior_root_screen_analysis_v1", "source_unit_count": 64,
        "bootstrap_replicates": BOOTSTRAPS, "arms": arm_summary, "contrasts": contrasts,
        "classification": classify(contrasts["M_LEARNED_minus_U_UNIFORM"],
            contrasts["M_LEARNED_minus_A_UCT"], contrasts["O_ORACLE_L_minus_U_UNIFORM"]),
        "per_root": {arm: rows for arm, rows in per_root.items()},
        "provenance": {"replay_sha256": sha256(replay_path), "validation_j_roots": len(j_values),
            "validation_j_files": j_manifest, "locked_test_paths_accessed": False}}
    if out_path.exists(): raise FileExistsError(f"refusing existing analysis: {out_path}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare"); p.add_argument("--corpus", type=Path, required=True); p.add_argument("--checkpoint", type=Path, required=True); p.add_argument("--output-dir", type=Path, required=True)
    r = sub.add_parser("replay"); r.add_argument("--executable", type=Path, required=True); r.add_argument("--prepared-dir", type=Path, required=True); r.add_argument("--output", type=Path, required=True)
    j = sub.add_parser("judge"); j.add_argument("--corpus", type=Path, required=True); j.add_argument("--prepared-dir", type=Path, required=True); j.add_argument("--replay", type=Path, required=True); j.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare": result = prepare(args.corpus, args.checkpoint, args.output_dir)
    elif args.command == "replay": result = run_replay(args.executable, args.prepared_dir, args.output)
    else: result = judge(args.corpus, args.prepared_dir, args.replay, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
