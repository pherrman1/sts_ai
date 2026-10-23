#!/usr/bin/env python3
"""Export an end-to-end leaf net (diag2.py SAVE=1 checkpoint) for Silver and exact_combat_solver.

The trunk becomes a combat_policy_mlp_v2 file: models/combat_policy_mlp_g7f_E.txt with the lines that make
policyMlpBase (state_w = state.weight x scales, b1 = act.bias, enc / mon_id / mon_dmg = the projected embedding
tables, as export_native.py writes them) replaced by the trained trunk; every other line stays byte-identical, so
only relu(base) changes (STS_SILVER_LEAF_HEAD_TRUNK / --leaf-trunk read nothing else). The head becomes a
silver_value_head_v1 file (scale 100) on that trunk, with the fixed standardizer the training used.
First checks that g7f_E's own text file equals the same export of model.pt (the trunk this net started from).

usage: export_e2e.py G7F_E_MODEL.pt G7F_E.txt CKPT.pt OUT_TRUNK.txt OUT_HEAD.txt
"""
import sys

import numpy as np
import torch

g7, g7txt, ckp, out_trunk, out_head = sys.argv[1:6]
base = torch.load(g7, map_location="cpu", weights_only=False)
scales = np.asarray(base["scales"][0], np.float64)
ck = torch.load(ckp, map_location="cpu", weights_only=False)


def tables(st):
    st = {k: v.detach().double().numpy() for k, v in st.items()}
    return {"state_w": st["state.weight"] * scales[:, None], "b1": st["act.bias"],
            "enc": st["enc.weight"] @ st["encproj.weight"].T,
            "mon_id": st["monid.weight"] @ st["monproj.weight"][:, :16].T,
            "mon_dmg": st["monint.weight"] @ st["monproj.weight"][:, 16:].T}


def fmt(a):
    return " ".join(f"{x:.9g}" for x in np.asarray(a, np.float32).ravel())


lines = open(g7txt).read().split("\n")
pos = {}
for i, ln in enumerate(lines):
    key = ln.split(" ")[0]
    if key in ("state_w", "b1", "enc", "mon_id", "mon_dmg") and i + 1 < len(lines) and key not in pos:
        pos[key] = i + 1
assert set(pos) == {"state_w", "b1", "enc", "mon_id", "mon_dmg"}, pos

# 1. g7f_E's text file is the export of model.pt (same tables to float32 print precision).
t0 = tables(base["state"])
for k, i in pos.items():
    have = np.array(lines[i].split(" "), np.float64)
    want = np.asarray(t0[k], np.float32).ravel().astype(np.float64)
    assert have.shape == want.shape, (k, have.shape, want.shape)
    err = float(np.max(np.abs(have - want)))
    print(f"g7f_E {k}: {have.size} values, max |txt - model.pt export| = {err:.3g}")
    assert err < 1e-6 * max(1.0, float(np.max(np.abs(want)))), k

# 2. The trained trunk's tables in place of g7f_E's.
tr = ck["trunk"]
st = {"state.weight": tr["emb.weight"], "act.bias": tr["bias"], "enc.weight": tr["encw"],
      "encproj.weight": tr["encproj"], "monid.weight": tr["monid"], "monint.weight": tr["monint"],
      "monproj.weight": tr["monproj"]}
t1 = tables(st)
for k, i in pos.items():
    lines[i] = fmt(t1[k])
open(out_trunk, "w").write("\n".join(lines))

# 3. The head (Linear(128, 64), ReLU, Linear(64, 1)) with the training's fixed standardizer.
h = {k: v.detach().double().numpy() for k, v in ck["head"].items()}
keys = sorted(h)
w1, b1 = h["0.weight"], h["0.bias"]
w2, b2 = h["2.weight"][0], h["2.bias"]
assert w1.shape == (64, 128) and w2.shape == (64,), {k: h[k].shape for k in keys}
with open(out_head, "w") as f:
    f.write("silver_value_head_v1\nin 128\nhidden 64\n")
    for key, v in (("mu", ck["mu"]), ("inv_sd", ck["inv"]), ("w1", w1), ("b1", b1), ("w2", w2), ("b2", np.atleast_1d(b2))):
        f.write(key + " " + " ".join(f"{x:.9g}" for x in np.asarray(v, np.float64).ravel()) + "\n")
    f.write("scale 100\noffset 0\n")
print(f"wrote {out_trunk} and {out_head}")
