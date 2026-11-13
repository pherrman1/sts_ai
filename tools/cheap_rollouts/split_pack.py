#!/usr/bin/env python3
"""Split a pack_capture.py npz by encounter: split_pack.py PACK.npz OUT_DIR -> OUT_DIR/<ENCOUNTER>.npz (+ .meta.json)."""
import json
import os
import sys

import numpy as np


def main():
    pack, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    z = dict(np.load(pack))
    meta = json.load(open(pack + ".meta.json"))
    enc = np.array([m[0] for m in meta])
    e_ptr = np.concatenate([[0], np.cumsum(z["r_nedge"])])
    for e in sorted(set(enc)):
        rs = np.flatnonzero(enc == e)
        st = np.concatenate([np.arange(z["st_ptr"][r], z["st_ptr"][r + 1]) for r in rs])
        ed = np.concatenate([np.arange(e_ptr[r], e_ptr[r + 1]) for r in rs])
        lens = np.diff(z["st_ptr"])[rs]
        sub = {k: z[k][rs] for k in ("r_src", "r_seed", "r_fight", "r_var", "r_val", "r_nedge")}
        sub.update(st_idx=z["st_idx"][st], st_val=z["st_val"][st], st_ptr=np.concatenate([[0], np.cumsum(lens)]),
                   e_act=z["e_act"][ed], e_tgt=z["e_tgt"][ed], e_vis=z["e_vis"][ed], tags=z["tags"])
        path = os.path.join(out_dir, e + ".npz")
        np.savez(path, **sub)
        json.dump([meta[r] for r in rs], open(path + ".meta.json", "w"))
        print(e, len(rs), flush=True)


if __name__ == "__main__":
    main()
