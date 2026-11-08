#!/usr/bin/env python3
"""Export a combat net (tools/combat_net/model.py) to the native format read by sts::search::CombatTokNet
(combat plan stage 3, 2026-11-08).

usage: export_native.py MODEL_DIR OUT.ctn
       export_native.py --random D LAYERS HEADS SEED OUT.ctn   (an untrained net, for tests and timing)

MODEL_DIR holds model.pt (a state_dict) and eval.json (its training config). File layout, little-endian:

  8 bytes   magic "CTOKNET1"
  10 int32  d, layers, heads, ffn, g_len, m_num, q_len, a_len, value_on, aux_on
  int32     number of tensors, then per tensor: int32 name length, name (utf-8), int32 ndim, ndim int32 dims,
            float32 data (row-major)

The C++ loader looks tensors up by their state_dict name and checks every shape.
"""

import argparse
import json
import os
import struct
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model as M  # noqa: E402
import tensorize as T  # noqa: E402

MAGIC = b"CTOKNET1"


def write(net, d, layers, heads, out):
    sd = net.state_dict()
    ffn = sd["trunk.layers.0.linear1.weight"].shape[0]
    g_len = sd["glob.0.weight"].shape[1] - 256
    m_num = sd["mon_num.weight"].shape[1]
    q_len = sd["queue.weight"].shape[1]
    a_len = sd["a_num.weight"].shape[1]
    with open(out, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<10i", d, layers, heads, ffn, g_len, m_num, q_len, a_len, int(net.value_on),
                            int(net.aux_on)))
        f.write(struct.pack("<i", len(sd)))
        for name, t in sd.items():
            a = t.detach().cpu().float().contiguous().numpy()
            b = name.encode()
            f.write(struct.pack("<i", len(b)) + b)
            f.write(struct.pack("<i", a.ndim) + struct.pack(f"<{a.ndim}i", *a.shape))
            f.write(a.astype("<f4").tobytes())
    return {"d": d, "layers": layers, "heads": heads, "ffn": ffn, "g_len": g_len, "m_num": m_num, "q_len": q_len,
            "a_len": a_len, "tensors": len(sd)}


def random_net(d, layers, heads, seed):
    """An untrained net in eval mode; embeddings and biases get N(0, 0.5) noise so a test sees every input."""
    torch.manual_seed(seed)
    net = M.CombatNet(d=d, layers=layers, heads=heads, g_len=T.G_LEN, m_num=T.M_NUM, q_len=T.Q_LEN, a_len=T.A_LEN)
    with torch.no_grad():
        for mod in net.modules():
            if isinstance(mod, torch.nn.Embedding):
                mod.weight.normal_(0.0, 0.5)
        for name, p in net.named_parameters():
            if name.endswith("bias"):
                p.normal_(0.0, 0.5)
    return net.eval()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("args", nargs="+")
    ap.add_argument("--random", action="store_true")
    a = ap.parse_args(argv)
    if a.random:
        d, layers, heads, seed, out = int(a.args[0]), int(a.args[1]), int(a.args[2]), int(a.args[3]), a.args[4]
        info = write(random_net(d, layers, heads, seed), d, layers, heads, out)
    else:
        model_dir, out = a.args
        cfg = json.load(open(os.path.join(model_dir, "eval.json")))["config"]
        net = M.CombatNet(d=cfg["d"], layers=cfg["layers"], g_len=T.G_LEN, m_num=T.M_NUM, q_len=T.Q_LEN,
                          a_len=T.A_LEN, aux=not cfg["no_aux"], value=not cfg["no_value"])
        net.load_state_dict(torch.load(os.path.join(model_dir, "model.pt"), map_location="cpu"))
        info = write(net.eval(), cfg["d"], cfg["layers"], 4, out)
    print(json.dumps(info))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
