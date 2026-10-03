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
import time
import resource
import uuid
import sys

import numpy as np

from tools.analysis.vwin_tree_utils import load_trees, predict_rows
from tools.vwin_refresh_dataset import (validated_dataset, half_train_sources, HALF_TRAIN_RULE,
    CorpusBinding, DEFAULT_CORPUS_BINDING, SPLIT_NAMES)

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
            writer = csv.writer(f, lineterminator="\n")
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


def preflight(index, output, *, binding=DEFAULT_CORPUS_BINDING):
    if Path(output).exists():
        raise FileExistsError(output)
    baseline = Baseline()
    data = validated_dataset(index, binding=binding)
    report = data.preflight(baseline.features)
    report.update(b0=baseline.identity(), tooling=tool_identity(),
                  real_test_predictions_opened=False, full_candidate_training_run=False)
    write_json(output, report)
    return report


def resource_evaluation(model, X, names, rows, kind):
    """The exact shared VALIDATION/TEST resource path, including adapters."""
    from tools.vwin_refresh_evaluation import resource_probes
    started = time.perf_counter()
    result = resource_probes(lambda values: model.predict(values, names),
                             X, names, rows, kind=kind)
    return {"result": result, "elapsed_seconds": time.perf_counter() - started,
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}


def checkpoint_hashes(run):
    run = Path(run)
    files = [run / "B0.txt"]
    for arm in ARMS:
        directory = run / arm
        arm_files = sorted(p for p in directory.rglob("*") if p.is_file())
        if not arm_files:
            raise ValueError(f"missing selected checkpoint: {arm}")
        files.extend(arm_files)
    return {str(p.relative_to(run)): sha256(p) for p in files}


def bound_corpus(run, tuning):
    """Validate saved expectations before any qualification or TEST corpus access."""
    binding = CorpusBinding.from_dict(tuning.get("corpus_binding"))
    preflight = json.loads((Path(run) / "preflight.json").read_text())
    if (CorpusBinding.from_dict(preflight.get("corpus_binding")) != binding
            or tuning["corpus_sha256"] != binding.index_sha256
            or preflight["corpus_index_sha256"] != binding.index_sha256
            or preflight["split_counts"] != dict(binding.split_counts)):
        raise ValueError("corpus binding disagrees with tuning/preflight")
    return binding


def qualify_validation(run, *, data=None):
    """Qualify execution, never model quality; negative resource gates are valid.

    The production artifact binds selected checkpoints, the whole VALIDATION
    populations, runtime and source. Failed attempts are retained separately;
    no attempt consumes or reads TEST feature matrices.
    """
    from tools.vwin_refresh_training import load_predictor, runtime_fingerprint
    run = Path(run)
    destination = run / "validation-resources.json"
    if destination.exists():
        raise FileExistsError(destination)
    tuning = json.loads((run / "tuning.json").read_text())
    tooling = tool_identity()
    runtime = runtime_fingerprint(tuning["runtime_device"])
    if tuning["tooling"] != tooling or tuning["runtime"] != runtime:
        raise ValueError("tooling/runtime changed since tuning")
    binding = bound_corpus(run, tuning)
    checkpoints = checkpoint_hashes(run)
    if data is None:
        data = validated_dataset(tuning["corpus_index"], binding=binding)
    if data.binding != binding:
        raise ValueError("qualification dataset corpus binding mismatch")
    models = {"B0": Baseline(run / "B0.txt"),
              **{arm: load_predictor(run / arm) for arm in ARMS}}
    started = time.perf_counter()
    record = {"schema": "vwin_refresh_a3_validation_resources_v1", "status": "running",
              "purpose": tuning["purpose"], "split": "VALIDATION",
              "corpus_sha256": tuning["corpus_sha256"], "corpus_binding": binding.to_dict(), "tooling": tooling,
              "runtime": runtime, "checkpoint_hashes": checkpoints,
              "tuning_sha256": sha256(run / "tuning.json"),
              "populations": {}, "arms": {arm: {} for arm in models},
              "selection_effect": "none; execution qualification only"}
    try:
        for kind in ("MAP", "WIN_RAW"):
            X, _, rows = data.read("VALIDATION", kind=kind)
            record["populations"][kind] = {"rows": len(rows),
                "source_seeds": len({int(r["sourceSeed"]) for r in rows})}
            for arm, model in models.items():
                print(f"VALIDATION {kind} {arm}: {len(rows)} rows", file=sys.stderr, flush=True)
                record["arms"][arm][kind] = resource_evaluation(model, X, data.feature_names, rows, kind)
                print(f"VALIDATION {kind} {arm}: complete in "
                      f"{record['arms'][arm][kind]['elapsed_seconds']:.3f}s", file=sys.stderr, flush=True)
            del X, rows
        if (tooling != tool_identity() or runtime != runtime_fingerprint(tuning["runtime_device"])
                or checkpoints != checkpoint_hashes(run)):
            raise ValueError("qualification inputs changed during execution")
        record["status"] = "complete"
        record["elapsed_seconds"] = time.perf_counter() - started
        write_json(destination, record)
    except Exception as exc:
        record.update(status="failed", error=f"{type(exc).__name__}: {exc}",
                      elapsed_seconds=time.perf_counter() - started)
        write_json(run / f"validation-resources.failed-{uuid.uuid4().hex}.json", record)
        raise
    return record


def verify_validation_qualification(run, tuning):
    from tools.vwin_refresh_training import runtime_fingerprint
    run = Path(run)
    binding = bound_corpus(run, tuning)
    report = json.loads((run / "validation-resources.json").read_text())
    if CorpusBinding.from_dict(report.get("corpus_binding")) != binding:
        raise ValueError("VALIDATION qualification corpus binding mismatch")
    if (report.get("schema") != "vwin_refresh_a3_validation_resources_v1"
            or report.get("status") != "complete" or report.get("split") != "VALIDATION"
            or report.get("purpose") != "selected_candidates"):
        raise ValueError("completed selected-checkpoint VALIDATION resource qualification required")
    if (report["tooling"] != tool_identity() or report["runtime"] != runtime_fingerprint(tuning["runtime_device"])
            or report["corpus_sha256"] != tuning["corpus_sha256"]
            or report["tuning_sha256"] != sha256(run / "tuning.json")
            or report["checkpoint_hashes"] != checkpoint_hashes(run)):
        raise ValueError("VALIDATION qualification identity mismatch")
    if set(report["arms"]) != {"B0", *ARMS} or set(report["populations"]) != {"MAP", "WIN_RAW"}:
        raise ValueError("incomplete VALIDATION resource qualification")
    for kind, population in report["populations"].items():
        if population["rows"] <= 0 or population["source_seeds"] <= 0:
            raise ValueError("empty VALIDATION resource population")
        for arm in ("B0", *ARMS):
            if set(report["arms"][arm]) != {"MAP", "WIN_RAW"}:
                raise ValueError("incomplete VALIDATION resource qualification")
            entry = report["arms"][arm][kind]
            if (entry["result"]["n"] != population["rows"] or entry["result"]["kind"] != kind
                    or not np.isfinite(entry["elapsed_seconds"]) or entry["elapsed_seconds"] < 0):
                raise ValueError("invalid VALIDATION resource result/timing")
    return report


def tune(index, output, *, threads=1, device="cpu", binding=DEFAULT_CORPUS_BINDING):
    from tools.vwin_refresh_training import (train_xgb, train_xgb_fixed, train_mlp,
                                             _configure_cuda_determinism, runtime_fingerprint)
    # XGB version reporting may inspect GPUs before M1 begins.
    _configure_cuda_determinism(device)
    tooling, runtime = tool_identity(), runtime_fingerprint(device)
    from tools.vwin_refresh_evaluation import evaluate_predictions, sibling_ranking
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    baseline = Baseline()
    data = validated_dataset(index, binding=binding)
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
    if tooling != tool_identity() or runtime != runtime_fingerprint(device):
        raise ValueError("tooling/runtime changed during tuning")
    write_json(output / "tuning.json", {
        "schema": "vwin_refresh_a3_tuning_v2", "tooling": tooling,
        "runtime": runtime, "runtime_device": device, "purpose": "selected_candidates",
        "corpus_index": str(Path(index).resolve()), "corpus_sha256": sha256(index),
        "corpus_binding": binding.to_dict(),
        "b0": baseline.identity(), "selected_features": selected,
        "selection_split": "VALIDATION", "test_predictions_opened": False,
        "complete_arms": list(ARMS)})
    del train_selected, val_selected, xv, model
    qualify_validation(output, data=data)
    return reports


def validation_smoke(index, output, *, binding=DEFAULT_CORPUS_BINDING):
    """Bounded adapter checkpoints; full real VALIDATION probes, never freezeable.

    This is not hyperparameter selection or scientific candidate qualification.
    The eventual full tune must qualify its own selected checkpoint hashes.
    """
    from tools.vwin_refresh_training import train_xgb, train_mlp, runtime_fingerprint
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    tooling, runtime = tool_identity(), runtime_fingerprint("cpu")
    plan = {"purpose": "smoke_only", "train_row_limit": 4096,
            "validation_training_row_limit": 1024,
            "row_selection": "first eligible rows in validated component order; no balancing",
            "xgb_grid": [{"max_depth": 4, "eta": .06, "min_child_weight": 10}],
            "xgb_max_rounds": 16, "xgb_patience": 4,
            "mlp_recipes": [{"lr": .001, "weight_decay": .0001, "dropout": 0.}],
            "mlp_max_epochs": 2, "mlp_patience": 1, "mlp_batch_size": 1024,
            "mlp_retrain_seeds": [0, 1, 2], "threads": 1,
            "resource_population": "ALL VALIDATION MAP and WIN_RAW, all four arms, 2000 bootstrap replicates",
            "tooling": tooling, "runtime": runtime}
    write_json(output / "smoke-plan.json", plan)
    print("Validating full corpus; no TEST prediction access", file=sys.stderr, flush=True)
    data = validated_dataset(index, binding=binding)
    baseline = Baseline()
    metadata = data.preflight(baseline.features)
    write_json(output / "preflight.json", metadata)
    selected = metadata["selected_feature_names"]
    columns = [data.feature_names.index(name) for name in selected]
    xt, yt, mt = data.read("TRAIN", row_limit=plan["train_row_limit"])
    xv, yv, mv = data.read("VALIDATION", row_limit=plan["validation_training_row_limit"])
    reports = {"plan": plan, "train_rows": len(yt), "validation_training_rows": len(yv),
               "train_source_seeds": sorted({int(row["sourceSeed"]) for row in mt}),
               "validation_training_source_seeds": sorted({int(row["sourceSeed"]) for row in mv})}
    xt, xv = xt[:, columns], xv[:, columns]
    for arm in ("X1", "X2"):
        started = time.perf_counter()
        model, report = train_xgb(xt, yt, xv, yv, selected, monotone=arm == "X2",
            grid=plan["xgb_grid"], max_rounds=16, patience=4, threads=1)
        model.save(output / arm)
        reports[arm] = {"training": report, "elapsed_seconds": time.perf_counter() - started}
    started = time.perf_counter()
    model, report = train_mlp(xt, yt, xv, yv, selected, recipes=plan["mlp_recipes"],
        max_epochs=2, patience=1, batch_size=1024, threads=1, device="cpu")
    model.save(output / "M1")
    reports["M1"] = {"training": report, "elapsed_seconds": time.perf_counter() - started}
    shutil.copyfile(B0, output / "B0.txt")
    write_json(output / "validation.json", reports)
    if tooling != tool_identity() or runtime != runtime_fingerprint("cpu"):
        raise ValueError("tooling/runtime changed during smoke")
    write_json(output / "tuning.json", {
        "schema": "vwin_refresh_a3_tuning_v2", "purpose": "smoke_only",
        "tooling": tooling, "runtime": runtime, "runtime_device": "cpu",
        "corpus_index": str(Path(index).resolve()), "corpus_sha256": sha256(index),
        "corpus_binding": binding.to_dict(),
        "b0": baseline.identity(), "selected_features": selected,
        "selection_split": "VALIDATION_SMOKE_ONLY", "test_predictions_opened": False,
        "complete_arms": list(ARMS)})
    del xt, xv, model
    return qualify_validation(output, data=data)


def artifact_hashes(run):
    run = Path(run)
    files = ("preflight.json", "validation.json", "tuning.json", "validation-resources.json")
    return {**checkpoint_hashes(run), **{name: sha256(run / name) for name in files}}


def freeze(run):
    run = Path(run)
    tuning = json.loads((run / "tuning.json").read_text())
    if (tuning["complete_arms"] != list(ARMS) or tuning["selection_split"] != "VALIDATION"
            or tuning["test_predictions_opened"] is not False):
        raise ValueError("only completed validation-selected arms may be frozen")
    if tuning["tooling"] != tool_identity():
        raise ValueError("tooling changed since tuning")
    if (run / "test-opened.json").exists():
        raise ValueError("TEST already opened")
    from tools.vwin_refresh_training import load_predictor, runtime_fingerprint
    if tuning["runtime"] != runtime_fingerprint(tuning["runtime_device"]):
        raise ValueError("runtime changed since tuning")
    verify_validation_qualification(run, tuning)
    binding = bound_corpus(run, tuning)
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
    record = {"schema": "vwin_refresh_a3_freeze_v2", "artifacts": artifact_hashes(run),
              "tooling": tool_identity(), "runtime": tuning["runtime"],
              "runtime_device": tuning["runtime_device"], "corpus_sha256": tuning["corpus_sha256"],
              "corpus_binding": binding.to_dict(),
              "test_policy": "one exclusive opening, all four frozen arms, no retuning"}
    write_json(run / "freeze.json", record)
    return record


def verify_freeze(run):
    run = Path(run)
    record = json.loads((run / "freeze.json").read_text())
    if record.get("schema") != "vwin_refresh_a3_freeze_v2":
        raise ValueError("invalid freeze schema")
    if record["artifacts"] != artifact_hashes(run):
        raise ValueError("frozen artifacts changed")
    if record["tooling"] != tool_identity():
        raise ValueError("frozen tooling changed")
    from tools.vwin_refresh_training import runtime_fingerprint
    if record["runtime"] != runtime_fingerprint(record["runtime_device"]):
        raise ValueError("frozen runtime changed")
    tuning = json.loads((run / "tuning.json").read_text())
    binding = bound_corpus(run, tuning)
    if (CorpusBinding.from_dict(record.get("corpus_binding")) != binding
            or record["corpus_sha256"] != binding.index_sha256):
        raise ValueError("frozen corpus binding changed")
    verify_validation_qualification(run, tuning)
    if (run / "test-opened.json").exists():
        raise ValueError("TEST was already opened; automatic reopen is prohibited")
    return record


def open_test(run, confirmation):
    if confirmation != "OPEN_REAL_TEST_ONCE":
        raise ValueError("explicit OPEN_REAL_TEST_ONCE confirmation required")
    run = Path(run)
    record = verify_freeze(run)  # before corpus or model access
    tuning = json.loads((run / "tuning.json").read_text())
    data = validated_dataset(tuning["corpus_index"],
                             binding=CorpusBinding.from_dict(record["corpus_binding"]))
    from tools.vwin_refresh_training import load_predictor
    from tools.vwin_refresh_evaluation import (evaluate_predictions, clustered_delta,
        sibling_ranking, offline_verdict)
    models = {"B0": Baseline(run / "B0.txt"),
              **{arm: load_predictor(run / arm) for arm in ARMS}}
    verify_freeze(run)  # Recheck after corpus validation/model loading, before latch.
    # An exclusive durable marker is written before the first TEST feature read.
    write_json(run / "test-opened.json", {"freeze_sha256": sha256(run / "freeze.json"),
                                          "corpus_binding": record["corpus_binding"],
                                          "status": "consumed_before_test_read"})
    X, y, rows = data.read("TEST", allow_test=True)
    names = data.feature_names
    predictions = {arm: model.predict(X, names) for arm, model in models.items()}
    branches = data.branches("TEST", allow_test=True)
    result = {"freeze_sha256": sha256(run / "freeze.json"), "runtime": record["runtime"],
              "tooling": record["tooling"], "corpus_binding": record["corpus_binding"], "arms": {}}
    decisions = {}
    seeds = [int(r["sourceSeed"]) for r in rows]
    for arm, model in models.items():
        p = predictions[arm]
        metrics = evaluate_predictions(y, p, rows)
        resource_record = resource_evaluation(model, X, names, rows, "MAP")
        resources = resource_record["result"]
        entry = {"predictive": metrics, "map_resources": resources,
                 "map_resource_timing": {k: v for k, v in resource_record.items() if k != "result"},
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
        resource_record = resource_evaluation(model, raw, names, raw_rows, "WIN_RAW")
        resource = resource_record["result"]
        result["arms"][arm]["win_raw_resource_timing"] = {k: v for k, v in resource_record.items() if k != "result"}
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
    p = sub.add_parser("validation-smoke", help="bounded non-freezeable models; full VALIDATION resource probes")
    p.add_argument("index"); p.add_argument("--output", required=True)
    p = sub.add_parser("qualify-validation"); p.add_argument("run")
    p = sub.add_parser("freeze"); p.add_argument("run")
    p = sub.add_parser("open-test"); p.add_argument("run")
    p.add_argument("--confirm", required=True, choices=("OPEN_REAL_TEST_ONCE",))
    for command in ("preflight", "tune"):
        command_parser = sub.choices[command]
        command_parser.add_argument("--expected-index-sha", help="preregistered 64-hex corpus index SHA-256")
        command_parser.add_argument("--expected-split-counts", metavar="TRAIN,VALIDATION,TEST",
                                    help="three positive source counts, in TRAIN,VALIDATION,TEST order")
    args = parser.parse_args(argv)
    binding = DEFAULT_CORPUS_BINDING
    if args.command in ("preflight", "tune"):
        sha, counts = args.expected_index_sha, args.expected_split_counts
        if (sha is None) != (counts is None):
            parser.error("expected-index-sha and expected-split-counts must be supplied together")
        if sha is not None:
            import re
            if re.fullmatch(r"[0-9]+,[0-9]+,[0-9]+", counts) is None or any(int(v) <= 0 for v in counts.split(",")):
                parser.error("expected-split-counts requires three positive integers: TRAIN,VALIDATION,TEST")
            try:
                binding = CorpusBinding(sha, dict(zip(SPLIT_NAMES, map(int, counts.split(",")))))
            except ValueError as exc:
                parser.error(str(exc))
    if args.command == "preflight":
        result = preflight(args.index, args.output, binding=binding)
    elif args.command == "tune":
        result = tune(args.index, args.output, threads=args.threads, device=args.device, binding=binding)
    elif args.command == "validation-smoke":
        result = validation_smoke(args.index, args.output)
    elif args.command == "qualify-validation":
        result = qualify_validation(args.run)
    elif args.command == "freeze":
        result = freeze(args.run)
    else:
        result = open_test(args.run, args.confirm)
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
