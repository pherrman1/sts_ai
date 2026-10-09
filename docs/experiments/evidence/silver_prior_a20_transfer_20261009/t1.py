#!/usr/bin/env python3
"""A20 transfer gate T1 (PREREG-T1.md): A0 prior v2 vs A20-trained vs mixed on A20 test roots.

  t1.py A0_FEATURES A20_FEATURES A0_MODEL OUT
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../tools"))
import lightgbm as lgb  # noqa: E402
import numpy as np  # noqa: E402
import scipy.sparse as sp  # noqa: E402

import silver_synth_gates as g  # noqa: E402
import silver_prior_v2 as v2  # noqa: E402

A20_BASE = {"natural": 60000000, "perturbed": 60002000}


def fold(m):
    base = A20_BASE if m["seed"] >= 60000000 else g.BASE
    return (m["seed"] - base[m["variant"]]) % 5


g.fold = fold
v2.fold = fold


def rows(features_dir):
    X, metas, n_state = g.load(features_dir)
    F, acts, owner, roots = v2.v2_rows(X, metas, n_state)
    share = g.visit_shares(metas, roots)
    y = np.array([share[a] for a in acts])
    return F, y, metas, acts, owner, roots


def train(parts, val):
    """parts: list of (F, y, idx); val: (F, y, idx). Rows of one root are contiguous."""
    Ftr = sp.vstack([p[0][p[2]] for p in parts], format="csr")
    ytr = np.concatenate([p[1][p[2]] for p in parts])
    otr = np.concatenate([p[3][p[2]] + 10**9 * k for k, p in enumerate(parts)])
    st_tr, _ = v2.groups_of(otr)
    st_va, _ = v2.groups_of(val[3][val[2]])
    dtr = lgb.Dataset(Ftr, ytr, free_raw_data=False)
    dva = lgb.Dataset(val[0][val[2]], val[1][val[2]], reference=dtr, free_raw_data=False)
    params = dict(v2.PARAMS, objective=v2.softmax_objective(st_tr), metric="None")
    val_obj = v2.softmax_eval(st_va)
    model = lgb.train(params, dtr, num_boost_round=v2.ROUNDS, valid_sets=[dva],
                      feval=lambda p, d: val_obj(p, d) if d is dva else ("group_xent", 0.0, False),
                      callbacks=[lgb.early_stopping(100, verbose=False), lgb.log_evaluation(200)])
    return model, {"trainRoots": len(st_tr), "valRoots": len(st_va), "iters": model.best_iteration,
                   "valGroupXent": model.best_score["valid_0"]["group_xent"]}


def evaluate(models, F, y, metas, acts, owner, roots, idx, rng):
    """Per test root: top-1 vs recorded 10k argmax; agree = second search has the same argmax."""
    pos = {a: k for k, a in enumerate(acts)}
    test_roots = sorted({owner[k] for k in idx})
    sub = np.array([pos[a] for r in test_roots for a in roots[r]])
    z = {name: dict(zip(sub, m.predict(F[sub], raw_score=True))) for name, m in models.items()}
    recs = []
    for r in test_roots:
        a_list = roots[r]
        vis = np.array([metas[a]["visits"] for a in a_list], float)
        best = int(np.argmax(vis))
        agree = None
        if metas[r]["second"]:
            v2s = np.array([metas[a].get("visits2") or 0 for a in a_list], float)
            agree = int(np.argmax(v2s)) == best
        share = vis / max(vis.sum(), 1)
        rec = {"seed": metas[r]["seed"], "act": metas[r]["act"], "room": metas[r]["room"],
               "enc": metas[r]["encounter"], "agree": agree}
        for name in models:
            s = np.array([z[name][pos[a]] for a in a_list])
            p = np.exp(s - s.max()); p /= p.sum()
            rec[name] = {"top1": int(np.argmax(s)) == best,
                         "xent": float(-(share * np.log(np.maximum(p, 1e-12))).sum())}
        recs.append(rec)
    return recs


def summarize(recs, names, rng, cond=lambda r: True):
    sel = [r for r in recs if cond(r)]
    if not sel:
        return {"roots": 0}
    seeds = np.array([r["seed"] for r in sel])
    out = {"roots": len(sel), "seeds": int(len(set(seeds)))}
    for n in names:
        t = np.array([r[n]["top1"] for r in sel], float)
        out[n] = {"top1": float(t.mean()), "xent": float(np.mean([r[n]["xent"] for r in sel]))}
    base = np.array([r["A0"]["top1"] for r in sel], float)
    for n in names:
        if n != "A0" and len(set(seeds)) > 1:
            d = np.array([r[n]["top1"] for r in sel], float) - base
            out[n]["minusA0"] = g.boot_mean(d, seeds, rng)
    return out


def main(a0_dir, a20_dir, a0_model, out):
    os.makedirs(out, exist_ok=True)
    rng = np.random.default_rng(13)
    A0 = rows(a0_dir)
    A20 = rows(a20_dir)

    def sel(d, folds):
        F, y, metas, acts, owner, roots = d
        return v2.select(metas, acts, owner, roots, folds)
    tr20, va20, te20 = sel(A20, (0, 1, 2)), sel(A20, (g.VAL,)), sel(A20, (g.TEST,))
    tr0, te0 = sel(A0, (0, 1, 2)), sel(A0, (g.TEST,))
    pack = lambda d, idx: (d[0], d[1], idx, d[4])
    report = {}
    mA0 = lgb.Booster(model_file=a0_model)
    mA20, report["trainA20"] = train([pack(A20, tr20)], pack(A20, va20))
    mA20.save_model(os.path.join(out, "prior-a20.txt"))
    mMix, report["trainMixed"] = train([pack(A0, tr0), pack(A20, tr20)], pack(A20, va20))
    mMix.save_model(os.path.join(out, "prior-mixed.txt"))
    models = {"A0": mA0, "A20": mA20, "Mixed": mMix}
    names = list(models)
    recs = evaluate(models, A20[0], A20[1], A20[2], A20[3], A20[4], A20[5], te20, rng)
    report["a20Test"] = {
        "all": summarize(recs, names, rng),
        "agree": summarize(recs, names, rng, lambda r: r["agree"] is True),
        **{f"act{a}": summarize(recs, names, rng, lambda r, a=a: r["act"] == a) for a in (1, 2, 3)},
        "boss": summarize(recs, names, rng, lambda r: r["room"] == "BOSS"),
        "act3boss": summarize(recs, names, rng, lambda r: r["room"] == "BOSS" and r["act"] == 3),
    }
    recs0 = evaluate(models, A0[0], A0[1], A0[2], A0[3], A0[4], A0[5], te0, rng)
    report["a0Test"] = {"all": summarize(recs0, names, rng),
                        "agree": summarize(recs0, names, rng, lambda r: r["agree"] is True)}
    json.dump(report, open(os.path.join(out, "t1-report.json"), "w"), indent=2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:])
