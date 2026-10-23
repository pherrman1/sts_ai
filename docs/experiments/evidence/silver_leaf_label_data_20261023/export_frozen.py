#!/usr/bin/env python3
"""Export a frozen-trunk head (diag2.py SAVE=1 checkpoint without a trunk) as a silver_value_head_v1 file on g7f_E's
own trunk (models/combat_policy_mlp_g7f_E.txt), with the training's fixed standardizer. As run inline for the q-label
frozen head (q_frozen_head.txt).

usage: export_frozen.py CKPT.pt OUT_HEAD.txt
"""
import sys

import numpy as np
import torch

ck = torch.load(sys.argv[1], map_location="cpu", weights_only=False)
assert ck["trunk"] is None, "checkpoint has a trained trunk: use export_e2e.py"
h = {k: t.double().numpy() for k, t in ck["head"].items()}
with open(sys.argv[2], "w") as f:
    f.write("silver_value_head_v1\nin 128\nhidden 64\n")
    for key, val in (("mu", ck["mu"]), ("inv_sd", ck["inv"]), ("w1", h["0.weight"]), ("b1", h["0.bias"]),
                     ("w2", h["2.weight"][0]), ("b2", np.atleast_1d(h["2.bias"][0]))):
        f.write(key + " " + " ".join(f"{x:.9g}" for x in np.asarray(val, np.float64).ravel()) + "\n")
    f.write("scale 100\noffset 0\n")
print(f"wrote {sys.argv[2]}")
