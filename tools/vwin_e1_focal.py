"""E1: focal retrain of the #334 X2 family on the frozen 1,024-source corpus.

Offline, TRAIN/VALIDATION only. TEST components are never opened. The corpus
was strictly validated for #334 (`validate_corpus`); this script re-checks only
the index, component-manifest and table SHA-256 values instead of re-running
the slow bundle validator.

Arms (same X2-B recipe: depth 6, eta 0.06, min_child_weight 10, curHp
monotone, subsample 0.8, colsample 0.7, hist, early stopping on VALIDATION):

- X2B: the frozen X2-B checkpoint as is (461 features, includes the four
  HIDDEN_FUTURE queue fields).
- P0: X2-B recipe retrained on all MAP rows, public 457 features.
- F1: focal rows only (first MAP row after each sampled sibling option), each
  decision's siblings sharing total weight 1, rescaled to mean weight 1.
- F2: all MAP rows; non-focal weight 1, focal rows keep F1's per-decision
  shares, scaled so the focal block's total weight equals the non-focal total.

Selection gain per sampled decision: won(model's argmax sibling) minus
won(V4/source chosen sibling), both from that sibling's own branch rollout;
predicted ties average the tied siblings' outcomes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from tools.vwin_refresh_contract import MAP_PREFIX, OUTPUTS
from tools.vwin_refresh_dataset import source_split

HIDDEN_FUTURE = ("nextEliteId", "nextFight0", "nextFight1", "nextFight2")
X2B_RECIPE = dict(max_depth=6, eta=0.06, min_child_weight=10)
CORPUS_SHA256 = "ae56f9633ce8da8a72e341978d707c9f145c1f1b6479afa438067af5570dfa00"
SPLIT_COUNTS = {"TRAIN": 696, "VALIDATION": 155, "TEST": 173}
X2B_MODEL_SHA256 = "99dbac6b5b082c46fe07242d2d15d8ccc6818041cb851efa79d6b423cdcb52dd"
X2B_VALIDATION_NLL = 0.4226083643848224


def sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table(manifest: Path, kind: str) -> Path:
    return Path(str(manifest)[:-len(".manifest.json")] + OUTPUTS[kind])


def load_split_tables(index_path, feature_names, splits=("TRAIN", "VALIDATION"), smoke=None):
    """Return per-split MAP matrices, labels, row metadata and branches."""
    import pandas as pd
    if "TEST" in splits:
        raise ValueError("TEST stays closed for E1")
    index_path = Path(index_path)
    if sha256(index_path) != CORPUS_SHA256:
        raise ValueError("corpus index SHA-256 mismatch")
    index = json.loads(index_path.read_text())
    counts = defaultdict(int)
    for seed in index["sourceSeeds"]:
        counts[source_split(int(seed))] += 1
    if dict(counts) != SPLIT_COUNTS:
        raise ValueError(f"split counts mismatch: {dict(counts)}")
    out = {s: dict(X=[], y=[], seed=[], branch=[], row=[], act=[], branches=[]) for s in splits}
    header_names = None
    for comp in index["components"]:
        manifest = (index_path.parent / comp["manifest"]).resolve()
        doc_bytes = manifest.read_bytes()
        if hashlib.sha256(doc_bytes).hexdigest() != comp["sha256"]:
            raise ValueError(f"{manifest}: manifest SHA-256 mismatch")
        doc = json.loads(doc_bytes)
        spec = doc["seedSpec"]
        comp_split = {source_split(s) for s in range(int(spec["start"]), int(spec["start"]) + int(spec["count"]))}
        if len(comp_split) != 1:
            raise ValueError("component spans splits")
        split = comp_split.pop()
        if split not in splits:
            continue  # TEST (or unrequested) component: tables are never opened.
        if smoke is not None and len(out[split]["y"]) >= smoke:
            continue
        if header_names is None:
            header_names = doc["stateFeatures"]["header"].split(",")
            missing = [n for n in feature_names if n not in header_names]
            if missing:
                raise ValueError(f"features absent: {missing}")
            cols = [len(MAP_PREFIX) + header_names.index(n) for n in feature_names]
        elif doc["stateFeatures"]["header"].split(",") != header_names:
            raise ValueError("feature header changed")
        for kind in ("map.csv", "runout.csv", "branches.csv"):
            if sha256(_table(manifest, kind)) != doc["outputs"][kind]:
                raise ValueError(f"{manifest}: {kind} SHA-256 mismatch")
        runout = pd.read_csv(_table(manifest, "runout.csv"), dtype={"branchId": str})
        if not ((runout["trajectoryValid"] == 1) & runout["finalWon"].isin([0, 1])).all():
            raise ValueError("invalid runout")
        labels = dict(zip(zip(runout["sourceSeed"].astype(int), runout["branchId"]), runout["finalWon"].astype(int)))
        meta = pd.read_csv(_table(manifest, "map.csv"), header=None, skiprows=1, usecols=[0, 1, 3, 4],
                           names=["sourceSeed", "branchId", "rowIdx", "act"], dtype={1: str})
        feats = pd.read_csv(_table(manifest, "map.csv"), header=None, skiprows=1, usecols=cols,
                            dtype=np.float32, engine="c").to_numpy(dtype=np.float32)
        feats = feats[:, np.argsort(np.argsort(cols))]  # pandas returns ascending column order
        if not np.isfinite(feats).all():
            raise ValueError("nonfinite feature")
        if {source_split(int(s)) for s in meta["sourceSeed"].unique()} != {split}:
            raise ValueError("row split mismatch")
        keys = list(zip(meta["sourceSeed"].astype(int), meta["branchId"]))
        d = out[split]
        d["X"].append(feats)
        d["y"].append(np.array([labels[k] for k in keys], dtype=np.float32))
        d["seed"].append(meta["sourceSeed"].to_numpy(np.int64))
        d["branch"].extend(meta["branchId"].tolist())
        d["row"].append(meta["rowIdx"].to_numpy(np.int64))
        d["act"].append(meta["act"].to_numpy(np.int64))
        br = pd.read_csv(_table(manifest, "branches.csv"), dtype={"branchId": str, "optionKey": str})
        if not ((br["valid"] == 1) & br["won"].isin([0, 1])).all():
            raise ValueError("invalid branch outcome")
        d["branches"].extend(br[["sourceSeed", "decisionIdx", "type", "chosen", "branchId", "won"]]
                             .to_dict("records"))
    for split, d in out.items():
        d["X"] = np.concatenate(d["X"])
        for key in ("y", "seed", "row", "act"):
            d[key] = np.concatenate(d[key])
        d["branch"] = np.asarray(d["branch"], dtype=object)
    return out


def focal_rows(seed, branch, row, branches):
    """Map each branch to its focal MAP row index (sibling_ranking join rule).

    MAP branches skip the pre-decision rowIdx=0; others use the minimum rowIdx.
    Returns (focal index per branch or -1, decision key per branch).
    """
    first, first_pos = {}, {}
    for i, (s, b, r) in enumerate(zip(seed, branch, row)):
        key = int(s), b
        if key not in first or r < row[first[key]]:
            first[key] = i
        if r > 0 and (key not in first_pos or r < row[first_pos[key]]):
            first_pos[key] = i
    idx = []
    for br in branches:
        key = int(br["sourceSeed"]), br["branchId"]
        table = first_pos if br["type"] == "MAP" else first
        idx.append(table.get(key, -1))
    return np.asarray(idx, dtype=np.int64)


def focal_weights(branches, focal_idx, n_rows):
    """F1 per-row weights over all rows (0 for non-focal); decisions sum to 1."""
    groups = defaultdict(list)
    for b, i in zip(branches, focal_idx):
        if i >= 0:
            groups[(int(b["sourceSeed"]), int(b["decisionIdx"]))].append(i)
    w = np.zeros(n_rows, dtype=np.float64)
    for members in groups.values():
        for i in members:
            w[i] += 1.0 / len(members)
    focal = w > 0
    w[focal] *= focal.sum() / w[focal].sum()
    return w


def arm_weights(arm, f1):
    focal = f1 > 0
    if arm == "P0":
        return np.ones_like(f1)
    if arm == "F1":
        return f1
    if arm == "F2":
        w = np.ones_like(f1)
        w[focal] = f1[focal] * ((~focal).sum() / f1[focal].sum())
        return w
    raise ValueError(arm)


def selection_gain(branches, focal_idx, scores):
    """Per-decision gain of model argmax over the chosen sibling (+ references)."""
    groups = defaultdict(list)
    for b, i in zip(branches, focal_idx):
        groups[(int(b["sourceSeed"]), int(b["decisionIdx"]), b["type"])].append((b, i))
    rows, skipped = [], defaultdict(int)
    for (seed, _, typ), members in groups.items():
        chosen = [b for b, _ in members if int(b["chosen"]) == 1]
        if len(members) < 2 or len(chosen) != 1 or any(i < 0 for _, i in members):
            skipped[typ] += 1
            continue
        s = np.array([scores[i] for _, i in members])
        won = np.array([int(b["won"]) for b, _ in members], dtype=float)
        top = np.isclose(s, s.max(), rtol=0, atol=1e-12)
        base = float(chosen[0]["won"])
        rows.append(dict(seed=seed, type=typ, gain=float(won[top].mean()) - base,
                         oracle=float(won.max()) - base, uniform=float(won.mean()) - base,
                         agrees=bool(top[[int(b["chosen"]) == 1 for b, _ in members]].all() and top.sum() == 1),
                         discordant=bool(won.min() != won.max())))
    return rows, dict(skipped)


def summarize_gain(rows, reps=2000, key="gain", baseline=None):
    from tools.vwin_refresh_evaluation import cluster_mean
    out = {}
    by_type = defaultdict(list)
    for i, r in enumerate(rows):
        by_type[r["type"]].append(i)
        by_type["pooled"].append(i)
    for typ, ids in sorted(by_type.items()):
        values = [rows[i][key] - (baseline[i][key] if baseline else 0.0) for i in ids]
        res = cluster_mean(values, [rows[i]["seed"] for i in ids], reps, 0)
        res["decisions"] = len(ids)
        res["discordant_decisions"] = sum(rows[i]["discordant"] for i in ids)
        res["agree_with_v4"] = float(np.mean([rows[i]["agrees"] for i in ids]))
        out[typ] = res
    return out


def train_arm(arm, seed, data, f1_train, f1_val, names, threads, outdir, max_rounds=2500):
    import xgboost as xgb
    from tools.vwin_refresh_training import XGBPredictor, xgb_parameters
    params = {**xgb_parameters(names, monotone=True, threads=threads), **X2B_RECIPE, "seed": seed}
    tr, va = data["TRAIN"], data["VALIDATION"]
    wt, wv = arm_weights(arm, f1_train), arm_weights(arm, f1_val)
    kt, kv = wt > 0, wv > 0
    dtrain = xgb.DMatrix(tr["Xp"][kt], label=tr["y"][kt], weight=wt[kt], feature_names=list(names))
    dval = xgb.DMatrix(va["Xp"][kv], label=va["y"][kv], weight=wv[kv], feature_names=list(names))
    t0 = time.time()
    booster = xgb.train(params, dtrain, num_boost_round=max_rounds, evals=[(dval, "validation")],
                        early_stopping_rounds=50, verbose_eval=False)
    count = booster.best_iteration + 1
    booster = booster[:count]
    predictor = XGBPredictor(booster, names)
    path = Path(outdir) / f"{arm}-s{seed}"
    predictor.save(path)
    return predictor, dict(arm=arm, seed=seed, params=params, tree_count=count,
                           train_rows=int(kt.sum()), train_weight_sum=float(wt[kt].sum()),
                           seconds=time.time() - t0, model_sha256=sha256(path / "model.ubj"))


def evaluate(name, p, va, focal_val_mask, branches, focal_idx, reps):
    from tools.vwin_refresh_evaluation import predictive_metrics, sibling_ranking
    y = va["y"]
    by_type = defaultdict(list)
    for b, i in zip(branches, focal_idx):
        if i >= 0:
            by_type[b["type"]].append(i)
    focal_ids = np.flatnonzero(focal_val_mask)
    strip = lambda m: {k: m[k] for k in ("n", "nll", "brier", "roc_auc", "ece")}
    meta = [dict(sourceSeed=int(s), branchId=b, rowIdx=int(r)) for s, b, r in zip(va["seed"], va["branch"], va["row"])]
    rows, skipped = selection_gain(branches, focal_idx, p)
    return dict(
        arm=name,
        all_rows=strip(predictive_metrics(y, p)),
        focal_rows=strip(predictive_metrics(y[focal_ids], p[focal_ids])),
        focal_by_type={t: strip(predictive_metrics(y[ids], p[ids])) for t, ids in sorted(by_type.items())},
        selection_gain=summarize_gain(rows, reps),
        selection_skipped=skipped,
        sibling_ranking=sibling_ranking(meta, p, [dict(b, valid=1) for b in branches], reps, 0),
    ), rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("index")
    ap.add_argument("--x2b-run", required=True, help="frozen X2-B tune directory")
    ap.add_argument("--output", required=True)
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--seeds", default="0,1,2")
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--smoke", type=int, help="load N components per split, 20 rounds, no anchor check")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("OMP_NUM_THREADS", str(args.threads))
    from tools.vwin_refresh_training import load_predictor
    from tools.vwin_refresh_evaluation import clustered_delta
    x2b_dir = Path(args.x2b_run) / "X2"
    if sha256(x2b_dir / "model.ubj") != X2B_MODEL_SHA256:
        raise ValueError("X2-B model SHA-256 mismatch")
    x2b = load_predictor(x2b_dir)
    full = list(x2b.feature_names)
    public = [n for n in full if n not in HIDDEN_FUTURE]
    if len(full) != 461 or len(public) != 457:
        raise ValueError("unexpected X2-B feature set")
    t0 = time.time()
    data = load_split_tables(args.index, full, smoke=args.smoke)
    log = dict(load_seconds=time.time() - t0, rows={s: int(len(d["y"])) for s, d in data.items()},
               branches={s: len(d["branches"]) for s, d in data.items()})
    print(json.dumps(log), flush=True)
    pub_cols = [full.index(n) for n in public]
    f1 = {}
    for s, d in data.items():
        d["Xp"] = np.ascontiguousarray(d["X"][:, pub_cols])
        d["focal_idx"] = focal_rows(d["seed"], d["branch"], d["row"], d["branches"])
        f1[s] = focal_weights(d["branches"], d["focal_idx"], len(d["y"]))
        log[f"{s}_focal_rows"] = int((f1[s] > 0).sum())
        log[f"{s}_branches_without_focal"] = int((d["focal_idx"] < 0).sum())
    va = data["VALIDATION"]
    del data["TRAIN"]["X"]
    focal_val = f1["VALIDATION"] > 0
    preds = {"X2B": x2b.predict(va["X"])}
    check = float(np.mean(-(va["y"] * np.log(np.clip(preds["X2B"], 1e-15, 1)) +
                            (1 - va["y"]) * np.log(np.clip(1 - preds["X2B"], 1e-15, 1)))))
    log["x2b_validation_nll_recomputed"] = check
    if args.smoke is None and (abs(check - X2B_VALIDATION_NLL) > 1e-9 or len(va["y"]) != 141566):
        raise ValueError(f"X2-B VALIDATION anchor mismatch: {check}")
    trained = []
    for arm in ("P0", "F1", "F2"):
        arm_preds = []
        for seed in [int(s) for s in args.seeds.split(",")]:
            predictor, info = train_arm(arm, seed, data, f1["TRAIN"], f1["VALIDATION"], public, args.threads, out,
                                         20 if args.smoke else 2500)
            trained.append(info)
            print(json.dumps({k: v for k, v in info.items() if k != "params"}), flush=True)
            p = predictor.predict(va["Xp"])
            preds[f"{arm}-s{seed}"] = p
            arm_preds.append(p)
        preds[arm] = np.mean(arm_preds, axis=0)  # 3-seed probability-mean ensemble (primary)
    results, gain_rows = {}, {}
    for name, p in preds.items():
        results[name], gain_rows[name] = evaluate(name, p, va, focal_val, va["branches"], va["focal_idx"], args.reps)
    comparisons = {}
    for name in ("X2B", "F1", "F2"):
        comparisons[f"{name}_minus_P0"] = dict(
            all_rows={k: clustered_delta(va["y"], preds["P0"], preds[name], va["seed"], args.reps)[k] for k in ("nll", "brier")},
            focal_rows={k: clustered_delta(va["y"][focal_val], preds["P0"][focal_val], preds[name][focal_val],
                                           va["seed"][focal_val], args.reps)[k] for k in ("nll", "brier")},
            selection_gain=summarize_gain(gain_rows[name], args.reps, baseline=gain_rows["P0"]))
    references = dict(oracle=summarize_gain(gain_rows["P0"], args.reps, key="oracle"),
                      uniform_random=summarize_gain(gain_rows["P0"], args.reps, key="uniform"))
    report = dict(schema="vwin_e1_focal_v1", smoke=args.smoke, corpus_sha256=CORPUS_SHA256, x2b_model_sha256=X2B_MODEL_SHA256,
                  hidden_future_removed=list(HIDDEN_FUTURE), public_feature_count=len(public),
                  recipe=X2B_RECIPE, seeds=args.seeds, threads=args.threads, test_opened=False,
                  log=log, trained=trained, results=results, comparisons=comparisons, references=references)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=float) + "\n")
    np.savez_compressed(out / "validation-predictions.npz", seed=va["seed"], row=va["row"],
                        branch=va["branch"].astype(str), y=va["y"], focal=focal_val, **preds)
    print("DONE", out / "report.json", flush=True)


if __name__ == "__main__":
    main()
