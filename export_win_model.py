#!/usr/bin/env python3
"""Export the shared compact XGBoost tree format used by native consumers.

``export_booster`` is intentionally the only logistic-tree serializer.  The
E2c trainer imports it so its truncation and node encoding cannot drift from
the established V_win exporter.
"""
import json
import sys

import xgboost as xgb


def _flatten(tree, fidx):
    byid = {}
    def walk(nd):
        byid[nd["nodeid"]] = nd
        for c in nd.get("children", []): walk(c)
    walk(tree)
    ids = sorted(byid)
    ci = {nid: i for i, nid in enumerate(ids)}
    out = []
    for nid in ids:
        nd = byid[nid]
        if "leaf" in nd:
            out.append(("L", float(nd["leaf"])))
        else:
            out.append(("S", fidx[nd["split"]], float(nd["split_condition"]), ci[nd["yes"]], ci[nd["no"]]))
    return out


def export_booster(bst, out, tree_count=None):
    """Write trees [0, tree_count) and return deterministic metadata.

    ``tree_count`` is deliberately an exclusive count.  An early-stopped
    caller passes ``best_iteration + 1``, matching XGBoost's prediction slice.
    """
    feats = bst.feature_names
    if not feats or len(set(feats)) != len(feats):
        raise ValueError("Booster must expose a unique ordered feature list")
    cfg = json.loads(bst.save_config())
    base_score = float(str(cfg["learner"]["learner_model_param"]["base_score"]).strip("[]"))
    obj = cfg["learner"]["objective"]["name"]
    logistic = int("logistic" in obj)
    dumps = bst.get_dump(dump_format="json")
    if tree_count is not None:
        if not 1 <= tree_count <= len(dumps):
            raise ValueError(f"invalid tree_count {tree_count}; Booster has {len(dumps)} trees")
        dumps = dumps[:tree_count]
    fidx = {name: i for i, name in enumerate(feats)}
    with open(out, "w", newline="\n") as f:
        f.write(f"nfeat {len(feats)}\n")
        for name in feats: f.write(f"feat {name}\n")
        f.write(f"logistic {logistic}\n")
        f.write(f"base_score {base_score:.17g}\n")
        f.write(f"ntrees {len(dumps)}\n")
        for tree_idx, dump in enumerate(dumps):
            nodes = _flatten(json.loads(dump), fidx)
            f.write(f"tree {tree_idx} {len(nodes)}\n")
            for node in nodes:
                if node[0] == "L": f.write(f"L {node[1]:.17g}\n")
                else: f.write(f"S {node[1]} {node[2]:.17g} {node[3]} {node[4]}\n")
    return {"feature_names": list(feats), "tree_count": len(dumps),
            "base_score": base_score, "logistic": bool(logistic), "objective": obj}


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else "models/v_win_xgb.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "build/v_win_trees.txt"
    max_trees = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    bst = xgb.Booster(); bst.load_model(model)
    info = export_booster(bst, out, max_trees or None)
    print(f"wrote {out}: {len(info['feature_names'])} feats, {info['tree_count']} trees, "
          f"base_score {info['base_score']}, logistic {int(info['logistic'])}")


if __name__ == "__main__":
    main()
