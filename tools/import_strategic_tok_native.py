#!/usr/bin/env python3
"""Rebuild a train_strategic_tok.py checkpoint from an exported OOC_STRAT_V4 file.

Inverse of export_strategic_tok.py (same block order). Used to warm-start
training (STRAT_INIT_CKPT) from a deployed .native artifact whose original .pt
is gone. Round trip: re-exporting the result must reproduce the input bytes.

    python3 tools/import_strategic_tok_native.py IN.native OUT.pt
"""
import os
import struct
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from export_strategic_tok import W_ORDER, DIMS  # noqa: E402
from strategic_tok_net import Net, NGLOB  # noqa: E402


def main():
    src, out = sys.argv[1], sys.argv[2]
    buf = open(src, "rb").read()
    if buf[:12] != b"OOC_STRAT_V4":
        raise SystemExit("not an OOC_STRAT_V4 file")
    dims = struct.unpack("17i", buf[12:12 + 68])
    if tuple(dims) != tuple(DIMS):
        raise SystemExit(f"dims {dims} != exporter dims {tuple(DIMS)}")
    off = 80

    def take(n):
        nonlocal off
        a = np.frombuffer(buf, np.float32, n, off).copy()
        off += 4 * n
        return a

    mean = take(NGLOB)
    inv = take(NGLOB)
    sd = Net().state_dict()
    for name in W_ORDER:
        sd[name] = torch.from_numpy(take(sd[name].numel()).reshape(sd[name].shape))
    for suffix in ["0.weight", "0.bias", "2.weight", "2.bias"]:
        for h in range(8):
            k = f"vals.{h}.{suffix}"
            sd[k] = torch.from_numpy(take(sd[k].numel()).reshape(sd[k].shape))
    for k in ["q.0.weight", "q.0.bias", "q.2.weight", "q.2.bias"]:
        sd[k] = torch.from_numpy(take(sd[k].numel()).reshape(sd[k].shape))
    if off != len(buf):
        raise SystemExit(f"consumed {off} of {len(buf)} bytes")
    torch.save({"state_dict": sd, "mean": mean, "inv": inv, "metrics": {},
                "rung": 4, "nrows": 0, "source_native": os.path.abspath(src)}, out)
    print(f"[import-strategic-tok] {src} -> {out}")


if __name__ == "__main__":
    main()
