"""#334 A3 offline pipeline: preflight -> tune -> freeze -> open-test.

No command changes a tracked model. Use `python3 -m tools.vwin_refresh_model`.
The real TEST latch is consumed before evaluation; a failed evaluation stays
consumed and requires a separately reviewed recovery, never an automatic retry.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np

from tools.analysis.vwin_tree_utils import load_trees, predict_rows
from tools.vwin_refresh_dataset import validated_dataset, half_train_sources, HALF_TRAIN_RULE

ARMS = ("X1", "X2", "M1")
ROOT = Path(__file__).resolve().parents[1]
B0 = ROOT / "models/v_win_trees.txt"
TOOL_FILES = ("tools/vwin_refresh_model.py", "tools/vwin_refresh_dataset.py",
              "tools/vwin_refresh_training.py", "tools/vwin_refresh_evaluation.py",
              "tools/vwin_refresh_corpus.py", "tools/vwin_refresh_contract.py",
              "tools/analysis/vwin_tree_utils.py", "src/game/GameContext.cpp", "src/game/Map.cpp")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    """Exclusive creation prevents accidental replacement of evidence."""
    with Path(path).open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def tool_identity():
    return {"git_sha": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "files": {p: sha256(ROOT / p) for p in TOOL_FILES}}


class Baseline:
    def __init__(self, path=None):
        path = B0 if path is None else path
        self.path = Path(path)
        self.features, self.trees, self.logistic, _, self.margin = load_trees(path)
        if not self.features or len(set(self.features)) != len(self.features):
            raise ValueError("invalid B0 feature contract")

    def predict(self, X, feature_names):
        names = list(feature_names)
        if len(set(names)) != len(names):
            raise ValueError("duplicate input feature names")
        indices = [names.index(f) for f in self.features]  # missing names fail closed
        return predict_rows(np.asarray(X)[:, indices], self.trees, self.logistic, self.margin)

    def identity(self):
        return {"sha256": sha256(self.path), "feature_count": len(self.features),
                "tree_count": len(self.trees), "features": self.features}


def native_parity(X, feature_names, executable, model=B0, tolerance=1e-4):
    """Optional no-seed winnettest path, using canonical rich-header order.

    Caller supplies the manifest's complete rich feature order, matching
    richIdxMap(). No C++ build or game simulation is launched by default.
    """
    if len(feature_names) != 1017:
        raise ValueError("native parity requires complete canonical rich contract")
    X = np.asarray(X, dtype=np.float32)
    if not 0 < len(X) <= 64:
        raise ValueError("native parity is limited to 1..64 supplied rows")
    with tempfile.TemporaryDirectory() as temp:
        fixture = Path(temp) / "parity.csv"
        with fixture.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["chosen", *feature_names, "won"])
            writer.writerows([1, *row, 0] for row in X)
        result = subprocess.run([str(Path(executable).resolve()), "winnettest",
                                 str(Path(model).resolve()), str(fixture), str(len(X))],
                                check=True, capture_output=True, text=True)
    observed = {}
    for line in result.stdout.splitlines():
        fields = line.split(",")
        if len(fields) == 2 and fields[0].isdigit():
            index = int(fields[0])
            if index in observed:
                raise ValueError("duplicate native parity row")
            observed[index] = float(fields[1])
    if set(observed) != set(range(len(X))):
        raise ValueError("native parity row coverage mismatch")
    native = np.array([observed[i] for i in range(len(X))])
    diff = np.abs(Baseline(model).predict(X, feature_names) - native)
    if not np.all(np.isfinite(diff)) or float(diff.max()) >= tolerance:
        raise ValueError("B0 Python/native parity failed")
    return {"rows": len(X), "max_abs_error": float(diff.max()), "tolerance": tolerance,
            "executable_sha256": sha256(executable), "model_sha256": sha256(model)}


def preflight(index, output):
    if Path(output).exists():
        raise FileExistsError(output)
    baseline = Baseline()
    data = validated_dataset(index)
    report = data.preflight(baseline.features)
    report.update(b0=baseline.identity(), tooling=tool_identity(),
                  real_test_predictions_opened=False, full_candidate_training_run=False)
    write_json(output, report)
    return report


def tune(index, output, *, threads=1, device="cpu"):
    from tools.vwin_refresh_training import (train_xgb, train_xgb_fixed, train_mlp,
                                             _configure_cuda_determinism)
    # XGB version reporting may inspect GPUs before M1 begins.
    _configure_cuda_determinism(device)
    from tools.vwin_refresh_evaluation import evaluate_predictions, sibling_ranking
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    baseline = Baseline()
    data = validated_dataset(index)
    metadata = data.preflight(baseline.features)
    write_json(output / "preflight.json", metadata)
    names = data.feature_names
    selected = metadata["selected_feature_names"]
    if "curHp" not in selected:
        raise ValueError("X2 requires curHp in TRAIN-selected features")
    columns = [names.index(f) for f in selected]
    xt, yt, mt = data.read("TRAIN")
    xv, yv, mv = data.read("VALIDATION")
    train_selected, val_selected = xt[:, columns], xv[:, columns]
    del xt
    branches = data.branches("VALIDATION")
    reports = {}
    bpred = baseline.predict(xv, names)
    reports["B0"] = {"validation": evaluate_predictions(yv, bpred, mv),
                     "siblings": sibling_ranking(mv, bpred, branches)}
    for arm in ("X1", "X2"):
        model, report = train_xgb(train_selected, yt, val_selected, yv, selected,
                                  monotone=arm == "X2", threads=threads)
        model.save(output / arm)
        prediction = model.predict(val_selected)
        reports[arm] = {"training": report,
                       "validation": evaluate_predictions(yv, prediction, mv),
                       "siblings": sibling_ranking(mv, prediction, branches)}
        if arm == "X1":
            chosen_seeds = half_train_sources([int(m["sourceSeed"]) for m in mt])
            chosen_set = set(chosen_seeds)
            half = np.array([int(m["sourceSeed"]) in chosen_set for m in mt])
            half_model, half_report = train_xgb_fixed(
                train_selected[half], yt[half], val_selected, yv, selected,
                params=report["selected"]["params"])
            half_prediction = half_model.predict(val_selected)
            half_metrics = evaluate_predictions(yv, half_prediction, mv)
            delta = half_metrics["overall"]["nll"] - reports[arm]["validation"]["overall"]["nll"]
            reports[arm]["learning_curve"] = {
                "half_source_seeds": list(chosen_seeds),
                "selection_rule": HALF_TRAIN_RULE,
                "training": half_report, "validation": half_metrics,
                "half_minus_full_nll": delta,
                "classification": "DATA_SCALE_SIGNAL" if delta >= .002 else "NO_CLEAR_DATA_SCALE_SIGNAL"}
            del half_model
        del model
    model, report = train_mlp(train_selected, yt, val_selected, yv, selected,
                              threads=threads, device=device)
    model.save(output / "M1")
    pred = model.predict(val_selected)
    reports["M1"] = {"training": report, "validation": evaluate_predictions(yv, pred, mv),
                     "siblings": sibling_ranking(mv, pred, branches)}
    shutil.copyfile(B0, output / "B0.txt")
    write_json(output / "validation.json", reports)
    write_json(output / "tuning.json", {
        "schema": "vwin_refresh_a3_tuning_v1", "tooling": tool_identity(),
        "corpus_index": str(Path(index).resolve()), "corpus_sha256": sha256(index),
        "b0": baseline.identity(), "selected_features": selected,
        "selection_split": "VALIDATION", "test_predictions_opened": False,
        "complete_arms": list(ARMS)})
    return reports


def artifact_hashes(run):
    run = Path(run)
    files = [run / name for name in ("preflight.json", "validation.json", "tuning.json", "B0.txt")]
    for arm in ARMS:
        directory = run / arm
        if not directory.is_dir():
            raise ValueError(f"missing selected checkpoint: {arm}")
        arm_files = sorted(p for p in directory.rglob("*") if p.is_file())
        if not arm_files:
            raise ValueError(f"empty selected checkpoint: {arm}")
        files.extend(arm_files)
    return {str(p.relative_to(run)): sha256(p) for p in files}


def freeze(run):
    run = Path(run)
    tuning = json.loads((run / "tuning.json").read_text())
    if (tuning["complete_arms"] != list(ARMS) or tuning["selection_split"] != "VALIDATION"
            or tuning["test_predictions_opened"] is not False):
        raise ValueError("only completed validation-selected arms may be frozen")
    if tuning["tooling"]["files"] != tool_identity()["files"]:
        raise ValueError("tooling changed since tuning")
    if (run / "test-opened.json").exists():
        raise ValueError("TEST already opened")
    from tools.vwin_refresh_training import load_predictor
    selected = tuning["selected_features"]
    preflight_record = json.loads((run / "preflight.json").read_text())
    if selected != preflight_record["selected_feature_names"]:
        raise ValueError("selected feature contract changed")
    for arm in ARMS:
        model = load_predictor(run / arm)
        if list(model.feature_names) != selected:
            raise ValueError(f"{arm} feature contract disagrees with TRAIN mask")
    if sha256(run / "B0.txt") != tuning["b0"]["sha256"]:
        raise ValueError("B0 checkpoint changed since tuning")
    record = {"schema": "vwin_refresh_a3_freeze_v1", "artifacts": artifact_hashes(run),
              "tooling": tool_identity(), "corpus_sha256": tuning["corpus_sha256"],
              "test_policy": "one exclusive opening, all four frozen arms, no retuning"}
    write_json(run / "freeze.json", record)
    return record


def verify_freeze(run):
    run = Path(run)
    record = json.loads((run / "freeze.json").read_text())
    if record.get("schema") != "vwin_refresh_a3_freeze_v1":
        raise ValueError("invalid freeze schema")
    if record["artifacts"] != artifact_hashes(run):
        raise ValueError("frozen artifacts changed")
    if record["tooling"]["files"] != tool_identity()["files"]:
        raise ValueError("frozen tooling changed")
    if (run / "test-opened.json").exists():
        raise ValueError("TEST was already opened; automatic reopen is prohibited")
    return record


def open_test(run, confirmation):
    if confirmation != "OPEN_REAL_TEST_ONCE":
        raise ValueError("explicit OPEN_REAL_TEST_ONCE confirmation required")
    run = Path(run)
    record = verify_freeze(run)  # before corpus or model access
    tuning = json.loads((run / "tuning.json").read_text())
    data = validated_dataset(tuning["corpus_index"], expected_sha=record["corpus_sha256"])
    from tools.vwin_refresh_training import load_predictor
    from tools.vwin_refresh_evaluation import (evaluate_predictions, clustered_delta,
        resource_probes, sibling_ranking, offline_verdict)
    models = {"B0": Baseline(run / "B0.txt"),
              **{arm: load_predictor(run / arm) for arm in ARMS}}
    # An exclusive durable marker is written before the first TEST feature read.
    write_json(run / "test-opened.json", {"freeze_sha256": sha256(run / "freeze.json"),
                                          "status": "consumed_before_test_read"})
    X, y, rows = data.read("TEST", allow_test=True)
    names = data.feature_names
    predictions = {arm: model.predict(X, names) for arm, model in models.items()}
    branches = data.branches("TEST", allow_test=True)
    result = {"freeze_sha256": sha256(run / "freeze.json"), "arms": {}}
    decisions = {}
    seeds = [int(r["sourceSeed"]) for r in rows]
    for arm, model in models.items():
        p = predictions[arm]
        metrics = evaluate_predictions(y, p, rows)
        resources = resource_probes(lambda values, m=model: m.predict(values, names), X, names, rows)
        entry = {"predictive": metrics, "map_resources": resources,
                 "siblings": sibling_ranking(rows, p, branches)}
        if arm != "B0":
            entry["delta_vs_b0"] = clustered_delta(y, predictions["B0"], p, seeds)
            decisions[arm] = {"nll": metrics["overall"]["nll"],
                              "nll_delta_ci95": entry["delta_vs_b0"]["nll"]["ci95"],
                              "map_resource_gate": resources["resource_gate"]}
        result["arms"][arm] = entry
    del X, predictions
    raw, _, raw_rows = data.read("TEST", kind="WIN_RAW", allow_test=True)
    for arm, model in models.items():
        resource = resource_probes(lambda values, m=model: m.predict(values, names),
                                   raw, names, raw_rows, kind="WIN_RAW")
        result["arms"][arm]["win_raw_resources"] = resource
        if arm != "B0":
            decisions[arm]["win_raw_resource_gate"] = resource["resource_gate"]
    result["verdict"] = offline_verdict(decisions)
    result["terminal_pricing_ready"] = False
    write_json(run / "test-results.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("preflight", help="validate contracts and TRAIN variance; no predictions")
    p.add_argument("index"); p.add_argument("--output", required=True)
    p = sub.add_parser("tune", help="full TRAIN/VALIDATION execution, only after review")
    p.add_argument("index"); p.add_argument("--output", required=True)
    p.add_argument("--authorize-full-training", action="store_true", required=True)
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    p = sub.add_parser("freeze"); p.add_argument("run")
    p = sub.add_parser("open-test"); p.add_argument("run")
    p.add_argument("--confirm", required=True, choices=("OPEN_REAL_TEST_ONCE",))
    args = parser.parse_args(argv)
    if args.command == "preflight":
        result = preflight(args.index, args.output)
    elif args.command == "tune":
        result = tune(args.index, args.output, threads=args.threads, device=args.device)
    elif args.command == "freeze":
        result = freeze(args.run)
    else:
        result = open_test(args.run, args.confirm)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
