#!/usr/bin/env python3
"""One-time, fail-closed LOCKED_TEST evaluation for the frozen T2 candidate."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
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

CHECKPOINT_SHA256 = "b756c3e6576bdb53085f24aeb1102e4e2fe55fd7469c55546c99f068ccf40e24"
ARM = "T2"
SEED = 20260922
TAU = 1.179975000005129
HASHES = {
    "release": "b32d8d79b44ee799af05892e79e45fb146f4859df58364722d7cd92531bd8419",
    "binding": "7febae9df90e427ad5db631a2004ff4c4cdd579346d22d25b3e1f4532af96e17",
    "selection": "ed91b3bb4c6983be3701333320f1e6c12f7332e3e371ac24b857a76a47d3b5ed",
    "vocabulary": "7e07db8b10618d7c1e9b9b1b31d8196950c03060c54fd4d25fd057ac7918cd46",
}
BOOTSTRAPS = 5000
LOCKED_TEST_CONSUMED = True
CONSUMED_EVIDENCE = "docs/experiments/evidence/silver_prior_locked_test_v1_20260922/README.md"
VALIDATION_DIR = ROOT / "docs/experiments/evidence/silver_prior_model_v1_20260922/stage-a-reviewed-863d7d5e"
VALIDATION_HASHES = {
    "L": "b559dabec4d3e9fd5ceff1b702c3ca82c97d40a112d8b5a324717b919647153c",
    "J": "1352b9b1acc1e34f146e5d8079f1e738ecbaa01337ab453267b4b5cda5e3c327",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def validate_checkpoint(path: Path):
    if sha256(path) != CHECKPOINT_SHA256:
        raise ValueError("frozen checkpoint SHA-256 mismatch")
    cp = torch.load(path, map_location="cpu", weights_only=True)
    cfg = cp.get("config", {})
    if (cp.get("arm") != ARM or cfg.get("seed") != SEED or
            cp.get("tau") != TAU or cfg.get("architecture") != "SilverPriorNetV1" or
            cfg.get("temperatures", {}).get(ARM) != TAU or
            any(cfg.get(f"{name}_sha256") != value for name, value in HASHES.items())):
        raise ValueError("frozen checkpoint metadata mismatch")
    if set(cp) != {"state_dict", "config", "normalization", "arm", "tau", "epoch"}:
        raise ValueError("unexpected checkpoint structure")
    return cp


def _load_sealed_manifests(corpus: Path):
    release, binding, selection, vocab, plan = [dataset.read(corpus / n) for n in
        ("release.json", "binding.json", "selection.json", "vocabulary.json", "plan.json")]
    for item in (release, binding, selection, plan):
        dataset.check_seal(item)
    projection.validate_vocabulary(vocab)
    actual = {"release": release["sha256"], "binding": binding["sha256"],
              "selection": selection["sha256"], "vocabulary": vocab["sha256"]}
    if actual != HASHES:
        raise ValueError("frozen dataset provenance mismatch")
    if (not release.get("training_ready") or release.get("binding_sha256") != binding["sha256"] or
            release.get("selection_sha256") != selection["sha256"] or
            binding.get("plan_sha256") != plan.get("sha256") or
            selection.get("plan_sha256") != plan.get("sha256") or
            plan.get("vocabulary_sha256") != vocab.get("sha256") or
            binding.get("executable_git_sha") != selection.get("executable_git_sha") or
            selection.get("pilot")):
        raise ValueError("release, binding, selection, or vocabulary linkage mismatch")
    quarantine = set(release.get("quarantined_roots", []))
    resolution_hash = release.get("quarantine_resolution_sha256")
    if bool(quarantine) != bool(resolution_hash):
        raise ValueError("release quarantine resolution mismatch")
    if resolution_hash:
        resolution = dataset.read(corpus / "resolutions" / f"{resolution_hash}.json")
        dataset.check_seal(resolution)
        if (resolution.get("schema") != "silver_prior_quarantine_v1" or
                resolution.get("sha256") != resolution_hash or
                resolution.get("binding_sha256") != binding["sha256"] or
                resolution.get("selection_sha256") != selection["sha256"] or
                set(resolution.get("quarantined_roots", [])) != quarantine):
            raise ValueError("sealed quarantine resolution mismatch")
    checksums = {entry["path"]: entry["sha256"] for entry in release["files"]}
    if len(checksums) != len(release["files"]):
        raise ValueError("duplicate release file entry")
    if not quarantine <= {e["root"]["root_id"] for e in selection["entries"]}:
        raise ValueError("quarantine references an unknown selection root")
    l_entries = [e for e in selection["entries"] if e.get("split") == "LOCKED_TEST"
                 and e["root"]["root_id"] not in quarantine]
    j_entries = [e for e in l_entries if e.get("judge_selected") is True]
    if not l_entries or not j_entries or len({e["root"]["root_id"] for e in l_entries}) != len(l_entries):
        raise ValueError("empty or duplicate LOCKED_TEST selection")
    return release, binding, selection, vocab, plan, checksums, quarantine, l_entries, j_entries


def load_validation_diagnostics():
    """Read the committed validation summaries used only for descriptive comparison."""
    paths = {
        "L": VALIDATION_DIR / "validation-l-metrics.json.gz",
        "J": VALIDATION_DIR / "validation-j-metrics.json.gz",
    }
    summaries = {}
    for name, path in paths.items():
        if sha256(path) != VALIDATION_HASHES[name]:
            raise ValueError(f"committed VALIDATION-{name} summary hash mismatch")
        with gzip.open(path, "rt", encoding="utf-8") as f:
            summary = json.load(f)[ARM]
        if summary.get("tau") != TAU:
            raise ValueError(f"committed VALIDATION-{name} summary temperature mismatch")
        metric = (summary.get("metrics", {}).get("expected_regret_minus_uniform") if name == "L"
                  else summary.get("metrics", {}).get("model_minus_uniform"))
        if not metric or metric.get("cluster") != "source_seed" or metric.get("bootstrap_replicates") != BOOTSTRAPS:
            raise ValueError(f"committed VALIDATION-{name} contrast schema mismatch")
        summaries[name] = metric
    return summaries


def _action_signature(observation):
    candidates = observation.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("missing projected candidate list")
    return [json.dumps(c, sort_keys=True, separators=(",", ":")) for c in candidates]


def _load_l(corpus, entries, checksums, plan, binding, vocab):
    rows = []
    for entry in entries:
        if entry.get("split") != "LOCKED_TEST":
            raise ValueError("LOCKED_TEST L loader received a non-LOCKED_TEST entry")
        root = entry["root"]
        rel = f"shards/L/{dataset.identity_hash(root)}.json.gz"
        if rel not in checksums or checksums[rel] != dataset.file_hash(corpus / rel):
            raise ValueError(f"LOCKED_TEST L release membership/checksum failure: {rel}")
        stored = dataset.read(corpus / rel)
        dataset.check_seal(stored)
        job = dataset.job_for(entry, plan, binding["executable_git_sha"])
        projected = dataset.shard(stored["replay"], job, vocab)
        if stored != projected:
            raise ValueError("LOCKED_TEST L projection/label/hash mismatch")
        values = projected["values"]
        if len(values) != len(projected["observation"].get("candidates", [])) or not values:
            raise ValueError("LOCKED_TEST L candidate/value alignment mismatch")
        rows.append((projected["observation"], values, root["source_seed"], root["root_id"]))
    return rows


def _load_j(corpus, entries, checksums, plan, binding, vocab, l_by_root):
    rows = []
    for entry in entries:
        if entry.get("split") != "LOCKED_TEST" or entry.get("judge_selected") is not True:
            raise ValueError("LOCKED_TEST J loader received an unselected or non-LOCKED_TEST entry")
        root = entry["root"]
        rel = f"raw/J/{dataset.identity_hash(root)}.json.gz"
        if rel not in checksums or checksums[rel] != dataset.file_hash(corpus / rel):
            raise ValueError(f"LOCKED_TEST J release membership/checksum failure: {rel}")
        raw = dataset.read(corpus / rel)
        job = dataset.job_for(entry, plan, binding["executable_git_sha"], role="J")
        dataset.validate_raw(raw, job)
        projected = dataset.shard(raw, job, vocab)
        if (len(projected["values"]) != len(projected["observation"].get("candidates", [])) or
                not projected["values"]):
            raise ValueError("LOCKED_TEST J candidate/value alignment mismatch")
        lrow = l_by_root.get(root["root_id"])
        if lrow is None or _action_signature(projected["observation"]) != _action_signature(lrow[0]):
            raise ValueError("LOCKED_TEST L/J root/action alignment mismatch")
        rows.append((projected["observation"], projected["values"], root["source_seed"], root["root_id"]))
    return rows


def _probabilities(logits):
    z = np.asarray(logits, dtype=np.float64)
    p = np.exp(z - z.max())
    return p / p.sum()


def evaluate_rows(model, rows, device="cpu"):
    prepared = trainer.collate_rows(rows)
    predictions = trainer.predict_prepared(model, prepared, device)
    l_per = []
    for pred in predictions:
        metric = trainer.root_metrics(pred["logits"], pred["q"], TAU)
        l_per.append({"root_id": pred["root_id"], "source_seed": pred["source_seed"], **metric})
    return predictions, l_per


def _summary(values, seeds):
    return trainer.bootstrap_summary(values, seeds, n_boot=BOOTSTRAPS, seed=SEED)


def summarize(l_per, j_predictions, j_rows, l_by_root):
    l_names = ("expected_regret", "uniform_regret", "argmax_regret", "top_agreement",
               "concordance", "entropy", "top_probability")
    l_summary = {name: _summary([r[name] if r[name] is not None else np.nan for r in l_per],
                                [r["source_seed"] for r in l_per]) for name in l_names}
    l_delta = [r["expected_regret"] - r["uniform_regret"] for r in l_per]
    l_summary["model_minus_uniform"] = _summary(l_delta, [r["source_seed"] for r in l_per])

    j_per = []
    for pred, row in zip(j_predictions, j_rows):
        qj = np.asarray(row[1], dtype=np.float64)
        pl = np.exp((np.asarray(l_by_root[row[3]][1], dtype=np.float64) - max(l_by_root[row[3]][1])) / TAU)
        pl /= pl.sum()
        p = _probabilities(pred["logits"])
        jbest = float(qj.max())
        j_per.append({
            "root_id": row[3], "source_seed": row[2],
            "model_expected_regret": jbest - float(p @ qj),
            "uniform_expected_regret": jbest - float(qj.mean()),
            "l_target_expected_regret": jbest - float(pl @ qj),
            "model_argmax_regret": jbest - float(qj[int(np.argmax(p))]),
            "l_argmax_regret": jbest - float(qj[int(np.argmax(l_by_root[row[3]][1]))]),
            "pairwise_concordance": trainer.pairwise_concordance(pred["logits"], qj),
        })
    j_names = ("model_expected_regret", "uniform_expected_regret", "l_target_expected_regret",
               "model_argmax_regret", "l_argmax_regret", "pairwise_concordance")
    j_summary = {name: _summary([r[name] if r[name] is not None else np.nan for r in j_per],
                                [r["source_seed"] for r in j_per]) for name in j_names}
    j_delta = [r["model_expected_regret"] - r["uniform_expected_regret"] for r in j_per]
    teacher_delta = [r["l_target_expected_regret"] - r["uniform_expected_regret"] for r in j_per]
    j_summary["model_minus_uniform"] = _summary(j_delta, [r["source_seed"] for r in j_per])
    j_summary["teacher_minus_uniform"] = _summary(teacher_delta, [r["source_seed"] for r in j_per])
    teacher_headroom = float(np.mean([-x for x in teacher_delta]))
    student_gain = float(np.mean([-x for x in j_delta]))
    j_summary["soft_prior_headroom_recovery"] = student_gain / teacher_headroom if teacher_headroom > 0 else None
    decision = ("PRIOR_MODEL_LOCKED_TEST_CONFIRMED"
                if l_summary["model_minus_uniform"]["ci95"][1] < 0 and
                j_summary["model_minus_uniform"]["ci95"][1] < 0
                else "PRIOR_MODEL_LOCKED_TEST_NOT_CONFIRMED")
    return l_summary, {"metrics": j_summary, "per_root": j_per}, decision


def validation_comparison(validation, locked_l, locked_j):
    """Side-by-side descriptive validation/locked contrasts; never a decision gate."""
    return {
        "classification_role": "DESCRIPTIVE_ONLY",
        "validation_l_model_minus_uniform": validation["L"],
        "locked_l_model_minus_uniform": locked_l["model_minus_uniform"],
        "validation_j_model_minus_uniform": validation["J"],
        "locked_j_model_minus_uniform": locked_j["metrics"]["model_minus_uniform"],
        "locked_j_teacher_minus_uniform": locked_j["metrics"]["teacher_minus_uniform"],
        "locked_j_soft_prior_headroom_recovery": locked_j["metrics"]["soft_prior_headroom_recovery"],
    }


def run(checkpoint_path: Path, corpus: Path, output_dir: Path):
    if LOCKED_TEST_CONSUMED:
        raise RuntimeError(f"LOCKED_TEST already consumed; refusing another evaluation. See {CONSUMED_EVIDENCE}")
    cp = validate_checkpoint(checkpoint_path)
    (release, binding, selection, vocab, plan, checksums,
     quarantine, l_entries, j_entries) = _load_sealed_manifests(corpus)
    validation = load_validation_diagnostics()
    if output_dir.exists():
        raise FileExistsError(f"LOCKED_TEST output directory already exists: {output_dir}")
    evaluator_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    receipt = {
        "status": "LOCKED_TEST_OPENED", "evaluator_git_sha": evaluator_sha,
        "evaluator_source_sha256": sha256(Path(__file__)), "checkpoint_sha256": CHECKPOINT_SHA256,
        "release_sha256": HASHES["release"], "binding_sha256": HASHES["binding"],
        "selection_sha256": HASHES["selection"], "vocabulary_sha256": HASHES["vocabulary"],
        "selected_arm": ARM, "seed": SEED,
    }
    output_dir.mkdir(parents=True, exist_ok=False)
    parentfd = os.open(output_dir.parent, os.O_RDONLY)
    try:
        os.fsync(parentfd)
    finally:
        os.close(parentfd)
    with (output_dir / "consumption-receipt.json").open("x") as f:
        json.dump(receipt, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    dirfd = os.open(output_dir, os.O_RDONLY)
    try:
        os.fsync(dirfd)
    finally:
        os.close(dirfd)

    # No LOCKED_TEST data path is opened until the durable create-only receipt exists.
    l_rows = _load_l(corpus, l_entries, checksums, plan, binding, vocab)
    l_by_root = {r[3]: r for r in l_rows}
    j_rows = _load_j(corpus, j_entries, checksums, plan, binding, vocab, l_by_root)
    l_prepared = trainer.collate_rows(l_rows)
    model = trainer.SilverPriorNetV1(l_prepared["contexts"].shape[1])
    model.load_state_dict(cp["state_dict"])
    model.normalization = cp["normalization"]
    l_predictions = trainer.predict_prepared(model, l_prepared, "cpu")
    l_per = [{"root_id": p["root_id"], "source_seed": p["source_seed"],
              **trainer.root_metrics(p["logits"], p["q"], TAU)} for p in l_predictions]
    j_predictions, _ = evaluate_rows(model, j_rows)
    l_summary, j_result, decision = summarize(l_per, j_predictions, j_rows, l_by_root)
    (output_dir / "locked-l-summary.json").write_text(json.dumps({"metrics": l_summary, "per_root": l_per}, indent=2, allow_nan=False) + "\n")
    (output_dir / "locked-j-summary.json").write_text(json.dumps(j_result, indent=2, allow_nan=False) + "\n")
    (output_dir / "decision.json").write_text(json.dumps({
        "classification": decision,
        "rule": "upper 95% source-seed cluster bootstrap CI of model-minus-uniform expected regret is < 0 for both LOCKED_TEST L and J",
        "bootstrap_replicates": BOOTSTRAPS,
        "validation_comparison": validation_comparison(validation, l_summary, j_result),
    }, indent=2) + "\n")
    return {"l_roots": len(l_rows), "l_sources": len({r[2] for r in l_rows}),
            "j_roots": len(j_rows), "j_sources": len({r[2] for r in j_rows}),
            "classification": decision}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if LOCKED_TEST_CONSUMED:
        parser.error(f"LOCKED_TEST already consumed; refusing another evaluation. See {CONSUMED_EVIDENCE}")
    print(json.dumps(run(args.checkpoint, args.corpus, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
