"""Retrain vcont-natpert and vroll-natpert with the unchanged §397 recipe (copied from silver_synth_gates.cmd_train)."""
import json, os, sys
REPO, FEAT, OUT = sys.argv[1:4]
sys.path.insert(0, os.path.join(REPO, "tools"))
import numpy as np
import silver_synth_gates as g
os.makedirs(OUT, exist_ok=True)
X, metas, n_state = g.load(FEAT)
variants = g.ARMS["natpert"]
def pick(kind, cond):
    return np.array([i for i, m in enumerate(metas) if m["k"] == kind and m["variant"] in variants and cond(m)], dtype=np.int64)
y = lambda rows: np.array([metas[i]["value"] for i in rows])
rep = {"rows": X.shape[0], "width": X.shape[1]}
lab = lambda f: (lambda m: m.get("role") == "label" and m["valid"] and not m["terminal"] and g.fold(m) in f)
tr, va = pick("child", lab((0, 1, 2))), pick("child", lab((g.VAL,)))
m = g.train_model(X[tr], y(tr), X[va], y(va), "regression"); m.save_model(os.path.join(OUT, "vcont-natpert.txt"))
rep["vcont-natpert"] = {"train": len(tr), "val": len(va), "iters": m.best_iteration}
lf = lambda f: (lambda mm: g.fold(mm) in f)
tr, va = pick("leaf", lf((0, 1, 2))), pick("leaf", lf((g.VAL,)))
m = g.train_model(X[tr], y(tr), X[va], y(va), "regression"); m.save_model(os.path.join(OUT, "vroll-natpert.txt"))
rep["vroll-natpert"] = {"train": len(tr), "val": len(va), "iters": m.best_iteration}
json.dump(rep, open(os.path.join(OUT, "train.json"), "w"), indent=2); print(rep)
