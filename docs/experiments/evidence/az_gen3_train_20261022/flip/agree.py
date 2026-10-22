#!/usr/bin/env python3
"""Top-choice agreement of gen 3, gen 2 and student_sel on student_sel-searched validation roots.
usage: agree.py FLIPDIR FASTDIR   (FLIPDIR from build.py student_sel + heart1score; FASTDIR from fastroots.py build)"""
import json, sys
KINDS = ("token", "skip_card", "bowl")
def outs(d): return {k: [json.loads(l)["logits"] for l in open(f"{d}/out_{k}.jsonl")] for k in ("sel", "g2", "g3")}
def full(d):
    o = outs(d)
    for i, m in enumerate(json.loads(l) for l in open(d + "/meta.jsonl")):
        idx = [j for j, x in enumerate(m["logits"]) if x is not None]
        yield {k: max(idx, key=lambda j: o[k][i][j]) for k in o}
def fast(d):
    o = outs(d)
    for i, m in enumerate(json.loads(l) for l in open(d + "/meta.jsonl")):
        if m["arm"] not in ("on", "A", "E"): continue
        tok2c = {t: ci for ci, x in enumerate(m["c"]) if x["map"] in KINDS for t in x["tok"]}
        if len(set(tok2c.values())) < 2: continue
        yield {k: tok2c[max(tok2c, key=lambda t: o[k][i][t])] for k in o}
for name, rs in (("full-budget roots", list(full(sys.argv[1]))), ("fast roots", list(fast(sys.argv[2])))):
    f3 = [r for r in rs if r["g3"] != r["sel"]]; same = sum(r["g2"] == r["g3"] for r in f3)
    d32 = sum(r["g3"] != r["g2"] for r in rs)
    print(f"{name}: n {len(rs)} | gen 3 != student_sel {len(f3)} ({len(f3)/len(rs):.2%}), of which gen 2 picks the same move {same} "
          f"({same/len(f3):.0%}) | gen 2 != student_sel {sum(r['g2'] != r['sel'] for r in rs)} | gen 3 != gen 2 {d32} ({d32/len(rs):.2%})")
