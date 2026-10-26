#!/usr/bin/env python3
"""AZ gen 2 value distillation: copy capture rows adding the teacher's value, "teacher_v" = sigmoid(value logit).
(Derived from label_teacher.py; the row's own "logits" (search targets) are kept unchanged.)
Original header of label_teacher.py:
AZ gen 2 Stage T step 2: label every captured state that has a heart1 record with a teacher's choice logits.

usage: label_teacher.py SILVERBOT_REPO TEACHER.pt OUTDIR --data a.capture.jsonl.gz ... [--trim-map] [--amp]
Each input file is rewritten to OUTDIR/<same name> with every row that has "record": "logits" = the teacher's logits
over the record's choice tokens (distill.py's SECTIONS order), the row's previous "logits" kept as "search_logits";
all other fields (z, act, deck_misc, screen, ...) unchanged. Rows without "record" are dropped. The teacher runs as
student_inputs.ExtraInputsNN at the checkpoint's own size (n_heads from --heads), bf16 autocast with --amp, on the
records as captured (untrimmed unless --trim-map, matching how the teacher was trained)."""
import argparse, gzip, json, os, sys
ap = argparse.ArgumentParser()
ap.add_argument("repo"); ap.add_argument("ckpt"); ap.add_argument("out"); ap.add_argument("--data", nargs="+", required=True)
ap.add_argument("--heads", type=int, default=8); ap.add_argument("--bs", type=int, default=256)
ap.add_argument("--device", default="cuda"); ap.add_argument("--amp", action="store_true"); ap.add_argument("--trim-map", action="store_true")
a = ap.parse_args()
sys.path[:0] = [a.repo, os.path.join(a.repo, "build"), os.path.join(os.path.dirname(os.path.abspath(__file__)))]
import torch
from silverbot import network
sys.path.insert(0, os.environ["STS_HEART1_TOOLS"])  # the sweep checkout's tools/heart1
import student_inputs
SECTIONS = (("cards_offered.cards", 96), ("relics_offered", 3), ("potions_offered", 5), ("fixed_actions", 5), ("paths_offered", 7))

def positions(rec):
    pos, off = [], 0
    for key, width in SECTIONS:
        pos += list(range(off, off + len(rec[key]))); off += width
    return pos

def trim(rec):
    y0 = rec["obs.mapY"]
    if y0 < 0: return rec
    keep = [i for i, y in enumerate(rec["obs.map.ys"]) if y >= y0]
    return {**rec, **{k: [rec[k][i] for i in keep] for k in ("obs.map.xs", "obs.map.ys", "obs.map.roomTypes", "obs.map.pathXs")}}

state = torch.load(a.ckpt, map_location="cpu", weights_only=True)
dim = state["norm.w"].shape[0]; layers = sum(1 for k in state if k.endswith(".norm1.w"))
mult = state["layers.0.mlp.w1.weight"].shape[0] // dim
net = student_inputs.ExtraInputsNN(network.ModelHP(dim=dim, n_layers=layers, mlp_dim_mult=mult, n_heads=a.heads, use_value_head=True))
missing, unexpected = net.load_state_dict(state, strict=False)
if unexpected or any(not k.startswith("x_") for k in missing): sys.exit(f"checkpoint mismatch: {missing} {unexpected}")
net = net.to(a.device).eval()
print(f"teacher d{dim}/L{layers}/mult{mult}/heads{a.heads}", flush=True)
os.makedirs(a.out, exist_ok=True); total = 0

def to_dev(x):
    if isinstance(x, dict): return {k: to_dev(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return type(x)(to_dev(v) for v in x)
    return x.to(a.device) if hasattr(x, "to") else x

for path in sorted(a.data):
    with gzip.open(path, "rt") as f: all_rows = [json.loads(l) for l in f if l.strip()]
    rows = [r for r in all_rows if "record" in r]
    out = []
    for i in range(0, len(rows), a.bs):
        chunk = rows[i:i + a.bs]
        recs = [trim(r["record"]) if a.trim_map else r["record"] for r in chunk]
        b = network.collate_fn([{**rec, "chosen_idx": 0, "outcome": 0.0} for rec in recs])
        b["extra"] = student_inputs.extra_batch([{**r, "record": rec} for r, rec in zip(chunk, recs)])
        with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=a.amp and a.device.startswith("cuda")):
            vv = net(to_dev(b))[1].float().cpu()
        for j, r in enumerate(chunk):
            r = dict(r); r["teacher_v"] = round(float(torch.sigmoid(vv[j])), 6)
            out.append(r)
    out += [r for r in all_rows if "record" not in r]  # rows without a record pass through unchanged
    with gzip.open(os.path.join(a.out, os.path.basename(path)), "wt") as f:
        for r in out: f.write(json.dumps(r, separators=(",", ":")) + "\n")
    total += len(out)
print(f"labeled {total} rows in {len(a.data)} files", flush=True)
