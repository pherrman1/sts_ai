#!/usr/bin/env python3
"""Student C parity: silverbot torch forward (with distill.py trim) vs native heart1score logits, and native top-1 vs
the captured heart1 logits. usage: student_parity.py SILVERBOT_REPO student.pt records.jsonl native.jsonl
(records: {"record","logits","screen"} lines from heart1-distill captures; native: one_combat heart1score output)."""
import json, os, sys
sb, ckpt, recs, native = sys.argv[1:5]
sys.path.insert(0, sb); sys.path.insert(0, sb + "/build"); sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "tools", "heart1"))
import torch
import heart1_reference as ref
from silverbot import network
def trim(rec):
    y0 = rec["obs.mapY"]
    if y0 < 0: return rec
    keep = [i for i, y in enumerate(rec["obs.map.ys"]) if y >= y0]
    rec = dict(rec)
    for k in ("obs.map.xs", "obs.map.ys", "obs.map.roomTypes", "obs.map.pathXs"):
        rec[k] = [rec[k][i] for i in keep]
    return rec
net = network.NN(network.ModelHP(dim=64, n_layers=2, mlp_dim_mult=4, n_heads=4, use_value_head=True))
net.load_state_dict(torch.load(ckpt, map_location="cpu", weights_only=True)); net.eval()
rows = [json.loads(l) for l in open(recs)]
nat = [json.loads(l) for l in open(native)]
out = []
for i in range(0, len(rows), 64):
    out += ref.silverbot_score(network, net, [trim(r["record"]) for r in rows[i:i+64]])
md = 0; agree = 0; h1agree = 0; byscreen = {}
for r, (lg, v), n in zip(rows, out, nat):
    md = max(md, max(abs(a - b) for a, b in zip(lg, n["logits"])), abs(v - n["value"]))
    am = lambda x: max(range(len(x)), key=x.__getitem__)
    agree += am(lg) == am(n["logits"])
    ok = am(n["logits"]) == am(r["logits"]); h1agree += ok
    s = byscreen.setdefault(r["screen"], [0, 0]); s[0] += 1; s[1] += ok
print(f"n={len(rows)} torch_vs_native max_abs_diff={md:.2e} argmax_agree={agree}/{len(rows)}")
print(f"native C top1 vs heart1 = {h1agree}/{len(rows)} = {h1agree/len(rows):.4f}; by screen", {k: f"{v[1]}/{v[0]}" for k, v in sorted(byscreen.items())})
