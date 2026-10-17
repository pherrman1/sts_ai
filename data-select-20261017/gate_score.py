# compare heart1score outputs (one per student) with labels; print top-1 by group
import json, sys, collections
labels = [json.loads(l) for l in open(sys.argv[1])]
outs = {p: [json.loads(l)["logits"] for l in open(p)] for p in sys.argv[2:]}
SEL = {1: "TRANSFORM", 2: "TRANSFORM_UPGRADE", 3: "UPGRADE", 4: "REMOVE", 5: "DUPLICATE", 6: "OBTAIN"}
for p, lg in outs.items():
    assert len(lg) == len(labels), (p, len(lg), len(labels))
    g = collections.defaultdict(lambda: [0, 0])
    for lab, l in zip(labels, lg):
        assert len(l) == lab["n"], (p, len(l), lab["n"])
        hit = max(range(len(l)), key=l.__getitem__) == lab["t"]
        keys = [(lab["set"], "all")]
        if lab["set"] == "new":
            keys += [("new", "select", SEL.get(lab["sel"]))] if lab["kind"] == "select" else [("new", "node", "act%d" % lab["act"])]
        for k in keys: g[k][0] += hit; g[k][1] += 1
    print(p)
    for k in sorted(g, key=str): print("  ", k, g[k][1], "%.2f%%" % (100 * g[k][0] / g[k][1]))
