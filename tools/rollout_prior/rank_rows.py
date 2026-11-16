#!/usr/bin/env python3
"""Root rows with recorded edge Q for the sibling-ordering measure (#1053). Same selection as calib/pv_rows.py
(validation split, prior-playout rooms, >= 2 edges, fight outcome as ref) plus k.edges = [[bits, qBacked, visits]]."""
import json, lzma, sys, tarfile
def split_of(seed): return (seed * 2654435761) % 2 ** 32 % 10
def playout_room(r): return r.get("room") == "BOSS" or (int(r.get("act", 0)) == 4 and r.get("room") == "ELITE")
out, tars = sys.argv[1], sys.argv[2:]
n = 0
with open(out, "w") as f:
    for t in tars:
        with tarfile.open(t) as tf:
            m = [x for x in tf.getmembers() if x.name.endswith(".jsonl.xz")]
            rows = [json.loads(l) for l in lzma.decompress(tf.extractfile(m[0]).read()).splitlines() if l.strip()]
        fights = {(r["seed"], r["fight"]): r for r in rows if r.get("kind") == "fight"}
        for r in rows:
            if r.get("kind") != "root" or split_of(int(r["seed"])) != 1 or not playout_room(r): continue
            if len(r.get("edges") or []) < 2 or not r.get("wire"): continue
            fr = fights.get((r["seed"], r["fight"]))
            o = {"seed": r["seed"], "fight": r["fight"], "decision": r["decision"], "wire": r["wire"],
                 "k": {"kind": "root", "enc": r.get("encounter"), "act": r.get("act"), "turn": r.get("turn"),
                       "qb": r.get("rootQBacked"), "sims": r.get("simulations"),
                       "edges": [[e["bits"], e.get("qBacked"), e.get("visits")] for e in r["edges"]],
                       "ref": None if fr is None else {"score": fr.get("score"), "won": fr.get("won"), "endHp": fr.get("endHp")}}}
            f.write(json.dumps(o) + "\n"); n += 1
print(n)
