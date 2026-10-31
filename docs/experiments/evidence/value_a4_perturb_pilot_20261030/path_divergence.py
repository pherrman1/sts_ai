#!/usr/bin/env python3
"""Exploratory (not pre-registered): where does each child's Act-4 decision path first differ from the control's,
and what is the paired outcome difference when it never does (same OOC path, combat may still differ).

  path_divergence.py UNITS_DIR     (dir with the unpacked unit tars: a4p-SEED.json + child jsonl.gz)
"""
import collections, glob, gzip, json, os, sys
import numpy as np


def rows(d, f):
    return [json.loads(l) for l in gzip.open(os.path.join(d, f + ".gz"), "rt")]


def main(root):
    where = collections.defaultdict(collections.Counter); diff = collections.defaultdict(list)
    for p in sorted(glob.glob(os.path.join(root, "**", "a4p-*.json"), recursive=True)):
        r = json.load(open(p)); d = os.path.dirname(p); E = r["entryDecisionIndex"]
        c0 = rows(d, r["children"][0]["file"]); st0 = {x["index"]: x for x in c0 if x.get("type") == "state"}
        d0 = [x for x in c0 if x.get("type") == "decision" and x["decisionIndex"] >= E]
        y0 = int(r["children"][0]["heartKilled"])
        for c in r["children"][1:]:
            ck = rows(d, c["file"]); stk = {x["index"]: x for x in ck if x.get("type") == "state"}
            dk = [x for x in ck if x.get("type") == "decision" and x["decisionIndex"] >= E]
            first = "same"
            for a, b in zip(d0, dk):
                if ((a.get("selectedKey"), a.get("by")) != (b.get("selectedKey"), b.get("by"))
                        or st0[a["stateIndex"]]["floor"] != stk[b["stateIndex"]]["floor"]):
                    first = "floor%d" % st0[a["stateIndex"]]["floor"]; break
            if first == "same" and len(d0) != len(dk):
                first = "length"
            where[c["op"]][first] += 1
            diff[(c["op"], first == "same")].append(int(c["heartKilled"]) - y0)
    out = {op: dict(cn) for op, cn in sorted(where.items())}
    out["same_path_mean_diff"] = {op: [len(v), float(np.mean(v))] for (op, same), v in sorted(diff.items()) if same}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
