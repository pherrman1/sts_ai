#!/usr/bin/env python3
"""Leakage-safe offline selection and one-shot anchor evaluation for M10 blends."""

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import xgboost as xgb

ALPHAS = (0.0, 0.1, 0.25, 0.5, 0.75, 1.0)
EXPECTED = {
    "corpus": "bdac7173f789cd1439438eca5079a167e15de7f9aaf8c4fc242635a38790a2c7",
    "manifest": "db67ff9df6a1578a46e4e09038b5f2548772fc9c70fc54a00b1576f659883cd7",
    "relabels": "abce8e1c59def61f4b1206ae0515486bf0faf5a23586cd7a59fced83a961865c",
    "features": "c23e5974a916ae59e34dacfbb1e9dcd6eea803cb77ff42a0e1390a87856a9987",
    "model": "cfb7bf8b041e6748a6a63f280eb8c43ad2bbefc223e69d0d9807567ebcbe5613",
}
M10_TREES = 501


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def jsonl(path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{number}: {exc}") from exc


def interval(values):
    values = sorted(values)
    return [float(np.quantile(values, .025)), float(np.quantile(values, .975))]


def metrics(rows, prediction):
    groups = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    concordant = pair_count = prediction_ties = top = 0
    regrets, centered = [], []
    for group_rows in groups.values():
        refs = np.asarray([r["reference"] for r in group_rows])
        preds = np.asarray([prediction(r) for r in group_rows])
        if len(group_rows) < 2:
            continue
        for i in range(len(group_rows)):
            for j in range(i + 1, len(group_rows)):
                reference_sign = np.sign(refs[i] - refs[j])
                if reference_sign == 0:
                    continue
                pair_count += 1
                prediction_sign = np.sign(preds[i] - preds[j])
                if prediction_sign == 0:
                    concordant += .5
                    prediction_ties += 1
                elif prediction_sign == reference_sign:
                    concordant += 1
        best_reference = float(refs.max())
        selected = int(np.argmax(preds))
        top += int(refs[selected] == best_reference)
        regrets.append(best_reference - float(refs[selected]))
        centered.extend((preds - preds.mean()) - (refs - refs.mean()))
    return {
        "rows": len(rows), "complete_sibling_groups": len(groups),
        "reference_pairs": pair_count, "prediction_ties": prediction_ties,
        "pairwise": concordant / pair_count if pair_count else None,
        "top_leaf": top / len(groups) if groups else None,
        "mean_regret": statistics.fmean(regrets) if regrets else None,
        "median_regret": statistics.median(regrets) if regrets else None,
        "centered_mae": statistics.fmean(abs(x) for x in centered) if centered else None,
        "centered_rmse": math.sqrt(statistics.fmean(x*x for x in centered)) if centered else None,
    }


def bootstrap(rows, candidates, replicates, seed):
    groups = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    group_ids = sorted(groups)
    names = list(candidates)
    pair_scores = np.zeros((len(names), len(group_ids)))
    pair_counts = np.zeros(len(group_ids))
    tops = np.zeros((len(names), len(group_ids)))
    regrets = np.zeros((len(names), len(group_ids)))
    for gi, group_id in enumerate(group_ids):
        group = groups[group_id]
        refs = np.asarray([row["reference"] for row in group])
        best = refs.max()
        for ni, name in enumerate(names):
            preds = np.asarray([candidates[name](row) for row in group])
            tops[ni, gi] = refs[int(np.argmax(preds))] == best
            regrets[ni, gi] = best - refs[int(np.argmax(preds))]
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    reference_sign = np.sign(refs[i] - refs[j])
                    if reference_sign == 0:
                        continue
                    if ni == 0:
                        pair_counts[gi] += 1
                    prediction_sign = np.sign(preds[i] - preds[j])
                    pair_scores[ni, gi] += .5 if prediction_sign == 0 else prediction_sign == reference_sign
    rng = np.random.default_rng(seed)
    samples = {name: defaultdict(list) for name in names if name != "rollout"}
    base_index = names.index("rollout")
    for _ in range(replicates):
        counts = np.bincount(rng.integers(0, len(group_ids), len(group_ids)), minlength=len(group_ids))
        denominator = float(pair_counts @ counts)
        base_pair = float(pair_scores[base_index] @ counts) / denominator
        base_top = float(tops[base_index] @ counts) / len(group_ids)
        base_regret = float(regrets[base_index] @ counts) / len(group_ids)
        for ni, name in enumerate(names):
            if name == "rollout":
                continue
            samples[name]["pairwise"].append(float(pair_scores[ni] @ counts) / denominator - base_pair)
            samples[name]["top_leaf"].append(float(tops[ni] @ counts) / len(group_ids) - base_top)
            samples[name]["mean_regret"].append(float(regrets[ni] @ counts) / len(group_ids) - base_regret)
    return {name: {metric: {"delta_95pct": interval(values),
                             "probability_improves": statistics.fmean(
                                 (v > 0) if metric != "mean_regret" else (v < 0) for v in values)}
                   for metric, values in result.items()} for name, result in samples.items()}


def subgroup(rows, prediction, depth_edges):
    selectors = {
        **{f"act_{v}": lambda r, v=v: r["act"] == v for v in sorted({r["act"] for r in rows})},
        **{f"encounter_{v}": lambda r, v=v: r["encounter_category"] == v for v in sorted({r["encounter_category"] for r in rows})},
        "hp_low": lambda r: r["hp_fraction"] < .33,
        "hp_mid": lambda r: .33 <= r["hp_fraction"] < .67,
        "hp_high": lambda r: r["hp_fraction"] >= .67,
        "rollout_short": lambda r: r["rollout_length"] <= 1,
        "rollout_medium": lambda r: 1 < r["rollout_length"] <= 3,
        "rollout_long": lambda r: r["rollout_length"] > 3,
        f"depth_lt_{depth_edges[0]}": lambda r: r["search_depth"] < depth_edges[0],
        f"depth_{depth_edges[0]}_to_{depth_edges[1]-1}": lambda r: depth_edges[0] <= r["search_depth"] < depth_edges[1],
        f"depth_ge_{depth_edges[1]}": lambda r: r["search_depth"] >= depth_edges[1],
    }
    result = {}
    for name, select in selectors.items():
        selected = [r for r in rows if select(r)]
        complete_ids = {r["group_id"] for r in selected}
        complete = [r for r in rows if r["group_id"] in complete_ids and all(select(x) for x in rows if x["group_id"] == r["group_id"])]
        if complete:
            result[name] = metrics(complete, prediction)
    return result


def load(args):
    paths = {name: getattr(args, name) for name in EXPECTED}
    hashes = {name: sha256(path) for name, path in paths.items()}
    mismatches = {name: [EXPECTED[name], value] for name, value in hashes.items() if value != EXPECTED[name]}
    if mismatches:
        raise SystemExit(f"immutable input hash mismatch: {mismatches}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("manifest_schema") != "silver_leaf_manifest_v1":
        raise SystemExit("incompatible manifest schema")
    corpus = {}
    for row in jsonl(args.corpus):
        if row.get("corpus_schema") != "silver_leaf_corpus_v1":
            raise SystemExit("incompatible corpus schema")
        if row["leaf_snapshot_id"] in corpus:
            raise SystemExit(f"duplicate corpus leaf {row['leaf_snapshot_id']}")
        corpus[row["leaf_snapshot_id"]] = row
    if set(manifest["leaf_snapshot_ids"]) != set(corpus):
        raise SystemExit("manifest/corpus leaf membership mismatch")
    corpus_group_sizes = Counter(row["group_id"] for row in corpus.values())
    with args.features.open(encoding="utf-8") as stream:
        header = json.loads(next(stream))
        feature_rows = [json.loads(line) for line in stream]
    if header.get("feature_schema") != "silver_leaf_combat_features_v1" or "feature_names" not in header:
        raise SystemExit("incompatible feature header")
    feature_leaves = set()
    for row in feature_rows:
        leaf = row["leaf_snapshot_id"]
        if leaf in feature_leaves:
            raise SystemExit(f"duplicate feature leaf {leaf}")
        feature_leaves.add(leaf)
        if len(row["features"]) != len(header["feature_names"]):
            raise SystemExit(f"feature width mismatch for {leaf}")
        if leaf not in corpus or row["group_id"] != corpus[leaf]["group_id"]:
            raise SystemExit(f"feature/corpus identity mismatch for {leaf}")
    if feature_leaves != set(corpus):
        raise SystemExit("feature/corpus leaf membership mismatch")
    labels, anchors = {}, set()
    relabel_keys = set()
    for row in jsonl(args.relabels):
        if row.get("relabel_schema") != "silver_leaf_teacher_v1":
            raise SystemExit("incompatible relabel schema")
        key = (row["leaf_snapshot_id"], row["state_kind"], row["budget"], row["replicate"])
        if key in relabel_keys:
            raise SystemExit(f"duplicate relabel identity {key}")
        relabel_keys.add(key)
        if row["state_kind"] != "leaf" or not row.get("teacher_valid", True):
            continue
        if row["leaf_snapshot_id"] not in corpus or row["group_id"] != corpus[row["leaf_snapshot_id"]]["group_id"]:
            raise SystemExit(f"relabel/corpus identity mismatch for {row['leaf_snapshot_id']}")
        if row["budget"] == 25000 and row["replicate"] == "B":
            anchors.add(row["group_id"])
        if row["budget"] == 25000:
            labels[(row["leaf_snapshot_id"], row["replicate"])] = row["original_root_corrected_teacher_value"]
    model = xgb.Booster()
    model.load_model(args.model)
    if model.feature_names != header["feature_names"]:
        raise SystemExit("model/feature-header name mismatch")
    matrix = np.asarray([r["features"] for r in feature_rows], dtype=np.float32)
    predictions = model.predict(
        xgb.DMatrix(matrix, feature_names=header["feature_names"] if "feature_names" in header else None),
        iteration_range=(0, M10_TREES))
    result = []
    for feature, prediction in zip(feature_rows, predictions):
        leaf = feature["leaf_snapshot_id"]
        source = corpus.get(leaf)
        if source is None or (leaf, "A") not in labels:
            continue
        result.append({**feature, "act": source["act"], "search_depth": source["search_depth"],
                       "corpus_group_size": corpus_group_sizes[source["group_id"]],
                       "rollout_length": source["aux_rollout"]["action_count"],
                       "rollout": source["aux_rollout"]["utility_original_root"],
                       "m10": float(prediction), "reference_A": labels[(leaf, "A")],
                       "reference_B": labels.get((leaf, "B"))})
    return result, anchors, hashes


def validate_lock(lock, hashes):
    if lock.get("schema") != "silver_m10_rollout_blend_lock_v1" or lock.get("input_hashes") != hashes:
        raise SystemExit("invalid candidate lock or input-hash mismatch")
    candidates = lock.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 2:
        raise SystemExit("lock must contain one or two candidates")
    kinds = [candidate.get("kind") for candidate in candidates]
    if any(kinds.count(kind) > 1 for kind in ("fixed", "depth")) or any(kind not in ("fixed", "depth") for kind in kinds):
        raise SystemExit("lock permits at most one fixed and one depth candidate")
    names = [candidate.get("name") for candidate in candidates]
    if len(set(names)) != len(names) or any(not name or name in ("rollout", "m10") for name in names):
        raise SystemExit("locked candidate names must be unique and cannot collide with controls")
    depth_edges = lock.get("depth_edges")
    if not isinstance(depth_edges, list) or len(depth_edges) != 2 or depth_edges != sorted(depth_edges):
        raise SystemExit("lock must record the two selection depth edges")
    if not lock.get("selection_metrics") or not lock.get("decision_rule"):
        raise SystemExit("lock must record selection metrics and the decision rule")
    for candidate in candidates:
        if candidate["kind"] == "fixed" and candidate.get("alpha") not in ALPHAS[1:-1]:
            raise SystemExit("fixed alpha must be a nonzero non-control coarse-grid value")
        if candidate["kind"] == "depth":
            if candidate.get("alpha_deep") not in ALPHAS[1:-1] or candidate.get("min_depth") not in depth_edges:
                raise SystemExit("depth candidate must use a coarse-grid alpha and preregistered edge")
    return candidates


def complete(rows):
    by_group = defaultdict(list)
    for row in rows:
        by_group[row["group_id"]].append(row)
    return [row for group in by_group.values()
            if len(group) >= 2 and len(group) == group[0]["corpus_group_size"]
            for row in group]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("select", "anchor"))
    for name in EXPECTED:
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260827)
    args = parser.parse_args()
    rows, anchors, hashes = load(args)
    if any((row["group_id"] in anchors) != (row["reference_B"] is not None) for row in rows):
        raise SystemExit("anchor membership/25k-B row mismatch")
    selection = complete([dict(row, reference=row["reference_A"]) for row in rows if row["group_id"] not in anchors])
    depths = sorted(r["search_depth"] for r in selection)
    depth_edges = [int(np.quantile(depths, q, method="higher")) for q in (1/3, 2/3)]
    if depth_edges[0] == depth_edges[1]:
        depth_edges[1] += 1
    fixed = {f"alpha_{alpha:g}": (lambda r, alpha=alpha: (1-alpha)*r["rollout"] + alpha*r["m10"]) for alpha in ALPHAS}
    fixed["rollout"] = fixed.pop("alpha_0")
    if args.mode == "select":
        report = {"schema": "silver_m10_rollout_blend_selection_v1", "inputs": hashes,
                  "leakage": {"anchor_groups_excluded": len(anchors), "anchor_rows_inspected_for_metrics": 0},
                  "depth_bins_pre_metric": depth_edges,
                  "selection_metrics": {name: metrics(selection, fn) for name, fn in fixed.items()},
                  "selection_bootstrap_vs_rollout": bootstrap(selection, fixed, args.bootstrap_replicates, args.bootstrap_seed),
                  "subgroups": {name: subgroup(selection, fn, depth_edges) for name, fn in fixed.items()}}
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if args.lock.exists():
            raise SystemExit("lock already exists; refusing to overwrite")
        print(json.dumps({"output": str(args.output), "depth_edges": depth_edges,
                          "instruction": "inspect selection report, then create the candidate lock explicitly"}))
        return
    lock = json.loads(args.lock.read_text(encoding="utf-8"))
    locked_candidates = validate_lock(lock, hashes)
    candidates = {"rollout": fixed["rollout"], "m10": fixed["alpha_1"]}
    for candidate in locked_candidates:
        if candidate["kind"] == "fixed":
            alpha = candidate["alpha"]
            candidates[candidate["name"]] = lambda r, alpha=alpha: (1-alpha)*r["rollout"] + alpha*r["m10"]
        elif candidate["kind"] == "depth":
            alpha, threshold = candidate["alpha_deep"], candidate["min_depth"]
            candidates[candidate["name"]] = lambda r, alpha=alpha, threshold=threshold: r["rollout"] if r["search_depth"] < threshold else (1-alpha)*r["rollout"] + alpha*r["m10"]
    anchor = complete([dict(row, reference=row["reference_B"]) for row in rows if row["group_id"] in anchors and row["reference_B"] is not None])
    report = {"schema": "silver_m10_rollout_blend_anchor_v1", "inputs": hashes, "lock": lock,
              "anchor_metrics": {name: metrics(anchor, fn) for name, fn in candidates.items()},
              "anchor_bootstrap_vs_rollout": bootstrap(anchor, candidates, args.bootstrap_replicates, args.bootstrap_seed + 1),
              "subgroups": {name: subgroup(anchor, fn, lock["depth_edges"]) for name, fn in candidates.items()}}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
