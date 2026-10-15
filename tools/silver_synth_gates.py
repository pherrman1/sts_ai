#!/usr/bin/env python3
"""Offline Gate A / Gate B of the synthetic Silver prior pilot.

Rules: /mnt/project-files/silver-synthetic-prior/GATES-PREREG.md.
Inputs come from `one_combat silversynthfeatures` (sparse feature rows) and
`one_combat silversynthreplay` (root search replay); see combat-search.md.

usage:
  silver_synth_gates.py train    FEATURES_DIR OUT_DIR
  silver_synth_gates.py gatea    FEATURES_DIR OUT_DIR
  silver_synth_gates.py tasks    FEATURES_DIR CORPUS_DIR OUT_DIR SPLIT ARM
  silver_synth_gates.py gateb    FEATURES_DIR OUT_DIR
  silver_synth_gates.py export   MODEL.txt NAMES.json OUT.txt FEATURES_DIR
"""
import glob
import gzip
import json
import os
import sys

import lightgbm as lgb
import numpy as np
import scipy.sparse as sp

BASE = {"natural": 56000000, "perturbed": 56002000}
TEST, VAL = 4, 3
ARMS = {"nat": ("natural",), "natpert": ("natural", "perturbed")}
PARAMS = dict(num_leaves=63, learning_rate=0.05, min_data_in_leaf=100, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, verbose=-1, num_threads=4, seed=1)
WEIGHTS = [25, 50, 100, 200, 400]
BUDGETS = [256, 1000]
REPLAY_SEEDS = [11, 12]
BOOT = 2000


def fold(meta):
    return (meta["seed"] - BASE[meta["variant"]]) % 5


def root_id(m):
    return (m["variant"], m["seed"], m["fight"], m["decision"])


def load(features_dir):
    """All sparse rows (CSR) and their meta; act/child rows inherit their root's id."""
    mats, metas = [], []
    for nnz_path in sorted(glob.glob(os.path.join(features_dir, "*.nnz"))):
        prefix = nnz_path[:-4]
        nnz = np.fromfile(prefix + ".nnz", dtype=np.uint32)
        idx = np.fromfile(prefix + ".idx", dtype=np.uint16).astype(np.int32)
        val = np.fromfile(prefix + ".val", dtype=np.float32)
        indptr = np.concatenate([[0], np.cumsum(nnz, dtype=np.int64)])
        with open(prefix + ".meta.jsonl") as f:
            meta = [json.loads(line) for line in f]
        assert len(meta) == len(nnz) and indptr[-1] == len(idx) == len(val), prefix
        summary = json.load(open(prefix + ".summary.json"))
        width = summary["policyFeatures"]
        mats.append(sp.csr_matrix((val, idx, indptr), shape=(len(nnz), width)))
        root = None
        for m in meta:
            if m["k"] in ("state", "leaf"):
                root = m
            else:
                m.update({k: root[k] for k in ("seed", "variant", "fight", "decision")})
        metas.extend(meta)
    return sp.vstack(mats, format="csr"), metas, summary["stateFeatures"]


def train_model(X, y, Xv, yv, objective):
    params = dict(PARAMS, objective=objective)
    model = lgb.train(params, lgb.Dataset(X, y), num_boost_round=2000,
                      valid_sets=[lgb.Dataset(Xv, yv)],
                      callbacks=[lgb.early_stopping(50, verbose=False)])
    return model


def edge_rows(X, metas):
    """Prior rows: each act row plus its root's state block, grouped by root."""
    roots, acts, owner = {}, [], []
    cur = None
    for i, m in enumerate(metas):
        if m["k"] == "state":
            cur = i
            roots[i] = []
        elif m["k"] == "act":
            roots[cur].append(i)
            acts.append(i)
            owner.append(cur)
    E = X[acts] + X[owner]
    return E, np.array(acts), np.array(owner), roots


def visit_shares(metas, roots):
    share = {}
    for r, acts in roots.items():
        v = np.array([metas[a]["visits"] for a in acts], dtype=float)
        for a, s in zip(acts, v / max(v.sum(), 1)):
            share[a] = s
    return share


def cmd_train(features_dir, out):
    os.makedirs(out, exist_ok=True)
    X, metas, n_state = load(features_dir)
    report = {"rows": X.shape[0], "width": X.shape[1], "stateFeatures": n_state}
    E, acts, owner, roots = edge_rows(X, metas)
    share = visit_shares(metas, roots)
    multi = np.array([len(roots[o]) >= 2 for o in owner])
    for arm, variants in ARMS.items():
        def pick(kind, cond):
            return np.array([i for i, m in enumerate(metas) if m["k"] == kind and m["variant"] in variants
                             and cond(m)], dtype=np.int64)
        # V_cont: label children (non-terminal, valid).
        lab = lambda f: (lambda m: m.get("role") == "label" and m["valid"] and not m["terminal"]
                         and fold(m) in f)
        tr, va = pick("child", lab((0, 1, 2))), pick("child", lab((VAL,)))
        y = lambda rows: np.array([metas[i]["value"] for i in rows])
        model = train_model(X[tr], y(tr), X[va], y(va), "regression")
        model.save_model(os.path.join(out, f"vcont-{arm}.txt"))
        report[f"vcont-{arm}"] = {"train": len(tr), "val": len(va), "iters": model.best_iteration}
        # V_roll: leaf rollout values.
        lf = lambda f: (lambda m: fold(m) in f)
        tr, va = pick("leaf", lf((0, 1, 2))), pick("leaf", lf((VAL,)))
        model = train_model(X[tr], y(tr), X[va], y(va), "regression")
        model.save_model(os.path.join(out, f"vroll-{arm}.txt"))
        report[f"vroll-{arm}"] = {"train": len(tr), "val": len(va), "iters": model.best_iteration}
        # Prior: visit share of each root action.
        sel = lambda f: np.array([k for k, (a, o) in enumerate(zip(acts, owner)) if multi[k]
                                  and metas[o]["variant"] in variants and fold(metas[o]) in f])
        tr, va = sel((0, 1, 2)), sel((VAL,))
        ys = lambda rows: np.array([share[acts[k]] for k in rows])
        model = train_model(E[tr], ys(tr), E[va], ys(va), "cross_entropy")
        model.save_model(os.path.join(out, f"prior-{arm}.txt"))
        report[f"prior-{arm}"] = {"train": len(tr), "val": len(va), "iters": model.best_iteration}
        print(arm, json.dumps({k: v for k, v in report.items() if arm in k}), flush=True)
    json.dump(report, open(os.path.join(out, "train.json"), "w"), indent=2)


def boot_mean(diff, seeds, rng):
    """Seed-clustered bootstrap of the mean of `diff`: (mean, lo, hi)."""
    us, inv = np.unique(seeds, return_inverse=True)
    sums = np.bincount(inv, weights=diff)
    cnts = np.bincount(inv).astype(float)
    draws = rng.integers(0, len(us), size=(BOOT, len(us)))
    means = sums[draws].sum(1) / cnts[draws].sum(1)
    return float(diff.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def concordance(score, label):
    agree = total = 0.0
    n = len(label)
    for i in range(n):
        for j in range(i + 1, n):
            dl = label[i] - label[j]
            if dl == 0:
                continue
            ds = score[i] - score[j]
            total += 1
            agree += 0.5 if ds == 0 else float(np.sign(ds) == np.sign(dl))
    return agree, total


def cmd_gatea(features_dir, out):
    X, metas, _ = load(features_dir)
    groups = {}
    for i, m in enumerate(metas):
        if m["k"] == "child":
            groups.setdefault(root_id(m), {}).setdefault(m["e"], {})[
                m["role"] + str(m.get("rep", ""))] = i
    models = {name: lgb.Booster(model_file=os.path.join(out, name + ".txt"))
              for name in ("vcont-natpert", "vcont-nat", "vroll-natpert", "vroll-nat")}
    probes = sorted({g["probe"] for edges in groups.values() for g in edges.values() if "probe" in g})
    preds = {name: dict(zip(probes, model.predict(X[probes]))) for name, model in models.items()}
    rng = np.random.default_rng(7)
    result = {}
    for variant in ("natural", "perturbed"):
        rows = []
        for rid, edges in groups.items():
            if rid[0] != variant or (rid[1] - BASE[variant]) % 5 != TEST or len(edges) < 2:
                continue
            es = sorted(edges)
            labs = [[metas[edges[e][f"label{r}"]] for r in (0, 1)] for e in es]
            if any(not l["valid"] for ls in labs for l in ls):
                continue
            L = np.array([np.mean([l["value"] for l in ls]) for ls in labs])
            probe = [metas[edges[e]["probe"]] for e in es]
            exact = [p["exact"] if p["terminal"] else None for p in probe]
            scores = {"R1": [p["rollouts"][0] for p in probe],
                      "R4": [float(np.mean(p["rollouts"])) for p in probe]}
            for name in models:
                scores[name] = [ex if ex is not None else preds[name][edges[e]["probe"]]
                                for e, ex in zip(es, exact)]
            row = {"seed": rid[1]}
            for name, s in scores.items():
                s = np.array(s, dtype=float)
                row["regret_" + name] = L.max() - L[int(np.argmax(s))]
                row["conc_" + name] = concordance(s, L)
            rows.append(row)
        seeds = np.array([r["seed"] for r in rows])
        res = {"groups": len(rows), "seeds": len(set(seeds.tolist()))}
        for name in ["R1", "R4"] + list(models):
            reg = np.array([r["regret_" + name] for r in rows])
            a = sum(r["conc_" + name][0] for r in rows)
            t = sum(r["conc_" + name][1] for r in rows)
            res[name] = {"regret": float(reg.mean()), "concordance": a / t}
            if name != "R1":
                res[name]["regretMinusR1"] = boot_mean(reg - np.array([r["regret_R1"] for r in rows]), seeds, rng)
        result[variant] = res
    nat = result["natural"]
    primary = nat["vcont-natpert"]
    result["gateA"] = {"pass": primary["regretMinusR1"][2] < 0 and primary["concordance"] > nat["R1"]["concordance"],
                       "secondaryPass": [n for n in models if n != "vcont-natpert"
                                         and nat[n]["regretMinusR1"][2] < 0
                                         and nat[n]["concordance"] > nat["R1"]["concordance"]]}
    json.dump(result, open(os.path.join(out, "gateA.json"), "w"), indent=2)
    print(json.dumps(result, indent=2))


def teacher(metas, acts):
    t = []
    for a in acts:
        qs = [metas[a][k] for k in ("q", "q2") if metas[a].get(k) is not None]
        t.append(float(np.mean(qs)) if qs else None)
    low = min(x for x in t if x is not None)
    return [low if x is None else x for x in t]


def cmd_tasks(features_dir, corpus_dir, out, split, arm):
    """Replay tasks for SPLIT (val|test) roots with a second teacher; ARM picks the prior."""
    X, metas, _ = load(features_dir)
    E, acts, owner, roots = edge_rows(X, metas)
    want_fold = {"val": VAL, "test": TEST}[split]
    chosen = [r for r, a in roots.items() if len(a) >= 2 and metas[r]["variant"] == "natural"
              and metas[r]["second"] and fold(metas[r]) == want_fold]
    if split == "val":
        chosen = chosen[:: max(1, len(chosen) // 2000)][:2000]
    pos = {a: k for k, a in enumerate(acts)}
    model = lgb.Booster(model_file=os.path.join(out, f"prior-{arm}.txt"))
    rows = np.array([pos[a] for r in chosen for a in roots[r]])
    raw = dict(zip(rows, model.predict(E[rows])))
    share = visit_shares(metas, roots)
    priors = {}
    for r in chosen:
        p = np.array([raw[pos[a]] for a in roots[r]])
        priors[root_id(metas[r])] = {"model": (p / p.sum()).tolist(),
                                     "oracle": [share[a] for a in roots[r]],
                                     "bits": [metas[a]["bits"] for a in roots[r]],
                                     "teacher": teacher(metas, roots[r])}
    json.dump({"|".join(map(str, k)): v for k, v in priors.items()},
              open(os.path.join(out, f"roots-{split}-{arm}.json"), "w"))
    arms = [("plain", None, 0)]
    if split == "val":
        arms += [(f"model-w{w}", "model", w) for w in WEIGHTS]
    else:
        w = json.load(open(os.path.join(out, f"weight-{arm}.json")))["weight"]
        arms += [(f"model-w{w}", "model", w), (f"oracle-w{w}", "oracle", w)]
    with open(os.path.join(out, f"tasks-{split}-{arm}.jsonl"), "w") as f:
        for path in sorted(glob.glob(os.path.join(corpus_dir, "natural-*.jsonl.gz"))):
            for line in gzip.open(path, "rt"):
                if '"kind":"root"' not in line:
                    continue
                row = json.loads(line)
                rid = (row["variant"], row["seed"], row["fight"], row["decision"])
                if rid not in priors:
                    continue
                pr = priors[rid]
                for name, source, w in arms:
                    f.write(json.dumps({"id": ["|".join(map(str, rid)), name], "wire": row["wire"],
                                        "bits": pr["bits"], "prior": pr[source] if source else None,
                                        "weight": w, "budgets": BUDGETS, "seeds": REPLAY_SEEDS}) + "\n")
    print(split, arm, "roots", len(priors), "arms", [a[0] for a in arms])


def replay_regrets(out, split, arm):
    path = os.path.join(out, f"roots-{split}-{arm}.json")
    if not os.path.exists(path):
        return {}, 0
    roots = json.load(open(path))
    regret, dropped = {}, 0
    for path in glob.glob(os.path.join(out, f"replay-{split}-{arm}-*.jsonl")):
        for line in open(path):
            if not line.startswith("{"):   # one_combat prints model banners to stdout
                continue
            r = json.loads(line)
            rid, name = r["id"]
            if not r["ok"]:
                dropped += 1
                continue
            info = roots[rid]
            T = np.array(info["teacher"])
            for run in r["runs"]:
                chosen = info["bits"].index(run["chosen"])
                regret.setdefault(name, {}).setdefault(run["budget"], {})[(rid, run["seed"])] = T.max() - T[chosen]
    return regret, dropped


def cmd_gateb(features_dir, out):
    rng = np.random.default_rng(11)
    result = {}
    for arm in ARMS:
        val, vdrop = replay_regrets(out, "val", arm)
        if val:
            means = {w: np.mean(list(val[f"model-w{w}"][256].values())) for w in WEIGHTS}
            best = min(WEIGHTS, key=lambda w: (round(means[w], 9), w))
            json.dump({"weight": best, "valMeans": means, "plain": np.mean(list(val["plain"][256].values())),
                       "dropped": vdrop}, open(os.path.join(out, f"weight-{arm}.json"), "w"), indent=2)
        test, tdrop = replay_regrets(out, "test", arm)
        if not test:
            continue
        res = {"dropped": tdrop}
        plain = test["plain"]
        common = None
        for name in test:
            for b in BUDGETS:
                keys = set(test[name][b])
                common = keys if common is None else common & keys
        common = sorted(common)
        seeds = np.array([int(k[0].split("|")[1]) for k in common])
        res["runs"] = len(common)
        for name in test:
            res[name] = {}
            for b in BUDGETS:
                reg = np.array([test[name][b][k] for k in common])
                base = np.array([plain[b][k] for k in common])
                res[name][b] = {"regret": float(reg.mean()), "ge3": int((reg >= 3).sum())}
                if name != "plain":
                    res[name][b]["minusPlain"] = boot_mean(reg - base, seeds, rng)
        model_name = next(n for n in test if n.startswith("model"))
        m = res[model_name]
        res["gateB"] = {"prior": model_name,
                        "pass": m[256]["minusPlain"][2] < 0
                        and all(m[b]["ge3"] <= res["plain"][b]["ge3"] for b in BUDGETS)}
        result[arm] = res
    json.dump(result, open(os.path.join(out, "gateB.json"), "w"), indent=2, default=str)
    print(json.dumps(result, indent=2, default=str))


def below_f32(t):
    """Smallest float32 c with (x < c) == (x <= t) for every float32 x."""
    f = np.float32(t)
    if float(f) > t:
        f = np.nextafter(f, np.float32(-np.inf))
    return float(np.nextafter(f, np.float32(np.inf)))


def compact_predict(lines, X):
    """Margin of a combat_policy_trees_v1 model on CSR rows (parity check)."""
    it = iter(" ".join(lines).split())
    assert next(it) == "combat_policy_trees_v1" and next(it) == "nfeat"
    n = int(next(it))
    cols = []
    for _ in range(n):
        assert next(it) == "feat"
        cols.append(next(it))
    assert next(it) == "base_score"
    margin = np.full(X.shape[0], float(next(it)))
    assert next(it) == "ntrees"
    trees = []
    for _ in range(int(next(it))):
        assert next(it) == "tree"
        next(it)
        nodes = []
        for _ in range(int(next(it))):
            if next(it) == "L":
                nodes.append((-1, float(next(it)), 0, 0))
            else:
                nodes.append((int(next(it)), float(next(it)), int(next(it)), int(next(it))))
        trees.append(nodes)
    return cols, trees, margin


def cmd_export(model_path, names_path, out_path, features_dir, parity_rows="2000"):
    """LightGBM (sparse CSR, Column_i = policy feature i) -> combat_policy_trees_v1."""
    names = json.load(open(names_path))
    model = lgb.Booster(model_file=model_path)
    dump = model.dump_model()
    used = sorted({n["split_feature"] for t in dump["tree_info"] for n in _splits(t["tree_structure"])})
    pos = {f: i for i, f in enumerate(used)}
    lines = ["combat_policy_trees_v1", f"nfeat {len(used)}"] + [f"feat {names[f]}" for f in used]
    lines += ["base_score 0", f"ntrees {len(dump['tree_info'])}"]
    for t, info in enumerate(dump["tree_info"]):
        order, queue = [], [info["tree_structure"]]
        while queue:  # breadth-first, so the last node is a leaf
            node = queue.pop(0)
            order.append(node)
            if "split_index" in node:
                queue += [node["left_child"], node["right_child"]]
        index = {id(n): i for i, n in enumerate(order)}
        lines.append(f"tree {t} {len(order)}")
        for n in order:
            if "split_index" not in n:
                lines.append(f"L {float(n['leaf_value'])!r}")
                continue
            if n["decision_type"] != "<=" or n.get("missing_type", "None") not in ("None", "NaN"):
                raise ValueError(f"unsupported split {n['decision_type']} {n.get('missing_type')}")
            lines.append(f"S {pos[n['split_feature']]} {below_f32(float(n['threshold']))!r} "
                         f"{index[id(n['left_child'])]} {index[id(n['right_child'])]}")
    open(out_path, "w").write("\n".join(lines) + "\n")
    # Parity on real edge rows: exported trees vs LightGBM raw margins.
    X, metas, _ = load(features_dir)
    E, _, _, _ = edge_rows(X, metas)
    rows = np.random.default_rng(5).choice(E.shape[0], int(parity_rows), replace=False)
    sub = E[rows].astype(np.float32).toarray()
    want = model.predict(E[rows], raw_score=True)
    _, trees, got = compact_predict(lines, sub)
    for nodes in trees:
        for r in range(sub.shape[0]):
            i = 0
            while nodes[i][0] >= 0:
                f, thr, yes, no = nodes[i]
                i = yes if sub[r, used[f]] < thr else no
            got[r] += nodes[i][1]
    err = float(np.abs(got - want).max())
    print(json.dumps({"trees": len(dump["tree_info"]), "features": len(used), "parityRows": len(rows),
                      "maxAbsMarginError": err}))
    assert err < 1e-3, err


def _splits(node):
    if "split_index" in node:
        yield node
        yield from _splits(node["left_child"])
        yield from _splits(node["right_child"])


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"train": cmd_train, "gatea": cmd_gatea, "tasks": cmd_tasks, "gateb": cmd_gateb,
     "export": cmd_export}[cmd](*args)
