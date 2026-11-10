#!/usr/bin/env python3
"""Learned stop for the whole-run Gumbel root at sequential-halving boundaries (research).

Input: CSVs (.csv or .csv.xz) written by STS_SILVER_GUMBEL_STOP_TRACE, one row per halving boundary of a root.
A root with P phases has boundaries 0..P; boundary P is the full search. A stop at boundary b < P plays the
leader of that row. The label of a row is "leader differs from the full-budget pick" (1 - leader_is_final).
The model is a sklearn HistGradientBoostingClassifier exported as trees (same format and C++ evaluator style as
tools/silver_learned_stop.py).

  gumbel_learned_stop.py cv TRACE_DIR --folds 4 --out FILE
      out-of-fold (folds by run seed) agreement vs CPU fraction for a threshold grid
  gumbel_learned_stop.py train TRACE_DIR --threshold T --out-dir DIR [--suffix Gumbel]
      fit on all runs, write model.json, NativeSilverGumbelStopModel<suffix>.cpp and in-sample offline.json
  gumbel_learned_stop.py selftest
"""
import argparse
import csv
import hashlib
import io
import json
import lzma
import math
import sys
from pathlib import Path

# Runtime-computable features, in the order the C++ evaluator receives them (NativeSilverGumbelStopModel.h).
FEATURES = [
    "boundary", "phases", "phases_left", "candidates", "spent_frac", "legal_actions", "inherited_visits",
    "act", "room", "turn", "score_gap", "score_gap_norm", "q_gap", "q_valid", "leader_visit_share",
    "leader_prior", "runner_up_prior", "prior_gap", "leader_same", "leader_streak", "stop_entropy",
    "stop_q_gap", "stop_root_visits",
]


def open_text(path):
    raw = Path(path).read_bytes()
    return lzma.decompress(raw).decode() if str(path).endswith(".xz") else raw.decode()


def features(r, prev):
    """One boundary row -> feature vector; prev = (leader_edge, streak) of the previous boundary of the root."""
    b, p = int(r["boundary"]), int(r["phases"])
    budget = max(float(r["budget"]), 1.0)
    leader = int(r["leader_edge"])
    same = prev is not None and prev[0] == leader
    streak = (prev[1] + 1) if same else 1
    lv = float(r["leader_visits"])
    lp, rp = float(r["leader_prior"]), float(r["runner_up_prior"])
    x = [b, p, p - b, float(r["candidates"]), float(r["spent"]) / budget, float(r["legal_actions"]),
         float(r["inherited_visits"]), float(r["act"]), float(r["room"]), float(r["turn"]),
         float(r["score_gap"]), float(r["score_gap"]) / (50.0 + lv), float(r["q_gap"]), float(r["q_valid"]),
         float(r["leader_visit_share"]), lp, rp, lp - rp if lp >= 0 and rp >= 0 else 0.0,
         1.0 if same else 0.0, float(streak), float(r["stop_entropy"]), float(r["stop_q_gap"]),
         float(r["stop_root_visits"])]
    return x, (leader, streak)


def load(trace_dir):
    """-> list of roots: {seed, rows: [(x, label, cpu_frac, sim_frac)], full_cpu}; rows are boundaries 0..P-1."""
    roots = []
    files = sorted(Path(trace_dir).glob("*.csv*"))
    for f in files:
        cur, key, prev = None, None, None
        for r in csv.DictReader(io.StringIO(open_text(f))):
            k = (r["seed"], r["combat"], r["decision"])
            if k != key:
                if cur:
                    roots.append(cur)
                key, prev = k, None
                cur = {"seed": int(r["seed"]), "rows": [], "full_cpu": float(r["root_cpu_seconds"])}
            x, prev = features(r, prev)
            if int(r["boundary"]) < int(r["phases"]):
                rc = max(float(r["root_cpu_seconds"]), 1e-12)
                cur["rows"].append((x, 1 - int(r["leader_is_final"]), float(r["cpu_seconds"]) / rc,
                                    float(r["spent"]) / max(float(r["root_sims"]), 1.0)))
        if cur:
            roots.append(cur)
    return roots


def export_hist_gbt(clf):
    trees = []
    for predictors in clf._predictors:
        tree = []
        for n in predictors[0].nodes:
            tree.append({"leaf": bool(n["is_leaf"]), "feature": int(n["feature_idx"]),
                         "threshold": float(n["num_threshold"]), "left": int(n["left"]),
                         "right": int(n["right"]), "value": float(n["value"])})
        trees.append(tree)
    return float(clf._baseline_prediction.ravel()[0]), trees


def risk(model, x):
    s = model["baseline"]
    for tree in model["trees"]:
        i = 0
        while not tree[i]["leaf"]:
            n = tree[i]
            i = n["left"] if x[n["feature"]] <= n["threshold"] else n["right"]
        s += tree[i]["value"]
    return 1.0 / (1.0 + math.exp(-s))


def fit(roots):
    from sklearn.ensemble import HistGradientBoostingClassifier
    X = [x for r in roots for x, _, _, _ in r["rows"]]
    y = [lab for r in roots for _, lab, _, _ in r["rows"]]
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31, random_state=0)
    clf.fit(X, y)
    return clf


def evaluate(roots, risks, thresholds):
    """risks[i][j] = risk of root i at boundary j. Stop at the first boundary with risk < thr."""
    total_cpu = sum(r["full_cpu"] for r in roots) or 1.0
    out = {}
    for thr in thresholds:
        cpu = sims = err = stops = 0.0
        for r, rk in zip(roots, risks):
            frac_c, frac_s, e = 1.0, 1.0, 0
            for (x, lab, cf, sf), q in zip(r["rows"], rk):
                if q < thr:
                    frac_c, frac_s, e = cf, sf, lab
                    stops += 1
                    break
            cpu += frac_c * r["full_cpu"]
            sims += frac_s
            err += e
        n = len(roots)
        out[str(thr)] = {"roots": n, "cpu_saving": 1 - cpu / total_cpu, "sim_saving": 1 - sims / n,
                         "disagreement": err / n, "stop_share": stops / n}
    return out


THRESHOLDS = [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12, 0.2]


def cv(args):
    roots = [r for r in load(args.trace_dir) if r["rows"]]
    seeds = sorted({r["seed"] for r in roots})
    fold = {s: i % args.folds for i, s in enumerate(seeds)}
    risks = [None] * len(roots)
    for f in range(args.folds):
        tr = [r for r in roots if fold[r["seed"]] != f]
        clf = fit(tr)
        idx = [i for i, r in enumerate(roots) if fold[r["seed"]] == f]
        X = [x for i in idx for x, _, _, _ in roots[i]["rows"]]
        p = clf.predict_proba(X)[:, 1]
        k = 0
        for i in idx:
            m = len(roots[i]["rows"])
            risks[i] = list(p[k:k + m])
            k += m
    rep = {"runs": len(seeds), "roots": len(roots), "folds": args.folds, "features": FEATURES,
           "out_of_fold": evaluate(roots, risks, THRESHOLDS)}
    # Reference: a hand rule that always stops at the last boundary before the full search.
    last = [[1.0] * (len(r["rows"]) - 1) + [0.0] for r in roots]
    rep["rule_last_boundary"] = evaluate(roots, last, [0.5])["0.5"]
    for name, lo, hi in (("by_phases", None, None),):
        pass
    by = {}
    for p in (1, 2, 3, 4):
        sub = [i for i, r in enumerate(roots) if int(r["rows"][0][0][1]) == p]
        by[str(p)] = evaluate([roots[i] for i in sub], [risks[i] for i in sub], [args.report_threshold])[
            str(args.report_threshold)]
    rep["by_phases_at_" + str(args.report_threshold)] = by
    Path(args.out).write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


def write_cpp(path, model, suffix):
    lines = ["// Generated by tools/gumbel_learned_stop.py; do not edit.",
             '#include "sim/search/NativeSilverGumbelStopModel.h"', "", "#include <cmath>", "",
             "namespace sts::search {", "", "namespace {",
             f'    constexpr const char *kModelId = "{model["id"]}";',
             f"    constexpr double kDefaultThreshold = {model['threshold']!r};",
             f"    constexpr double kBaseline = {model['baseline']!r};",
             "    struct Node { int feature; double threshold; int left, right; double value; bool leaf; };"]
    offsets, nodes = [], []
    for t in model["trees"]:
        offsets.append(len(nodes))
        for n in t:
            nodes.append(n)
    lines.append(f"    constexpr int kTreeCount = {len(model['trees'])};")
    lines.append("    constexpr int kTreeStart[] = {" + ", ".join(map(str, offsets)) + "};")
    lines.append("    constexpr Node kNodes[] = {")
    for n in nodes:
        lines.append(f"        {{{n['feature']}, {n['threshold']!r}, {n['left']}, {n['right']}, {n['value']!r}, "
                     f"{'true' if n['leaf'] else 'false'}}},")
    lines += ["    };", "}", "",
              f"const char *nativeSilverGumbelStopModel{suffix}Id() {{ return kModelId; }}",
              f"double nativeSilverGumbelStopModel{suffix}DefaultThreshold() {{ return kDefaultThreshold; }}",
              f"double nativeSilverGumbelStopModel{suffix}Risk(const NativeSilverGumbelStopFeatures &x) {{",
              "    double s = kBaseline;",
              "    for (int t = 0; t < kTreeCount; ++t) {",
              "        int i = 0;",
              "        const Node *base = kNodes + kTreeStart[t];",
              "        while (!base[i].leaf) i = x[base[i].feature] <= base[i].threshold ? base[i].left : base[i].right;",
              "        s += base[i].value;",
              "    }",
              "    return 1.0 / (1.0 + std::exp(-s));",
              "}", "", "}", ""]
    Path(path).write_text("\n".join(lines))


def train(args):
    roots = [r for r in load(args.trace_dir) if r["rows"]]
    clf = fit(roots)
    baseline, trees = export_hist_gbt(clf)
    digest = hashlib.sha256(json.dumps({"b": baseline, "t": trees}, sort_keys=True).encode()).hexdigest()[:12]
    model = {"id": f"ggbt-{digest}", "threshold": args.threshold, "baseline": baseline, "trees": trees,
             "features": FEATURES, "runs": len({r["seed"] for r in roots}), "roots": len(roots)}
    X = [x for r in roots[:3000] for x, _, _, _ in r["rows"]]
    probe = clf.predict_proba(X)[:, 1]
    worst = max(abs(p - risk(model, x)) for p, x in zip(probe, X))
    if worst > 1e-9:
        raise SystemExit(f"exported model differs from sklearn by {worst}")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "model.json").write_text(json.dumps(model))
    write_cpp(out / f"NativeSilverGumbelStopModel{args.suffix}.cpp", model, args.suffix)
    # Probe vectors for the C++ parity test: (x, risk) of the first rows.
    (out / "probe.json").write_text(json.dumps([{"x": x, "risk": float(p)} for x, p in zip(X[:64], probe[:64])]))
    print(json.dumps({"id": model["id"], "roots": len(roots), "trees": len(trees)}))


def parity(args):
    """A trace written with STS_SILVER_GUMBEL_LEARNED_STOP on: recompute each asked boundary's risk from the traced
    columns and compare with the C++ gstop_risk; a root stops exactly at its first boundary with risk < threshold."""
    model = json.loads(Path(args.model).read_text())
    thr = args.threshold if args.threshold is not None else model["threshold"]
    worst, asked, stops, bad_stop = 0.0, 0, 0, 0
    key, prev, rows = None, None, []

    def close(rows):
        nonlocal stops, bad_stop
        if not rows:
            return
        first = next((i for i, (b, p, g) in enumerate(rows) if b < p and 0 <= g < thr), None)
        stopped = first is not None
        stops += stopped
        # a stopped root has no row after the stop; an unstopped one reaches its last boundary
        if stopped and first != len(rows) - 1:
            bad_stop += 1
        if not stopped and rows[-1][0] != rows[-1][1]:
            bad_stop += 1

    for r in csv.DictReader(io.StringIO(open_text(args.trace))):
        k = (r["seed"], r["combat"], r["decision"])
        if k != key:
            close(rows)
            key, prev, rows = k, None, []
        x, prev = features(r, prev)
        g = float(r["gstop_risk"])
        rows.append((int(r["boundary"]), int(r["phases"]), g))
        if g >= 0:
            asked += 1
            worst = max(worst, abs(g - risk(model, x)))
    close(rows)
    out = {"asked": asked, "max_abs_diff": worst, "stops": stops, "stop_mismatch": bad_stop, "threshold": thr}
    print(json.dumps(out))
    if asked == 0 or worst > 1e-9 or bad_stop:
        raise SystemExit("parity FAIL")


def selftest():
    m = {"baseline": 0.0, "trees": [[{"leaf": False, "feature": 0, "threshold": 0.5, "left": 1, "right": 2, "value": 0},
                                     {"leaf": True, "feature": 0, "threshold": 0, "left": 0, "right": 0, "value": 2.0},
                                     {"leaf": True, "feature": 0, "threshold": 0, "left": 0, "right": 0, "value": -2.0}]]}
    x = [0.0] * len(FEATURES)
    assert risk(m, x) > 0.8
    x[0] = 1
    assert risk(m, x) < 0.2
    roots = [{"seed": 1, "full_cpu": 1.0, "rows": [([0] * len(FEATURES), 0, 0.25, 0.25), ([1] * len(FEATURES), 1, 0.5, 0.5)]}]
    ev = evaluate(roots, [[0.5, 0.0]], [0.1])["0.1"]
    assert ev["disagreement"] == 1 and abs(ev["cpu_saving"] - 0.5) < 1e-12
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cv")
    c.add_argument("trace_dir")
    c.add_argument("--folds", type=int, default=4)
    c.add_argument("--report-threshold", type=float, default=0.02)
    c.add_argument("--out", required=True)
    t = sub.add_parser("train")
    t.add_argument("trace_dir")
    t.add_argument("--threshold", type=float, required=True)
    t.add_argument("--out-dir", required=True)
    t.add_argument("--suffix", default="")
    q = sub.add_parser("parity")
    q.add_argument("trace")
    q.add_argument("--model", required=True)
    q.add_argument("--threshold", type=float)
    sub.add_parser("selftest")
    a = ap.parse_args()
    {"cv": cv, "train": train, "parity": parity, "selftest": lambda _: selftest()}[a.cmd](a)


if __name__ == "__main__":
    main()
